//! Original CoreAudio IOProc capture. Native timestamps and PCM planes are
//! validated before publication; device operations stay on a dedicated owner.
use super::{
    backend,
    capture::{CapturePermit, CaptureState},
    capture_transport::Ring,
    native_packet::{Format, Layout, Tracker},
    AudioError, AudioFault, FaultMetadata, FaultOrigin, FaultProperty, NativeCallbackCompletion,
    NativeCallbackOutcome, NativeCapturePacket, NativeLifecycleEvent, NativeLifecyclePhase,
    COMMAND_TIMEOUT, MAX_DEVICE_CHANNELS,
};
use block2::RcBlock;
use objc2_core_audio::*;
use objc2_core_audio_types::{AudioBufferList, AudioStreamBasicDescription, AudioTimeStamp};
use objc2_core_foundation::{CFRetained, CFString};
use std::{
    cell::UnsafeCell,
    collections::BTreeSet,
    ffi::c_void,
    mem::{offset_of, size_of, MaybeUninit},
    ptr::{self, NonNull},
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc, Arc, Mutex, OnceLock,
    },
    thread,
    time::{Duration, Instant},
};

const MAX_PROPERTY_BYTES: usize = 64 * 1024;
const MAX_PLANES: usize = MAX_DEVICE_CHANNELS as usize;
const POLL: Duration = Duration::from_millis(20);
const QUIESCE: Duration = Duration::from_millis(250);

#[derive(Clone, Debug, PartialEq)]
struct NativeStream {
    id: AudioObjectID,
    first_channel: u32,
    format: Format,
}
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Selection {
    id: AudioObjectID,
    uid: String,
    rate: u32,
    streams: Vec<NativeStream>,
    layout: Layout,
    output_streams: usize,
}
impl Selection {
    pub(crate) fn configuration(&self) -> cpal::SupportedStreamConfig {
        // The transport normalizes native formats to f32; the native ASBDs are
        // retained separately and revalidated before activation.
        cpal::SupportedStreamConfig::new(
            self.layout.channels,
            self.rate,
            cpal::SupportedBufferSize::Unknown,
            cpal::SampleFormat::F32,
        )
    }
    pub(crate) fn description(&self) -> String {
        self.streams
            .iter()
            .map(|stream| {
                let f = stream.format;
                format!(
                    "{}ch {}-bit {}{}",
                    f.channels,
                    f.bits,
                    if f.flags & super::native_packet::FLOAT != 0 {
                        "float"
                    } else {
                        "PCM"
                    },
                    if f.flags & super::native_packet::NON_INTERLEAVED != 0 {
                        " planar"
                    } else {
                        ""
                    }
                )
            })
            .collect::<Vec<_>>()
            .join(" + ")
    }
}

pub(crate) fn select(id: &str, rate: u32) -> Result<Selection, AudioError> {
    let parsed: cpal::DeviceId = id
        .parse()
        .map_err(|_| AudioError::InvalidInputId(id.into()))?;
    if parsed.host() != cpal::HostId::CoreAudio
        || parsed.id().is_empty()
        || parsed.id().contains('\0')
    {
        return Err(AudioError::InvalidInputId(id.into()));
    }
    inspect(parsed.id(), rate)
        .map_err(|error| backend("native input format discovery", Some(id.into()), error))
}

fn address(selector: u32, scope: u32) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress {
        mSelector: selector,
        mScope: scope,
        mElement: kAudioObjectPropertyElementMain,
    }
}
fn status(code: i32) -> Result<(), String> {
    if code == 0 {
        Ok(())
    } else {
        Err(format!("CoreAudio OSStatus {code}"))
    }
}
fn property<T: Copy>(
    object: AudioObjectID,
    address: AudioObjectPropertyAddress,
) -> Result<T, String> {
    let mut value = MaybeUninit::<T>::uninit();
    let mut bytes = size_of::<T>() as u32;
    // Only native integer, floating, pointer and repr(C) data types are used.
    status(unsafe {
        AudioObjectGetPropertyData(
            object,
            NonNull::from(&address),
            0,
            ptr::null(),
            NonNull::from(&mut bytes),
            NonNull::new(value.as_mut_ptr().cast()).unwrap(),
        )
    })?;
    if bytes as usize != size_of::<T>() {
        return Err("native property size changed".into());
    }
    Ok(unsafe { value.assume_init() })
}
fn property_bytes(
    object: AudioObjectID,
    address: AudioObjectPropertyAddress,
) -> Result<(Vec<u64>, usize), String> {
    let mut bytes = 0;
    status(unsafe {
        AudioObjectGetPropertyDataSize(
            object,
            NonNull::from(&address),
            0,
            ptr::null(),
            NonNull::from(&mut bytes),
        )
    })?;
    if bytes as usize > MAX_PROPERTY_BYTES {
        return Err("native property exceeds bounded storage".into());
    }
    let capacity = bytes as usize;
    let mut data = vec![0_u64; capacity.div_ceil(8).max(1)];
    status(unsafe {
        AudioObjectGetPropertyData(
            object,
            NonNull::from(&address),
            0,
            ptr::null(),
            NonNull::from(&mut bytes),
            NonNull::new(data.as_mut_ptr().cast()).unwrap(),
        )
    })?;
    if bytes as usize > capacity {
        return Err("native property grew during discovery".into());
    }
    Ok((data, bytes as usize))
}
fn objects(object: AudioObjectID, selector: u32, scope: u32) -> Result<Vec<AudioObjectID>, String> {
    let (data, bytes) = property_bytes(object, address(selector, scope))?;
    if !bytes.is_multiple_of(size_of::<AudioObjectID>()) {
        return Err("invalid native object list".into());
    }
    // Aligned owned storage covers the returned byte count, with no trailing ID.
    Ok(
        unsafe { std::slice::from_raw_parts(data.as_ptr().cast::<AudioObjectID>(), bytes / 4) }
            .to_vec(),
    )
}
fn uid(object: AudioObjectID) -> Result<String, String> {
    let raw: *mut CFString = property(
        object,
        address(
            kAudioDevicePropertyDeviceUID,
            kAudioObjectPropertyScopeGlobal,
        ),
    )?;
    let raw = NonNull::new(raw).ok_or("native device has no UID")?;
    // AudioDevicePropertyDeviceUID returns a retained CFString to the caller.
    Ok(unsafe { CFRetained::from_raw(raw) }.to_string())
}
fn inspect(wanted_uid: &str, rate: u32) -> Result<Selection, String> {
    let mut matching = None;
    for id in objects(
        kAudioObjectSystemObject as u32,
        kAudioHardwarePropertyDevices,
        kAudioObjectPropertyScopeGlobal,
    )? {
        // Unrelated disappearing devices need not prevent selecting this UID.
        if uid(id).is_ok_and(|candidate| candidate == wanted_uid) && matching.replace(id).is_some()
        {
            return Err("duplicate native input UID".into());
        }
    }
    let id = matching.ok_or("selected native input is unavailable")?;
    let alive: u32 = property(
        id,
        address(
            kAudioDevicePropertyDeviceIsAlive,
            kAudioObjectPropertyScopeGlobal,
        ),
    )?;
    let nominal: f64 = property(
        id,
        address(
            kAudioDevicePropertyNominalSampleRate,
            kAudioObjectPropertyScopeGlobal,
        ),
    )?;
    if alive == 0 || nominal != f64::from(rate) {
        return Err("native input is not alive at the requested sample rate".into());
    }
    let input_ids = objects(
        id,
        kAudioDevicePropertyStreams,
        kAudioObjectPropertyScopeInput,
    )?;
    if input_ids.is_empty() || input_ids.len() > MAX_PLANES {
        return Err("unsupported native stream count".into());
    }
    let mut streams = Vec::with_capacity(input_ids.len());
    for stream in input_ids {
        let first_channel = property(
            stream,
            address(
                kAudioStreamPropertyStartingChannel,
                kAudioObjectPropertyScopeGlobal,
            ),
        )?;
        let asbd: AudioStreamBasicDescription = property(
            stream,
            address(
                kAudioStreamPropertyVirtualFormat,
                kAudioObjectPropertyScopeGlobal,
            ),
        )?;
        streams.push(NativeStream {
            id: stream,
            first_channel,
            format: Format {
                rate: asbd.mSampleRate,
                id: asbd.mFormatID,
                flags: asbd.mFormatFlags,
                packet_bytes: asbd.mBytesPerPacket,
                packet_frames: asbd.mFramesPerPacket,
                frame_bytes: asbd.mBytesPerFrame,
                channels: asbd.mChannelsPerFrame,
                bits: asbd.mBitsPerChannel,
            },
        });
    }
    streams.sort_by_key(|stream| stream.first_channel);
    let mut next_channel = 1;
    for stream in &streams {
        if stream.first_channel != next_channel {
            return Err("native stream channel layout is not contiguous".into());
        }
        next_channel = next_channel
            .checked_add(stream.format.channels)
            .ok_or("native channel count overflow")?;
    }
    let layout = Layout::new(&streams.iter().map(|s| s.format).collect::<Vec<_>>(), rate)
        .map_err(|fault| fault.message().to_owned())?;
    let (configuration, bytes) = property_bytes(
        id,
        address(
            kAudioDevicePropertyStreamConfiguration,
            kAudioObjectPropertyScopeInput,
        ),
    )?;
    if bytes < offset_of!(AudioBufferList, mBuffers) {
        return Err("invalid native buffer-list property".into());
    }
    let pointer = configuration.as_ptr().cast::<AudioBufferList>();
    let count = unsafe { (*pointer).mNumberBuffers as usize };
    if count != layout.planes.len()
        || bytes
            < offset_of!(AudioBufferList, mBuffers)
                + count * size_of::<objc2_core_audio_types::AudioBuffer>()
    {
        return Err("native buffer layout does not match stream formats".into());
    }
    let buffers = unsafe {
        std::slice::from_raw_parts(
            ptr::addr_of!((*pointer).mBuffers).cast::<objc2_core_audio_types::AudioBuffer>(),
            count,
        )
    };
    if buffers
        .iter()
        .zip(&layout.planes)
        .any(|(buffer, plane)| buffer.mNumberChannels != plane.channels)
    {
        return Err("native plane channel count does not match its format".into());
    }
    let output_streams = objects(
        id,
        kAudioDevicePropertyStreams,
        kAudioObjectPropertyScopeOutput,
    )?
    .len();
    if output_streams > MAX_PLANES {
        return Err("unsupported native output stream count".into());
    }
    Ok(Selection {
        id,
        uid: wanted_uid.into(),
        rate,
        streams,
        layout,
        output_streams,
    })
}

type StartReply = mpsc::SyncSender<Result<(), AudioError>>;
pub(crate) struct NativeCapture {
    commands: mpsc::SyncSender<StartReply>,
    active: Arc<AtomicBool>,
    ring: Arc<Ring>,
}
impl NativeCapture {
    pub(crate) fn build(selection: &Selection, state: CaptureState) -> Result<Self, AudioError> {
        let ring = state.ring();
        let (ready_tx, ready_rx) = mpsc::sync_channel(1);
        let (commands, receiver) = mpsc::sync_channel(1);
        let active = Arc::new(AtomicBool::new(true));
        let owner_active = active.clone();
        let selection = selection.clone();
        thread::Builder::new()
            .name("ravelink-coreaudio-capture".into())
            .spawn(move || {
                owner_loop(selection, state, owner_active, receiver, ready_tx);
            })
            .map_err(|e| backend("native capture owner creation", None, e))?;
        let stream = Self {
            commands,
            active,
            ring,
        };
        match ready_rx.recv_timeout(COMMAND_TIMEOUT) {
            Ok(Ok(())) => Ok(stream),
            Ok(Err(error)) => Err(error),
            Err(mpsc::RecvTimeoutError::Timeout) => Err(AudioError::Timeout {
                operation: "native input creation",
            }),
            Err(_) => Err(AudioError::RuntimeUnavailable),
        }
    }
    pub(crate) fn play(&self) -> Result<(), AudioError> {
        let (tx, rx) = mpsc::sync_channel(1);
        self.commands
            .try_send(tx)
            .map_err(|_| AudioError::RuntimeUnavailable)?;
        match rx.recv_timeout(COMMAND_TIMEOUT) {
            Ok(result) => result,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                self.cancel();
                Err(AudioError::Timeout {
                    operation: "native input activation",
                })
            }
            Err(_) => Err(AudioError::RuntimeUnavailable),
        }
    }
    fn cancel(&self) {
        self.active.store(false, Ordering::Release);
        self.ring.native_timing.lifecycle(NativeLifecycleEvent {
            phase: NativeLifecyclePhase::HandleCancelled,
            host_time: unsafe { AudioGetCurrentHostTime() },
            status: None,
            callbacks_in_flight: None,
        });
    }
}
impl Drop for NativeCapture {
    fn drop(&mut self) {
        self.cancel();
    }
}
fn owner_loop(
    selection: Selection,
    state: CaptureState,
    active: Arc<AtomicBool>,
    commands: mpsc::Receiver<StartReply>,
    ready: StartReply,
) {
    let permit = state.permit();
    if !active.load(Ordering::Acquire) || !permit.authorized() {
        let _ = ready.send(Err(AudioError::Cancelled));
        return;
    }
    let mut native = match Owner::open(selection, state, active.clone()) {
        Ok(native) => native,
        Err(error) => {
            let _ = ready.send(Err(backend("native input creation", None, error)));
            return;
        }
    };
    if !active.load(Ordering::Acquire) || !permit.authorized() {
        let _ = ready.send(Err(AudioError::Cancelled));
        return;
    }
    if ready.send(Ok(())).is_err() {
        return;
    }
    while active.load(Ordering::Acquire) && permit.authorized() {
        match commands.recv_timeout(POLL) {
            Ok(reply) => {
                if !active.load(Ordering::Acquire) || !permit.authorized() {
                    let _ = reply.send(Err(AudioError::Cancelled));
                    return;
                }
                let result = native
                    .start()
                    .map_err(|error| backend("native input activation", None, error));
                if result.is_err() {
                    permit.fail_at(
                        AudioFault::Backend,
                        FaultOrigin::NativeInputLifecycle,
                        FaultMetadata {
                            native_object: Some(native.selection.id),
                            ..permit.metadata()
                        },
                    );
                }
                let success = result.is_ok();
                if !active.load(Ordering::Acquire) || !permit.authorized() {
                    let _ = reply.send(Err(AudioError::Cancelled));
                    return;
                }
                if reply.send(result).is_err() || !success {
                    return;
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(_) => return,
        }
    }
}

/// A UID remains reserved while its owner is blocked in an OS call, or after
/// failed teardown. Reopening cannot reuse its ID/context or accumulate leaks.
struct Reservation {
    uid: String,
    release: bool,
}
static RESERVED: OnceLock<Mutex<BTreeSet<String>>> = OnceLock::new();
impl Reservation {
    fn acquire(uid: &str) -> Result<Self, String> {
        let mut reserved = RESERVED
            .get_or_init(|| Mutex::new(BTreeSet::new()))
            .lock()
            .map_err(|_| "native owner registry is unavailable")?;
        if !reserved.insert(uid.into()) {
            return Err("selected input still has a live or unquiesced owner; wait for shutdown or restart the application".into());
        }
        Ok(Self {
            uid: uid.into(),
            release: true,
        })
    }
}
impl Drop for Reservation {
    fn drop(&mut self) {
        if self.release {
            if let Ok(mut reserved) = RESERVED.get().unwrap().lock() {
                reserved.remove(&self.uid);
            }
        }
    }
}

struct Gate {
    permit: CapturePermit,
    active: Arc<AtomicBool>,
    alive: AtomicBool,
    accepting: AtomicBool,
}
impl Gate {
    fn authorized(&self) -> bool {
        self.alive.load(Ordering::Acquire)
            && self.active.load(Ordering::Acquire)
            && self.permit.authorized()
    }
}
struct PacketState {
    capture: CaptureState,
    tracker: Tracker,
    packet_index: u64,
    queue_frame: u64,
}
struct Context {
    object: AudioObjectID,
    layout: Layout,
    gate: Arc<Gate>,
    ring: Arc<Ring>,
    in_flight: AtomicUsize,
    entered: AtomicBool,
    state: UnsafeCell<PacketState>,
}
// The IOProc is the sole state writer. A nonspinning re-entry guard prevents
// overlapping mutable access even if a broken host invokes it concurrently.
// Owner reads only atomics until callbacks have been destroyed and drained.
unsafe impl Sync for Context {}

struct Flight<'a>(&'a Context);
impl Drop for Flight<'_> {
    fn drop(&mut self) {
        self.0.in_flight.fetch_sub(1, Ordering::Release);
    }
}
struct Entered<'a>(&'a AtomicBool);
impl Drop for Entered<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}
unsafe fn io_proc(
    context: &Context,
    now: NonNull<AudioTimeStamp>,
    input: NonNull<AudioBufferList>,
    input_time: NonNull<AudioTimeStamp>,
    _output: NonNull<AudioBufferList>,
    _output_time: NonNull<AudioTimeStamp>,
) {
    // The OS-retained block owns an Arc to the context, including the interval
    // before this callback increments in_flight. No callback clones that Arc.
    let entry_host_time = unsafe { AudioGetCurrentHostTime() };
    context.in_flight.fetch_add(1, Ordering::AcqRel);
    let _flight = Flight(context);
    if !context.gate.authorized() || !context.gate.accepting.load(Ordering::Acquire) {
        return;
    }
    if context
        .entered
        .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
        .is_err()
    {
        context.gate.permit.fail_at(
            AudioFault::Xrun,
            FaultOrigin::NativeInputReentry,
            FaultMetadata {
                native_object: Some(context.object),
                observed_mach_host_time: Some(entry_host_time),
                ..context.gate.permit.metadata()
            },
        );
        return;
    }
    let _entered = Entered(&context.entered);
    let state = unsafe { &mut *context.state.get() };
    let timestamp = unsafe { input_time.as_ref() };
    let count = unsafe { ptr::addr_of!((*input.as_ptr()).mNumberBuffers).read() };
    let frames = if count == 0 {
        0
    } else {
        (unsafe { ptr::addr_of!((*input.as_ptr()).mBuffers[0].mDataByteSize).read() }) as usize
            / context.layout.planes[0].frame_bytes
    };
    let Some(index) = state.packet_index.checked_add(1) else {
        context.gate.permit.fail_at(
            AudioFault::ResourceExhausted,
            FaultOrigin::NativeInputPacket,
            FaultMetadata {
                native_object: Some(context.object),
                observed_mach_host_time: Some(entry_host_time),
                ..context.gate.permit.metadata()
            },
        );
        return;
    };
    state.packet_index = index;
    let packet = NativeCapturePacket {
        packet_index: index,
        queue_frame: state.queue_frame,
        sample_time: timestamp.mSampleTime,
        host_time: timestamp.mHostTime,
        observed_host_time: entry_host_time,
        rate_scalar: timestamp.mRateScalar,
        flags: timestamp.mFlags.0,
        frames: frames as u32,
        epoch: context.gate.permit.epoch(),
    };
    let result = unsafe { process_packet(context, state, input, packet) };
    let after_pcm_host_time = unsafe { AudioGetCurrentHostTime() };
    let outcome = match result {
        Ok(true) => NativeCallbackOutcome::Published,
        Ok(false) => NativeCallbackOutcome::Cancelled,
        Err(fault) => NativeCallbackOutcome::Rejected(fault),
    };
    match result {
        Ok(true) => {
            context
                .ring
                .native_timing
                .record(packet, state.tracker.previous, None);
            state.tracker.commit(packet);
            state.queue_frame += u64::from(packet.frames);
        }
        Ok(false) => {}
        Err(fault) => {
            context
                .ring
                .native_timing
                .record(packet, state.tracker.previous, Some(fault));
            let origin = if matches!(
                fault,
                AudioFault::CaptureOverflow | AudioFault::CaptureUnderflow
            ) {
                FaultOrigin::CaptureTransportProducer
            } else {
                FaultOrigin::NativeInputPacket
            };
            context.gate.permit.fail_at(
                fault,
                origin,
                FaultMetadata {
                    native_object: Some(context.object),
                    packet_index: Some(index),
                    observed_mach_host_time: Some(after_pcm_host_time),
                    ..context.gate.permit.metadata()
                },
            );
        }
    }
    let now = unsafe { now.as_ref() };
    context
        .ring
        .native_timing
        .complete(NativeCallbackCompletion {
            packet_index: index,
            entry_host_time,
            after_pcm_host_time,
            completion_host_time: unsafe { AudioGetCurrentHostTime() },
            os_now_sample_time: now.mSampleTime,
            os_now_host_time: now.mHostTime,
            os_now_flags: now.mFlags.0,
            outcome,
        });
}
unsafe fn process_packet(
    context: &Context,
    state: &mut PacketState,
    input: NonNull<AudioBufferList>,
    packet: NativeCapturePacket,
) -> Result<bool, AudioFault> {
    let count = unsafe { ptr::addr_of!((*input.as_ptr()).mNumberBuffers).read() as usize };
    if count != context.layout.planes.len() {
        return Err(AudioFault::InvalidBuffer);
    }
    let buffers = unsafe {
        std::slice::from_raw_parts(
            ptr::addr_of!((*input.as_ptr()).mBuffers).cast::<objc2_core_audio_types::AudioBuffer>(),
            count,
        )
    };
    let frames = context.layout.validate_sizes(buffers.iter().map(|buffer| {
        (
            buffer.mNumberChannels,
            buffer.mDataByteSize as usize,
            !buffer.mData.is_null(),
        )
    }))?;
    state.tracker.check(&packet)?;
    state
        .queue_frame
        .checked_add(frames as u64)
        .ok_or(AudioFault::ResourceExhausted)?;
    // Shape, lengths and presence were checked for every enabled plane before
    // borrowing any PCM. CoreAudio owns these bytes until this callback returns.
    let reader = context.layout.stereo_reader(|index| unsafe {
        std::slice::from_raw_parts(
            buffers[index].mData.cast::<u8>(),
            buffers[index].mDataByteSize as usize,
        )
    });
    if !context.gate.authorized() {
        return Ok(false);
    }
    state
        .capture
        .push_native_frames(frames, |frame| reader.frame(frame))
}

type ListenerBlock = RcBlock<dyn Fn(u32, NonNull<AudioObjectPropertyAddress>)>;
fn listener_block(
    gate: Arc<Gate>,
    object: AudioObjectID,
    address: AudioObjectPropertyAddress,
    fault: AudioFault,
) -> ListenerBlock {
    RcBlock::new(
        move |count: u32, changed: NonNull<AudioObjectPropertyAddress>| {
            if !gate.authorized() {
                return;
            }
            if count as usize > MAX_PROPERTY_BYTES / size_of::<AudioObjectPropertyAddress>() {
                gate.permit.fail_at(
                    AudioFault::InvalidBuffer,
                    FaultOrigin::NativeInputProperty,
                    FaultMetadata {
                        native_object: Some(object),
                        ..gate.permit.metadata()
                    },
                );
                return;
            }
            let changed = unsafe { std::slice::from_raw_parts(changed.as_ptr(), count as usize) };
            if let Some(item) = changed
                .iter()
                .find(|item| item.mSelector == address.mSelector)
            {
                let origin = if item.mSelector == kAudioDeviceProcessorOverload {
                    FaultOrigin::NativeInputOverload
                } else {
                    FaultOrigin::NativeInputProperty
                };
                gate.permit.fail_at(
                    fault,
                    origin,
                    FaultMetadata {
                        native_object: Some(object),
                        property: Some(FaultProperty {
                            selector: item.mSelector,
                            scope: item.mScope,
                            element: item.mElement,
                        }),
                        ..gate.permit.metadata()
                    },
                );
            }
        },
    )
}
type CaptureBlock = RcBlock<
    dyn Fn(
        NonNull<AudioTimeStamp>,
        NonNull<AudioBufferList>,
        NonNull<AudioTimeStamp>,
        NonNull<AudioBufferList>,
        NonNull<AudioTimeStamp>,
    ),
>;
fn capture_block(context: Arc<Context>) -> CaptureBlock {
    RcBlock::new(move |now, input, input_time, output, output_time| unsafe {
        io_proc(&context, now, input, input_time, output, output_time);
    })
}
struct Listener {
    object: AudioObjectID,
    address: AudioObjectPropertyAddress,
    block: ListenerBlock,
}
struct Owner {
    selection: Selection,
    context: Option<Arc<Context>>,
    callback: CaptureBlock,
    gate: Arc<Gate>,
    proc_id: AudioDeviceIOProcID,
    started: bool,
    listeners: Vec<Listener>,
    reservation: Reservation,
}
impl Owner {
    fn mark(&self, phase: NativeLifecyclePhase, status: Option<i32>) {
        if let Some(context) = &self.context {
            context.ring.native_timing.lifecycle(NativeLifecycleEvent {
                phase,
                host_time: unsafe { AudioGetCurrentHostTime() },
                status,
                callbacks_in_flight: Some(context.in_flight.load(Ordering::Acquire) as u64),
            });
        }
    }
    fn open(
        selection: Selection,
        state: CaptureState,
        active: Arc<AtomicBool>,
    ) -> Result<Self, String> {
        let reservation = Reservation::acquire(&selection.uid)?;
        if inspect(&selection.uid, selection.rate)? != selection {
            return Err("selected input changed since discovery".into());
        }
        let gate = Arc::new(Gate {
            permit: state.permit(),
            active,
            alive: AtomicBool::new(true),
            accepting: AtomicBool::new(false),
        });
        let context = Arc::new(Context {
            object: selection.id,
            layout: selection.layout.clone(),
            gate: gate.clone(),
            ring: state.ring(),
            in_flight: AtomicUsize::new(0),
            entered: AtomicBool::new(false),
            state: UnsafeCell::new(PacketState {
                capture: state,
                tracker: Tracker::default(),
                packet_index: 0,
                queue_frame: 0,
            }),
        });
        let callback = capture_block(context.clone());
        let mut owner = Self {
            selection,
            context: Some(context),
            callback,
            gate,
            proc_id: None,
            started: false,
            listeners: Vec::new(),
            reservation,
        };
        owner.mark(NativeLifecyclePhase::CreateRequested, None);
        // Null dispatch queue invokes synchronously on CoreAudio's IO thread.
        // CoreAudio Block_copy owns the captured Arc through DestroyIOProcID.
        let created = unsafe {
            AudioDeviceCreateIOProcIDWithBlock(
                NonNull::from(&mut owner.proc_id),
                owner.selection.id,
                None,
                RcBlock::as_ptr(&owner.callback),
            )
        };
        owner.mark(NativeLifecyclePhase::CreateReturned, Some(created));
        status(created)?;
        if owner.proc_id.is_none() {
            return Err("CoreAudio returned no IOProc".into());
        }
        owner.set_usage(
            kAudioObjectPropertyScopeInput,
            owner.selection.streams.len(),
            true,
        )?;
        owner.set_usage(
            kAudioObjectPropertyScopeOutput,
            owner.selection.output_streams,
            false,
        )?;
        for (selector, scope, fault) in [
            (
                kAudioDevicePropertyDeviceIsAlive,
                kAudioObjectPropertyScopeGlobal,
                AudioFault::DeviceUnavailable,
            ),
            (
                kAudioDevicePropertyDeviceUID,
                kAudioObjectPropertyScopeGlobal,
                AudioFault::DeviceChanged,
            ),
            (
                kAudioDevicePropertyNominalSampleRate,
                kAudioObjectPropertyScopeGlobal,
                AudioFault::StreamInvalidated,
            ),
            (
                kAudioDevicePropertyDeviceHasChanged,
                kAudioObjectPropertyScopeGlobal,
                AudioFault::DeviceChanged,
            ),
            (
                kAudioDevicePropertyStreams,
                kAudioObjectPropertyScopeInput,
                AudioFault::StreamInvalidated,
            ),
            (
                kAudioDevicePropertyStreamConfiguration,
                kAudioObjectPropertyScopeInput,
                AudioFault::StreamInvalidated,
            ),
            (
                kAudioDevicePropertyIOStoppedAbnormally,
                kAudioObjectPropertyScopeGlobal,
                AudioFault::StreamInvalidated,
            ),
            (
                kAudioDeviceProcessorOverload,
                kAudioObjectPropertyScopeGlobal,
                AudioFault::Xrun,
            ),
        ] {
            owner.listen(owner.selection.id, address(selector, scope), fault)?;
        }
        for index in 0..owner.selection.streams.len() {
            let stream = owner.selection.streams[index].id;
            owner.listen(
                stream,
                address(
                    kAudioStreamPropertyVirtualFormat,
                    kAudioObjectPropertyScopeGlobal,
                ),
                AudioFault::StreamInvalidated,
            )?;
            owner.listen(
                stream,
                address(
                    kAudioStreamPropertyStartingChannel,
                    kAudioObjectPropertyScopeGlobal,
                ),
                AudioFault::StreamInvalidated,
            )?;
        }
        // Close the discovery/listener-registration race without querying a
        // property from a real-time callback.
        if inspect(&owner.selection.uid, owner.selection.rate)? != owner.selection
            || !owner.gate.authorized()
        {
            return Err("selected input changed during setup".into());
        }
        Ok(owner)
    }
    fn listen(
        &mut self,
        object: AudioObjectID,
        address: AudioObjectPropertyAddress,
        fault: AudioFault,
    ) -> Result<(), String> {
        let block = listener_block(self.gate.clone(), object, address, fault);
        status(unsafe {
            AudioObjectAddPropertyListenerBlock(
                object,
                NonNull::from(&address),
                None,
                RcBlock::as_ptr(&block),
            )
        })?;
        self.listeners.push(Listener {
            object,
            address,
            block,
        });
        Ok(())
    }
    fn set_usage(&self, scope: u32, streams: usize, enabled: bool) -> Result<(), String> {
        if streams == 0 {
            return Ok(());
        }
        let size =
            offset_of!(AudioHardwareIOProcStreamUsage, mStreamIsOn) + streams * size_of::<u32>();
        let mut storage = vec![0_u64; size.div_ceil(8)];
        let usage = storage
            .as_mut_ptr()
            .cast::<AudioHardwareIOProcStreamUsage>();
        unsafe {
            (*usage).mIOProc =
                NonNull::new(self.proc_id.unwrap() as *const () as *mut c_void).unwrap();
            (*usage).mNumberStreams = streams as u32;
            let on = ptr::addr_of_mut!((*usage).mStreamIsOn).cast::<u32>();
            for index in 0..streams {
                on.add(index).write(u32::from(enabled));
            }
        }
        status(unsafe {
            AudioObjectSetPropertyData(
                self.selection.id,
                NonNull::from(&address(kAudioDevicePropertyIOProcStreamUsage, scope)),
                0,
                ptr::null(),
                size as u32,
                NonNull::new(storage.as_mut_ptr().cast()).unwrap(),
            )
        })
    }
    fn start(&mut self) -> Result<(), String> {
        if self.started {
            return Ok(());
        }
        if !self.gate.authorized() {
            return Err("capture was cancelled".into());
        }
        if inspect(&self.selection.uid, self.selection.rate)? != self.selection {
            return Err("native input format changed before activation".into());
        }
        self.gate.accepting.store(true, Ordering::Release);
        self.started = true;
        self.mark(NativeLifecyclePhase::StartRequested, None);
        let started = unsafe { AudioDeviceStart(self.selection.id, self.proc_id) };
        self.mark(NativeLifecyclePhase::StartReturned, Some(started));
        let result = status(started);
        if result.is_err() {
            self.gate.accepting.store(false, Ordering::Release);
            self.gate.permit.fail_at(
                AudioFault::Backend,
                FaultOrigin::NativeInputLifecycle,
                FaultMetadata {
                    native_object: Some(self.selection.id),
                    status: Some(started),
                    ..self.gate.permit.metadata()
                },
            );
        }
        result
    }
}
impl Drop for Owner {
    fn drop(&mut self) {
        // Revoke before every potentially blocking native teardown operation.
        self.gate.alive.store(false, Ordering::Release);
        self.gate.accepting.store(false, Ordering::Release);
        self.mark(NativeLifecyclePhase::GatesRevoked, None);
        let mut quiescent = true;
        let mut first_failure = None;
        if self.started {
            self.mark(NativeLifecyclePhase::StopRequested, None);
            let stopped = unsafe { AudioDeviceStop(self.selection.id, self.proc_id) };
            self.mark(NativeLifecyclePhase::StopReturned, Some(stopped));
            quiescent &= stopped == 0;
            if stopped != 0 {
                first_failure = Some(FaultMetadata {
                    native_object: Some(self.selection.id),
                    status: Some(stopped),
                    ..self.gate.permit.metadata()
                });
            }
        }
        if self.proc_id.is_some() {
            self.mark(NativeLifecyclePhase::DestroyRequested, None);
            let destroyed = unsafe { AudioDeviceDestroyIOProcID(self.selection.id, self.proc_id) };
            self.mark(NativeLifecyclePhase::DestroyReturned, Some(destroyed));
            quiescent &= destroyed == 0;
            if destroyed != 0 && first_failure.is_none() {
                first_failure = Some(FaultMetadata {
                    native_object: Some(self.selection.id),
                    status: Some(destroyed),
                    ..self.gate.permit.metadata()
                });
            }
        }
        self.mark(NativeLifecyclePhase::ListenersRemovalRequested, None);
        let mut removal_status = 0;
        for listener in &self.listeners {
            let removed = unsafe {
                AudioObjectRemovePropertyListenerBlock(
                    listener.object,
                    NonNull::from(&listener.address),
                    None,
                    RcBlock::as_ptr(&listener.block),
                )
            };
            if removal_status == 0 {
                removal_status = removed;
            }
            quiescent &= removed == 0;
            if removed != 0 && first_failure.is_none() {
                first_failure = Some(FaultMetadata {
                    native_object: Some(listener.object),
                    status: Some(removed),
                    property: Some(FaultProperty {
                        selector: listener.address.mSelector,
                        scope: listener.address.mScope,
                        element: listener.address.mElement,
                    }),
                    ..self.gate.permit.metadata()
                });
            }
        }
        self.mark(
            NativeLifecyclePhase::ListenersRemovalReturned,
            Some(removal_status),
        );
        if let Some(context) = &self.context {
            let deadline = Instant::now() + QUIESCE;
            while context.in_flight.load(Ordering::Acquire) != 0 && Instant::now() < deadline {
                thread::sleep(Duration::from_millis(1));
            }
            quiescent &= context.in_flight.load(Ordering::Acquire) == 0;
        }
        self.mark(NativeLifecyclePhase::QuiescenceChecked, None);
        if !quiescent {
            // A late OS callback must never reach freed state. This also keeps
            // its UID reserved, so repeated starts cannot accumulate contexts.
            self.reservation.release = false;
            self.mark(NativeLifecyclePhase::ContextRetained, None);
            if let Some(context) = self.context.take() {
                std::mem::forget(context);
            }
            self.gate.permit.fail_at(
                AudioFault::Backend,
                FaultOrigin::NativeInputLifecycle,
                first_failure.unwrap_or_else(|| FaultMetadata {
                    native_object: Some(self.selection.id),
                    ..self.gate.permit.metadata()
                }),
            );
        } else {
            self.mark(NativeLifecyclePhase::OwnerCompleted, None);
        }
    }
}

#[cfg(test)]
#[path = "native_capture_tests.rs"]
mod tests;
