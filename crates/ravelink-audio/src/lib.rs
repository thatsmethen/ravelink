//! Explicit-device, stopped-by-default audio runtime for macOS and Windows.
//!
//! Blocking control methods must run away from the GUI thread. One dedicated
//! thread owns CPAL hosts/devices/streams. Callbacks use a preallocated mixer,
//! planar buffers and atomic telemetry, with no application locks or allocation.
//! A command deadline cancels late output; it cannot kill a stuck OS call. A
//! supervising process is still required for hard recovery from driver hangs.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use ravelink_core::{
    CompiledMixer, InputKind, MeterReading, ResourceBudget, Session, StereoOutput, Uuid,
};
use std::{
    fmt,
    sync::{
        atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::Duration,
};

const COMMAND_TIMEOUT: Duration = Duration::from_secs(5);
const RENDER_CHUNK: usize = 2048;
const MAX_CALLBACK_FRAMES: usize = 16384;
const GRAPH_BYTES: usize = 64 * 1024 * 1024;

/// CPAL's host-qualified native ID. Stable where the OS/backend permits; never a
/// display name or a request to follow the system default device.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct OutputId(pub String);

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OutputDevice {
    pub id: OutputId,
    pub name: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunningConfiguration {
    pub output: OutputDevice,
    pub bus_id: Uuid,
    pub sample_rate: u32,
    pub device_channels: u16,
    /// The chosen mix is sent to channels 1–2; remaining device channels are silent.
    pub sample_format: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AudioError {
    UnsupportedPlatform,
    RuntimeUnavailable,
    Timeout {
        operation: &'static str,
    },
    AlreadyRunning,
    InvalidSession(String),
    InvalidOutputId(String),
    DeviceUnavailable(OutputId),
    UnsupportedConfiguration {
        device: String,
        sample_rate: u32,
    },
    Backend {
        operation: &'static str,
        device: Option<String>,
        detail: String,
    },
    Cancelled,
}
impl fmt::Display for AudioError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedPlatform => f.write_str("Audio is supported on macOS/CoreAudio and Windows/WASAPI."),
            Self::RuntimeUnavailable => f.write_str("The audio control thread is unavailable. Restart the audio runtime."),
            Self::Timeout { operation } => write!(f, "Audio {operation} exceeded its deadline. Output was cancelled; the device may be unresponsive."),
            Self::AlreadyRunning => f.write_str("Stop audio before starting a different session or output."),
            Self::InvalidSession(reason) => write!(f, "Cannot start this mix: {reason}"),
            Self::InvalidOutputId(id) => write!(f, "The selected output identity is invalid for this platform: {id}"),
            Self::DeviceUnavailable(id) => write!(f, "The selected output is unavailable: {}. Reconnect it or explicitly select another output.", id.0),
            Self::UnsupportedConfiguration { device, sample_rate } => write!(f, "{device} does not expose a supported stereo PCM output at {sample_rate} Hz. Choose a compatible output or session sample rate."),
            Self::Backend { operation, device, detail } => {
                write!(f, "Audio {operation} failed")?;
                if let Some(device) = device { write!(f, " for {device}")?; }
                write!(f, ": {detail}")
            }
            Self::Cancelled => f.write_str("Audio start was cancelled before activation."),
        }
    }
}
impl std::error::Error for AudioError {}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u32)]
pub enum AudioFault {
    None = 0,
    DeviceUnavailable = 1,
    DeviceChanged = 2,
    PermissionDenied = 3,
    StreamInvalidated = 4,
    Xrun = 5,
    Backend = 6,
    InvalidBuffer = 7,
    Render = 8,
    RealtimeDenied = 9,
    ResourceExhausted = 10,
}
impl AudioFault {
    fn from_code(code: u32) -> Self {
        match code {
            0 => Self::None,
            1 => Self::DeviceUnavailable,
            2 => Self::DeviceChanged,
            3 => Self::PermissionDenied,
            4 => Self::StreamInvalidated,
            5 => Self::Xrun,
            7 => Self::InvalidBuffer,
            8 => Self::Render,
            9 => Self::RealtimeDenied,
            10 => Self::ResourceExhausted,
            _ => Self::Backend,
        }
    }
    pub fn message(self) -> &'static str {
        match self {
            Self::None => "",
            Self::DeviceUnavailable => "The selected output disconnected. Reconnect it and start explicitly.",
            Self::DeviceChanged => "The output route changed unexpectedly. Output stopped; select the intended device again.",
            Self::PermissionDenied => "The operating system denied audio access. Check the app's audio permissions.",
            Self::StreamInvalidated => "The output format or stream became invalid. Check the device settings and start again.",
            Self::Xrun => "The device reported a buffer underrun or overrun. Output stopped; reduce audio load before restarting.",
            Self::Backend => "The audio backend reported a stream failure. Check the selected device before restarting.",
            Self::InvalidBuffer => "The device supplied an unsupported callback buffer. Output stopped.",
            Self::Render => "The mixer could not render the requested buffer. Output stopped.",
            Self::RealtimeDenied => "Real-time audio scheduling was denied. Output stopped before continuing with degraded scheduling.",
            Self::ResourceExhausted => "The operating system exhausted audio resources. Close other audio streams before restarting.",
        }
    }
}

#[derive(Clone, Debug)]
pub struct AudioSnapshot {
    pub running: bool,
    pub configuration: Option<RunningConfiguration>,
    pub rendered_frames: u64,
    pub callback_count: u64,
    pub input_meters: Vec<MeterReading>,
    pub bus_meters: Vec<MeterReading>,
    pub fault: AudioFault,
    pub error: Option<AudioError>,
}

struct AtomicMeter {
    id: Uuid,
    peak: [AtomicU32; 2],
    rms: [AtomicU32; 2],
    clipped: [AtomicU64; 2],
}
impl AtomicMeter {
    fn new(id: Uuid) -> Self {
        Self {
            id,
            peak: std::array::from_fn(|_| AtomicU32::new(0)),
            rms: std::array::from_fn(|_| AtomicU32::new(0)),
            clipped: std::array::from_fn(|_| AtomicU64::new(0)),
        }
    }
    fn publish(&self, meter: &MeterReading) {
        for side in 0..2 {
            self.peak[side].store(meter.peak[side].to_bits(), Ordering::Relaxed);
            self.rms[side].store(meter.rms[side].to_bits(), Ordering::Relaxed);
            self.clipped[side].fetch_add(meter.clipped_samples[side], Ordering::Relaxed);
        }
    }
    fn read(&self, audible: bool) -> MeterReading {
        MeterReading {
            id: self.id,
            peak: std::array::from_fn(|i| {
                if audible {
                    f32::from_bits(self.peak[i].load(Ordering::Relaxed))
                } else {
                    0.0
                }
            }),
            rms: std::array::from_fn(|i| {
                if audible {
                    f32::from_bits(self.rms[i].load(Ordering::Relaxed))
                } else {
                    0.0
                }
            }),
            clipped_samples: std::array::from_fn(|i| self.clipped[i].load(Ordering::Relaxed)),
        }
    }
}
struct Telemetry {
    fault: AtomicU32,
    frames: AtomicU64,
    callbacks: AtomicU64,
    inputs: Vec<AtomicMeter>,
    buses: Vec<AtomicMeter>,
}
impl Telemetry {
    fn new(session: &Session) -> Self {
        Self {
            fault: AtomicU32::new(0),
            frames: AtomicU64::new(0),
            callbacks: AtomicU64::new(0),
            inputs: session
                .inputs
                .iter()
                .map(|i| AtomicMeter::new(i.id))
                .collect(),
            buses: session
                .buses
                .iter()
                .map(|b| AtomicMeter::new(b.id))
                .collect(),
        }
    }
    fn fail(&self, fault: AudioFault) {
        let _ = self
            .fault
            .compare_exchange(0, fault as u32, Ordering::AcqRel, Ordering::Relaxed);
    }
}
#[derive(Default)]
struct ControlState {
    running: bool,
    configuration: Option<RunningConfiguration>,
    telemetry: Option<Arc<Telemetry>>,
    error: Option<AudioError>,
    authorization: Option<(Arc<AtomicBool>, u64)>,
}
struct Shared {
    state: Mutex<ControlState>,
    epoch: AtomicU64,
}
impl Shared {
    fn state(&self) -> std::sync::MutexGuard<'_, ControlState> {
        // No callback takes this lock. Recovering control metadata cannot enable audio.
        self.state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}
type Reply<T> = mpsc::SyncSender<Result<T, AudioError>>;
enum Command {
    Enumerate(Reply<Vec<OutputDevice>>),
    Start {
        session: Session,
        bus: Uuid,
        output: OutputId,
        epoch: u64,
        wanted: Arc<AtomicBool>,
        reply: Reply<RunningConfiguration>,
    },
    Stop(Reply<()>),
    Shutdown,
}

/// A control handle; creation never enumerates devices or starts audio.
/// Methods wait at most five seconds and should be called from a UI worker.
pub struct AudioRuntime {
    commands: mpsc::SyncSender<Command>,
    shared: Arc<Shared>,
}
impl AudioRuntime {
    pub fn new() -> Result<Self, AudioError> {
        let (commands, receiver) = mpsc::sync_channel(8);
        let shared = Arc::new(Shared {
            state: Mutex::new(ControlState::default()),
            epoch: AtomicU64::new(0),
        });
        let owner = shared.clone();
        thread::Builder::new()
            .name("ravelink-audio-control".into())
            .spawn(move || runtime_loop(receiver, owner))
            .map_err(|error| AudioError::Backend {
                operation: "thread creation",
                device: None,
                detail: error.to_string(),
            })?;
        Ok(Self { commands, shared })
    }
    pub fn enumerate_output_devices(&self) -> Result<Vec<OutputDevice>, AudioError> {
        let (tx, rx) = mpsc::sync_channel(1);
        self.send(Command::Enumerate(tx))?;
        receive(rx, "device discovery")
    }
    pub fn start(
        &self,
        session: Session,
        bus_id: Uuid,
        output_id: OutputId,
    ) -> Result<RunningConfiguration, AudioError> {
        validate_session(&session, bus_id)?;
        let wanted = Arc::new(AtomicBool::new(true));
        let (tx, rx) = mpsc::sync_channel(1);
        self.send(Command::Start {
            session,
            bus: bus_id,
            output: output_id,
            epoch: self.shared.epoch.load(Ordering::Acquire),
            wanted: wanted.clone(),
            reply: tx,
        })?;
        let result = receive(rx, "start");
        if result.is_err() {
            wanted.store(false, Ordering::Release);
        }
        result
    }
    /// Immediately prevents subsequent callback output, then asks the owner to
    /// release the stream. Already handed-off hardware samples cannot be recalled.
    pub fn stop(&self) -> Result<(), AudioError> {
        self.shared.epoch.fetch_add(1, Ordering::AcqRel);
        self.shared.state().running = false;
        let (tx, rx) = mpsc::sync_channel(1);
        self.send(Command::Stop(tx))?;
        receive(rx, "stop")
    }
    pub fn snapshot(&self) -> AudioSnapshot {
        let state = self.shared.state();
        let fault = state.telemetry.as_ref().map_or(AudioFault::None, |t| {
            AudioFault::from_code(t.fault.load(Ordering::Acquire))
        });
        let authorized = state.authorization.as_ref().is_some_and(|(wanted, epoch)| {
            wanted.load(Ordering::Acquire) && self.shared.epoch.load(Ordering::Acquire) == *epoch
        });
        let running = state.running && authorized && fault == AudioFault::None;
        let (frames, callbacks, inputs, buses) =
            state
                .telemetry
                .as_ref()
                .map_or((0, 0, Vec::new(), Vec::new()), |t| {
                    (
                        t.frames.load(Ordering::Relaxed),
                        t.callbacks.load(Ordering::Relaxed),
                        t.inputs.iter().map(|m| m.read(running)).collect(),
                        t.buses.iter().map(|m| m.read(running)).collect(),
                    )
                });
        AudioSnapshot {
            running,
            configuration: state.configuration.clone(),
            rendered_frames: frames,
            callback_count: callbacks,
            input_meters: inputs,
            bus_meters: buses,
            fault,
            error: state.error.clone(),
        }
    }
    fn send(&self, command: Command) -> Result<(), AudioError> {
        self.commands
            .try_send(command)
            .map_err(|_| AudioError::RuntimeUnavailable)
    }
}
impl Drop for AudioRuntime {
    fn drop(&mut self) {
        self.shared.epoch.fetch_add(1, Ordering::AcqRel);
        let _ = self.commands.try_send(Command::Shutdown);
        // Do not join a thread that may be blocked in an OS driver call. Callback
        // gates are revoked immediately; the thread releases resources when able.
    }
}
fn receive<T>(
    receiver: mpsc::Receiver<Result<T, AudioError>>,
    operation: &'static str,
) -> Result<T, AudioError> {
    match receiver.recv_timeout(COMMAND_TIMEOUT) {
        Ok(result) => result,
        Err(mpsc::RecvTimeoutError::Timeout) => Err(AudioError::Timeout { operation }),
        Err(mpsc::RecvTimeoutError::Disconnected) => Err(AudioError::RuntimeUnavailable),
    }
}

fn native_host() -> Result<cpal::Host, AudioError> {
    #[cfg(target_os = "macos")]
    let host = cpal::host_from_id(cpal::HostId::CoreAudio);
    #[cfg(target_os = "windows")]
    let host = cpal::host_from_id(cpal::HostId::Wasapi);
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    return Err(AudioError::UnsupportedPlatform);
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    host.map_err(|e| backend("host initialization", None, e))
}
fn backend(
    operation: &'static str,
    device: Option<String>,
    error: impl fmt::Display,
) -> AudioError {
    AudioError::Backend {
        operation,
        device,
        detail: error.to_string(),
    }
}
fn enumerate() -> Result<Vec<OutputDevice>, AudioError> {
    let host = native_host()?;
    let devices = host
        .output_devices()
        .map_err(|e| backend("device discovery", None, e))?;
    let mut outputs = Vec::new();
    for device in devices {
        let id = device
            .id()
            .map_err(|e| backend("device identity", None, e))?;
        let name = device
            .description()
            .map_err(|e| backend("device description", Some(id.to_string()), e))?
            .name()
            .to_owned();
        outputs.push(OutputDevice {
            id: OutputId(id.to_string()),
            name,
        });
    }
    outputs.sort_by(|a, b| a.name.cmp(&b.name).then_with(|| a.id.0.cmp(&b.id.0)));
    Ok(outputs)
}
fn validate_session(session: &Session, bus: Uuid) -> Result<(), AudioError> {
    session
        .validate()
        .map_err(|e| AudioError::InvalidSession(e.to_string()))?;
    if !session.buses.iter().any(|b| b.id == bus) {
        return Err(AudioError::InvalidSession(
            "the selected mix no longer exists".into(),
        ));
    }
    if session
        .inputs
        .iter()
        .any(|i| !matches!(i.kind, InputKind::TestTone { .. }))
    {
        return Err(AudioError::InvalidSession("this runtime currently supports test-tone inputs only; hardware/application/virtual capture is not implemented".into()));
    }
    Ok(())
}
fn select_config(
    configs: impl Iterator<Item = cpal::SupportedStreamConfigRange>,
    sample_rate: u32,
) -> Option<cpal::SupportedStreamConfig> {
    configs
        .filter(|c| c.channels() >= 2 && supported_pcm(c.sample_format()))
        .filter_map(|c| c.try_with_sample_rate(sample_rate))
        .min_by_key(|c| {
            (
                c.channels(),
                match c.sample_format() {
                    cpal::SampleFormat::F32 => 0,
                    cpal::SampleFormat::F64 => 1,
                    _ => 2,
                },
            )
        })
}
fn supported_pcm(format: cpal::SampleFormat) -> bool {
    matches!(
        format,
        cpal::SampleFormat::F32
            | cpal::SampleFormat::F64
            | cpal::SampleFormat::I8
            | cpal::SampleFormat::I16
            | cpal::SampleFormat::I24
            | cpal::SampleFormat::I32
            | cpal::SampleFormat::I64
            | cpal::SampleFormat::U8
            | cpal::SampleFormat::U16
            | cpal::SampleFormat::U24
            | cpal::SampleFormat::U32
            | cpal::SampleFormat::U64
    )
}

struct Running {
    _stream: cpal::Stream,
    wanted: Arc<AtomicBool>,
    telemetry: Arc<Telemetry>,
    epoch: u64,
}
fn runtime_loop(receiver: mpsc::Receiver<Command>, shared: Arc<Shared>) {
    let mut running: Option<Running> = None;
    loop {
        if running.as_ref().is_some_and(|r| {
            r.telemetry.fault.load(Ordering::Acquire) != 0
                || !r.wanted.load(Ordering::Acquire)
                || shared.epoch.load(Ordering::Acquire) != r.epoch
        }) {
            if let Some(old) = running.take() {
                old.wanted.store(false, Ordering::Release);
                drop(old);
            }
            shared.state().running = false;
        }
        match receiver.recv_timeout(Duration::from_millis(20)) {
            Ok(Command::Enumerate(reply)) => {
                let _ = reply.send(enumerate());
            }
            Ok(Command::Start {
                session,
                bus,
                output,
                epoch,
                wanted,
                reply,
            }) => {
                let result = if running.is_some() {
                    Err(AudioError::AlreadyRunning)
                } else {
                    start_stream(&session, bus, output, epoch, wanted, shared.clone())
                };
                match result {
                    Ok((owner, configuration)) => {
                        {
                            let mut state = shared.state();
                            state.running = true;
                            state.configuration = Some(configuration.clone());
                            state.telemetry = Some(owner.telemetry.clone());
                            state.error = None;
                            state.authorization = Some((owner.wanted.clone(), epoch));
                        }
                        if reply.send(Ok(configuration)).is_err() {
                            owner.wanted.store(false, Ordering::Release);
                        }
                        running = Some(owner);
                    }
                    Err(error) => {
                        if running.is_none() {
                            shared.state().error = Some(error.clone());
                        }
                        let _ = reply.send(Err(error));
                    }
                }
            }
            Ok(Command::Stop(reply)) => {
                if let Some(old) = running.take() {
                    old.wanted.store(false, Ordering::Release);
                    drop(old);
                }
                let mut state = shared.state();
                state.running = false;
                state.error = None;
                let _ = reply.send(Ok(()));
            }
            Ok(Command::Shutdown) | Err(mpsc::RecvTimeoutError::Disconnected) => break,
            Err(mpsc::RecvTimeoutError::Timeout) => {}
        }
    }
    if let Some(old) = running {
        old.wanted.store(false, Ordering::Release);
    }
}

fn start_stream(
    session: &Session,
    bus: Uuid,
    output: OutputId,
    epoch: u64,
    wanted: Arc<AtomicBool>,
    shared: Arc<Shared>,
) -> Result<(Running, RunningConfiguration), AudioError> {
    validate_session(session, bus)?;
    let id: cpal::DeviceId = output
        .0
        .parse()
        .map_err(|_| AudioError::InvalidOutputId(output.0.clone()))?;
    let host = native_host()?;
    // Avoid device_by_id's Option API, which hides device enumeration errors.
    let mut selected = None;
    for device in host
        .devices()
        .map_err(|e| backend("device discovery", None, e))?
    {
        if device
            .id()
            .map_err(|e| backend("device identity", None, e))?
            == id
        {
            selected = Some(device);
            break;
        }
    }
    let device = selected.ok_or_else(|| AudioError::DeviceUnavailable(output.clone()))?;
    let name = device
        .description()
        .map_err(|e| backend("device description", Some(output.0.clone()), e))?
        .name()
        .to_owned();
    let config = select_config(
        device
            .supported_output_configs()
            .map_err(|e| backend("output format discovery", Some(name.clone()), e))?,
        session.sample_rate,
    )
    .ok_or_else(|| AudioError::UnsupportedConfiguration {
        device: name.clone(),
        sample_rate: session.sample_rate,
    })?;
    let configuration = RunningConfiguration {
        output: OutputDevice {
            id: output,
            name: name.clone(),
        },
        bus_id: bus,
        sample_rate: config.sample_rate(),
        device_channels: config.channels(),
        sample_format: config.sample_format().to_string(),
    };
    let render = RenderState::new(
        session,
        bus,
        usize::from(config.channels()),
        epoch,
        wanted.clone(),
        shared.clone(),
    )?;
    let telemetry = render.telemetry.clone();
    if !render.authorized() {
        return Err(AudioError::Cancelled);
    }
    let stream_config = config.config();
    macro_rules! build {
        ($ty:ty) => {
            make_stream::<$ty>(&device, &stream_config, render, telemetry.clone())
        };
    }
    let stream = match config.sample_format() {
        cpal::SampleFormat::F32 => build!(f32),
        cpal::SampleFormat::F64 => build!(f64),
        cpal::SampleFormat::I8 => build!(i8),
        cpal::SampleFormat::I16 => build!(i16),
        cpal::SampleFormat::I24 => build!(cpal::I24),
        cpal::SampleFormat::I32 => build!(i32),
        cpal::SampleFormat::I64 => build!(i64),
        cpal::SampleFormat::U8 => build!(u8),
        cpal::SampleFormat::U16 => build!(u16),
        cpal::SampleFormat::U24 => build!(cpal::U24),
        cpal::SampleFormat::U32 => build!(u32),
        cpal::SampleFormat::U64 => build!(u64),
        _ => {
            return Err(AudioError::UnsupportedConfiguration {
                device: name,
                sample_rate: session.sample_rate,
            })
        }
    }
    .map_err(|e| backend("stream creation", Some(name.clone()), e))?;
    if !wanted.load(Ordering::Acquire) || shared.epoch.load(Ordering::Acquire) != epoch {
        return Err(AudioError::Cancelled);
    }
    stream
        .play()
        .map_err(|e| backend("stream activation", Some(name), e))?;
    if !wanted.load(Ordering::Acquire) || shared.epoch.load(Ordering::Acquire) != epoch {
        return Err(AudioError::Cancelled);
    }
    Ok((
        Running {
            _stream: stream,
            wanted,
            telemetry,
            epoch,
        },
        configuration,
    ))
}
fn make_stream<T>(
    device: &cpal::Device,
    config: &cpal::StreamConfig,
    mut render: RenderState,
    telemetry: Arc<Telemetry>,
) -> Result<cpal::Stream, cpal::Error>
where
    T: cpal::SizedSample + cpal::FromSample<f32>,
{
    device.build_output_stream_raw(
        *config,
        T::FORMAT,
        move |data, _| {
            if let Some(samples) = data.as_slice_mut::<T>() {
                render.write(samples);
            } else {
                render.telemetry.fail(AudioFault::InvalidBuffer);
            }
        },
        move |error| {
            use cpal::ErrorKind;
            let fault = match error.kind() {
                ErrorKind::DeviceNotAvailable => AudioFault::DeviceUnavailable,
                ErrorKind::DeviceChanged => AudioFault::DeviceChanged,
                ErrorKind::PermissionDenied => AudioFault::PermissionDenied,
                ErrorKind::StreamInvalidated => AudioFault::StreamInvalidated,
                ErrorKind::Xrun => AudioFault::Xrun,
                ErrorKind::RealtimeDenied => AudioFault::RealtimeDenied,
                ErrorKind::ResourceExhausted => AudioFault::ResourceExhausted,
                _ => AudioFault::Backend,
            };
            telemetry.fail(fault);
        },
        Some(COMMAND_TIMEOUT),
    )
}

struct RenderState {
    mixer: CompiledMixer,
    bus: Uuid,
    channels: usize,
    left: Vec<f32>,
    right: Vec<f32>,
    epoch: u64,
    wanted: Arc<AtomicBool>,
    shared: Arc<Shared>,
    telemetry: Arc<Telemetry>,
}
impl RenderState {
    fn new(
        session: &Session,
        bus: Uuid,
        channels: usize,
        epoch: u64,
        wanted: Arc<AtomicBool>,
        shared: Arc<Shared>,
    ) -> Result<Self, AudioError> {
        let overhead = session
            .inputs
            .len()
            .checked_add(session.buses.len())
            .and_then(|n| n.checked_mul(std::mem::size_of::<AtomicMeter>()))
            .and_then(|n| n.checked_add(2 * RENDER_CHUNK * std::mem::size_of::<f32>()))
            .and_then(|n| GRAPH_BYTES.checked_sub(n))
            .ok_or_else(|| {
                AudioError::InvalidSession("the graph exceeds the runtime memory budget".into())
            })?;
        let mixer = CompiledMixer::compile(
            session,
            ResourceBudget {
                max_block_frames: RENDER_CHUNK,
                max_working_bytes: overhead,
            },
        )
        .map_err(|e| AudioError::InvalidSession(e.to_string()))?;
        let telemetry = Arc::new(Telemetry::new(session));
        Ok(Self {
            mixer,
            bus,
            channels,
            left: vec![0.0; RENDER_CHUNK],
            right: vec![0.0; RENDER_CHUNK],
            epoch,
            wanted,
            shared,
            telemetry,
        })
    }
    fn authorized(&self) -> bool {
        self.wanted.load(Ordering::Acquire)
            && self.shared.epoch.load(Ordering::Acquire) == self.epoch
            && self.telemetry.fault.load(Ordering::Acquire) == 0
    }
    fn write<T: cpal::SizedSample + cpal::FromSample<f32>>(&mut self, output: &mut [T]) {
        output.fill(T::EQUILIBRIUM);
        if !self.authorized() {
            return;
        }
        if self.channels < 2
            || !output.len().is_multiple_of(self.channels)
            || output.len() / self.channels > MAX_CALLBACK_FRAMES
        {
            self.telemetry.fail(AudioFault::InvalidBuffer);
            return;
        }
        let frames = output.len() / self.channels;
        for start in (0..frames).step_by(RENDER_CHUNK) {
            let count = (frames - start).min(RENDER_CHUNK);
            let mut destinations = [StereoOutput {
                id: self.bus,
                left: &mut self.left[..count],
                right: &mut self.right[..count],
            }];
            if self.mixer.render(&[], &mut destinations, count).is_err() {
                self.telemetry.fail(AudioFault::Render);
                output.fill(T::EQUILIBRIUM);
                return;
            }
            for frame in 0..count {
                output[(start + frame) * self.channels] =
                    T::from_sample(self.left[frame].clamp(-1.0, 1.0));
                output[(start + frame) * self.channels + 1] =
                    T::from_sample(self.right[frame].clamp(-1.0, 1.0));
            }
            for (target, meter) in self.telemetry.inputs.iter().zip(self.mixer.input_meters()) {
                target.publish(meter);
            }
            for (target, meter) in self.telemetry.buses.iter().zip(self.mixer.bus_meters()) {
                target.publish(meter);
            }
        }
        // Revoke output even if a stop/fault arrived while this callback rendered.
        if !self.authorized() {
            output.fill(T::EQUILIBRIUM);
            return;
        }
        self.telemetry
            .frames
            .fetch_add(frames as u64, Ordering::Relaxed);
        self.telemetry.callbacks.fetch_add(1, Ordering::Relaxed);
    }
}

#[cfg(test)]
mod tests;
