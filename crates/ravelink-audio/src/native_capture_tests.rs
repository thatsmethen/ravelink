//! Synthetic native callbacks only: no device discovery, registration, start,
//! microphone access, or native stream teardown calls occur in these controls.
use super::*;
use crate::{ControlState, Session, Shared, Telemetry};
use objc2_core_audio_types::{AudioBuffer, AudioTimeStampFlags};
use std::sync::atomic::AtomicU64;

#[test]
fn portable_native_constants_match_the_pinned_apple_sdk() {
    use crate::native_packet as packet;
    use objc2_core_audio_types::*;
    assert_eq!(packet::LINEAR_PCM, kAudioFormatLinearPCM);
    assert_eq!(packet::FLOAT, kAudioFormatFlagIsFloat);
    assert_eq!(packet::BIG_ENDIAN, kAudioFormatFlagIsBigEndian);
    assert_eq!(packet::SIGNED, kAudioFormatFlagIsSignedInteger);
    assert_eq!(packet::PACKED, kAudioFormatFlagIsPacked);
    assert_eq!(packet::HIGH_ALIGNED, kAudioFormatFlagIsAlignedHigh);
    assert_eq!(packet::NON_INTERLEAVED, kAudioFormatFlagIsNonInterleaved);
    assert_eq!(AudioTimeStampFlags::SampleTimeValid.0, 1);
    assert_eq!(AudioTimeStampFlags::HostTimeValid.0, 2);
    assert_eq!(AudioTimeStampFlags::RateScalarValid.0, 4);
}

fn context() -> (Arc<Context>, Arc<Shared>, Arc<Telemetry>) {
    let ring = Ring::new();
    let shared = Arc::new(Shared {
        state: Mutex::new(ControlState::default()),
        epoch: AtomicU64::new(7),
    });
    let telemetry = Arc::new(Telemetry::new(&Session::new(
        "Native callback fixture",
        48000,
    )));
    let state = CaptureState::new(
        ring.clone(),
        0,
        2,
        7,
        Arc::new(AtomicBool::new(true)),
        shared.clone(),
        telemetry.clone(),
    );
    let layout = Layout::new(
        &[Format {
            rate: 48000.0,
            id: u32::from_be_bytes(*b"lpcm"),
            flags: 9,
            packet_bytes: 8,
            packet_frames: 1,
            frame_bytes: 8,
            channels: 2,
            bits: 32,
        }],
        48000,
    )
    .unwrap();
    let context = Arc::new(Context {
        object: 71,
        layout,
        gate: Arc::new(Gate {
            permit: state.permit(),
            active: Arc::new(AtomicBool::new(true)),
            alive: AtomicBool::new(true),
            accepting: AtomicBool::new(true),
        }),
        ring,
        in_flight: AtomicUsize::new(0),
        entered: AtomicBool::new(false),
        state: UnsafeCell::new(PacketState {
            capture: state,
            tracker: Tracker::default(),
            packet_index: 0,
            queue_frame: 0,
        }),
    });
    (context, shared, telemetry)
}
fn timestamp(sample: f64, host: u64) -> AudioTimeStamp {
    // The C POD contains only integer/floating fields; zero is valid for each.
    let mut timestamp: AudioTimeStamp = unsafe { std::mem::zeroed() };
    timestamp.mSampleTime = sample;
    timestamp.mHostTime = host;
    timestamp.mRateScalar = 1.0;
    timestamp.mFlags = AudioTimeStampFlags(7);
    timestamp
}
fn buffers(pcm: &mut [f32]) -> AudioBufferList {
    AudioBufferList {
        mNumberBuffers: 1,
        mBuffers: [AudioBuffer {
            mNumberChannels: 2,
            mDataByteSize: std::mem::size_of_val(pcm) as u32,
            mData: pcm.as_mut_ptr().cast(),
        }],
    }
}
fn invoke(block: &CaptureBlock, input: &mut AudioBufferList, sample: f64, host: u64) {
    let mut stamp = timestamp(sample, host);
    let mut now = timestamp(sample + 64.0, host + 4000);
    let mut output_stamp = timestamp(0.0, 0);
    let mut output = AudioBufferList {
        mNumberBuffers: 0,
        mBuffers: [AudioBuffer {
            mNumberChannels: 0,
            mDataByteSize: 0,
            mData: ptr::null_mut(),
        }],
    };
    block.call((
        NonNull::from(&mut now),
        NonNull::from(input),
        NonNull::from(&mut stamp),
        NonNull::from(&mut output),
        NonNull::from(&mut output_stamp),
    ));
}
fn fault(telemetry: &Telemetry) -> AudioFault {
    AudioFault::from_code(telemetry.fault.load(Ordering::Acquire))
}

#[test]
fn original_native_callback_publishes_expected_pcm_and_exact_gap_evidence() {
    let (context, _shared, telemetry) = context();
    let callback = capture_block(context.clone());
    let mut pcm = [0.25_f32, -0.5].repeat(512);
    let mut input = buffers(&mut pcm);
    invoke(&callback, &mut input, 50944.0, 1000);
    assert_eq!(context.ring.captured.load(Ordering::Relaxed), 512);
    assert_eq!(context.ring.test_sample(511), [0.25, -0.5]);
    // The exact 568-frame loss observed in the frozen system run must reject
    // this entire packet, rather than stitch discontinuous PCM together.
    crate::tests::OPERATIONS.with(|n| n.set(0));
    crate::tests::COUNTING.with(|on| on.set(true));
    invoke(&callback, &mut input, 52024.0, 2000);
    crate::tests::COUNTING.with(|on| on.set(false));
    assert_eq!(crate::tests::OPERATIONS.with(std::cell::Cell::get), 0);
    let attribution = telemetry.fault.snapshot().unwrap();
    assert_eq!(attribution.origin, FaultOrigin::NativeInputPacket);
    assert_eq!(attribution.direction, crate::FaultDirection::Input);
    assert_eq!(attribution.endpoint_index, Some(0));
    let raw = attribution.metadata.unwrap();
    assert_eq!(raw.native_object, Some(71));
    assert_eq!(raw.packet_index, Some(2));
    assert_eq!(raw.epoch, 7);
    assert!(raw.observed_mach_host_time.is_some());
    assert_eq!(fault(&telemetry), AudioFault::Xrun);
    assert_eq!(context.ring.captured.load(Ordering::Relaxed), 512);
    let timing = context.ring.native_timing.snapshot().unwrap();
    let first = timing.first_fault.unwrap();
    assert_eq!(first.previous.unwrap().sample_time, 50944.0);
    assert_eq!(first.previous.unwrap().frames, 512);
    assert_eq!(first.current.sample_time, 52024.0);
    assert_eq!(first.current.queue_frame, 512);
    assert_eq!(first.current.epoch, 7);
    let completion = timing.last_completed_callback.unwrap();
    assert_eq!(
        completion.outcome,
        NativeCallbackOutcome::Rejected(AudioFault::Xrun)
    );
    assert_eq!(completion.os_now_sample_time, 52088.0);
    assert_eq!(completion.os_now_host_time, 6000);
    assert_eq!(completion.os_now_flags, 7);
    assert!(completion.entry_host_time <= completion.after_pcm_host_time);
    assert!(completion.after_pcm_host_time <= completion.completion_host_time);
    // A later valid-looking callback cannot replace the pair after the fault.
    invoke(&callback, &mut input, 52536.0, 3000);
    assert_eq!(
        context.ring.native_timing.snapshot().unwrap().first_fault,
        Some(first)
    );
    assert_eq!(context.in_flight.load(Ordering::Acquire), 0);
}

#[test]
fn first_native_callback_variable_packet_sizes_and_metadata_allocate_nothing() {
    let (context, _shared, telemetry) = context();
    let callback = capture_block(context.clone());
    let mut pcm: Vec<f32> = (0..super::super::MAX_CALLBACK_FRAMES)
        .flat_map(|i| [i as f32 / 32768.0, -(i as f32) / 16384.0])
        .collect();
    let mut input = buffers(&mut pcm);
    let mut cursor = 0;
    crate::tests::OPERATIONS.with(|n| n.set(0));
    crate::tests::COUNTING.with(|on| on.set(true));
    for frames in [1, 127, 512, 16384, 256] {
        input.mBuffers[0].mDataByteSize = frames * 8;
        invoke(&callback, &mut input, cursor as f64, 1 + cursor as u64);
        cursor += frames;
        std::hint::black_box(context.ring.native_timing.snapshot());
    }
    crate::tests::COUNTING.with(|on| on.set(false));
    assert_eq!(crate::tests::OPERATIONS.with(std::cell::Cell::get), 0);
    assert_eq!(fault(&telemetry), AudioFault::None);
    assert_eq!(
        context.ring.captured.load(Ordering::Relaxed),
        u64::from(cursor)
    );
    assert_eq!(
        context.ring.test_sample(u64::from(cursor - 1)),
        [255.0 / 32768.0, -255.0 / 16384.0]
    );
}

#[test]
fn malformed_native_planes_are_rejected_before_pcm_is_borrowed() {
    for case in 0..5 {
        let (context, _shared, telemetry) = context();
        let callback = capture_block(context.clone());
        let mut pcm = [0.25_f32; 4];
        let mut input = buffers(&mut pcm);
        match case {
            0 => input.mBuffers[0].mData = ptr::null_mut(),
            1 => input.mBuffers[0].mDataByteSize = 15,
            2 => input.mBuffers[0].mNumberChannels = 1,
            3 => input.mNumberBuffers = 0,
            4 => {
                input.mBuffers[0].mDataByteSize = (super::super::MAX_CALLBACK_FRAMES as u32 + 1) * 8
            }
            _ => unreachable!(),
        }
        invoke(&callback, &mut input, 0.0, 1);
        assert_eq!(fault(&telemetry), AudioFault::InvalidBuffer, "case {case}");
        assert_eq!(context.ring.captured.load(Ordering::Relaxed), 0);
    }
}

#[test]
fn stale_epoch_cancelled_and_reentrant_native_callbacks_cannot_publish() {
    for case in 0..5 {
        let (context, _shared, telemetry) = context();
        let callback = capture_block(context.clone());
        match case {
            0 => _shared.epoch.store(8, Ordering::Release),
            1 => context.gate.active.store(false, Ordering::Release),
            2 => context.gate.alive.store(false, Ordering::Release),
            3 => context.gate.accepting.store(false, Ordering::Release),
            4 => context.entered.store(true, Ordering::Release),
            _ => unreachable!(),
        }
        let mut pcm = [0.25_f32; 4];
        invoke(&callback, &mut buffers(&mut pcm), 0.0, 1);
        if case == 4 {
            let attribution = telemetry.fault.snapshot().unwrap();
            assert_eq!(attribution.origin, FaultOrigin::NativeInputReentry);
            assert_eq!(attribution.metadata.unwrap().native_object, Some(71));
        } else {
            assert_eq!(telemetry.fault.snapshot(), None);
        }
        assert_eq!(context.ring.captured.load(Ordering::Relaxed), 0);
        assert_eq!(context.in_flight.load(Ordering::Acquire), 0);
        assert_eq!(
            fault(&telemetry),
            if case == 4 {
                AudioFault::Xrun
            } else {
                AudioFault::None
            }
        );
    }
}

#[test]
fn retained_native_block_survives_owner_drop_and_refuses_late_pcm() {
    let (context, _shared, _telemetry) = context();
    let weak = Arc::downgrade(&context);
    let ring = context.ring.clone();
    let callback = capture_block(context.clone());
    let retained = callback.clone(); // Models the documented native Block_copy.
    let uid = "offline-retained-block-fixture";
    let owner = Owner {
        selection: Selection {
            id: 9,
            uid: uid.into(),
            rate: 48000,
            streams: Vec::new(),
            layout: context.layout.clone(),
            output_streams: 0,
        },
        context: Some(context),
        callback,
        gate: weak.upgrade().unwrap().gate.clone(),
        proc_id: None,
        started: false,
        listeners: Vec::new(),
        reservation: Reservation::acquire(uid).unwrap(),
    };
    // No native stream was registered; this exercises actual owner revocation,
    // quiescence accounting and destruction without invoking device APIs.
    drop(owner);
    assert!(weak.upgrade().is_some());
    let mut pcm = [1.0_f32; 4];
    invoke(&retained, &mut buffers(&mut pcm), 0.0, 1);
    assert_eq!(ring.captured.load(Ordering::Relaxed), 0);
    let timing = ring.native_timing.snapshot().unwrap();
    assert!(timing.lifecycle[NativeLifecyclePhase::GatesRevoked as usize].is_some());
    assert!(timing.lifecycle[NativeLifecyclePhase::OwnerCompleted as usize].is_some());
    assert!(timing.lifecycle[NativeLifecyclePhase::ContextRetained as usize].is_none());
    drop(retained);
    assert!(weak.upgrade().is_none());
    // Successful teardown releases this explicit UID reservation.
    assert!(Reservation::acquire(uid).is_ok());
}

#[test]
fn native_format_notification_latches_fault_without_allocating_and_gates_late_pcm() {
    let (context, _shared, telemetry) = context();
    let callback = capture_block(context.clone());
    let mut format = address(
        kAudioStreamPropertyVirtualFormat,
        kAudioObjectPropertyScopeGlobal,
    );
    let listener = listener_block(
        context.gate.clone(),
        72,
        format,
        AudioFault::StreamInvalidated,
    );
    let mut unrelated = address(
        kAudioStreamPropertyStartingChannel,
        kAudioObjectPropertyScopeGlobal,
    );
    listener.call((1, NonNull::from(&mut unrelated)));
    assert_eq!(fault(&telemetry), AudioFault::None);
    crate::tests::OPERATIONS.with(|n| n.set(0));
    crate::tests::COUNTING.with(|on| on.set(true));
    listener.call((1, NonNull::from(&mut format)));
    crate::tests::COUNTING.with(|on| on.set(false));
    assert_eq!(crate::tests::OPERATIONS.with(std::cell::Cell::get), 0);
    assert_eq!(fault(&telemetry), AudioFault::StreamInvalidated);
    let attribution = telemetry.fault.snapshot().unwrap();
    assert_eq!(attribution.origin, FaultOrigin::NativeInputProperty);
    assert_eq!(attribution.metadata.unwrap().native_object, Some(72));
    assert_eq!(
        attribution.metadata.unwrap().property,
        Some(FaultProperty {
            selector: format.mSelector,
            scope: format.mScope,
            element: format.mElement,
        })
    );
    let mut pcm = [0.25_f32; 4];
    invoke(&callback, &mut buffers(&mut pcm), 0.0, 1);
    assert_eq!(context.ring.captured.load(Ordering::Relaxed), 0);
}

#[test]
fn unproven_native_quiescence_retains_context_and_blocks_uid_reuse() {
    let (context, _shared, telemetry) = context();
    let ring = context.ring.clone();
    let weak = Arc::downgrade(&context);
    let leaked_pointer = Arc::as_ptr(&context);
    let callback = capture_block(context.clone());
    let retained = callback.clone();
    let uid = "offline-unquiesced-native-fixture";
    context.in_flight.store(1, Ordering::Release);
    let owner = Owner {
        selection: Selection {
            id: 9,
            uid: uid.into(),
            rate: 48000,
            streams: Vec::new(),
            layout: context.layout.clone(),
            output_streams: 0,
        },
        context: Some(context),
        callback,
        gate: weak.upgrade().unwrap().gate.clone(),
        proc_id: None,
        started: false,
        listeners: Vec::new(),
        reservation: Reservation::acquire(uid).unwrap(),
    };
    drop(owner); // No native handle; only the actual bounded drain/retain path.
    assert_eq!(fault(&telemetry), AudioFault::Backend);
    assert!(Reservation::acquire(uid).is_err());
    let timing = ring.native_timing.snapshot().unwrap();
    assert_eq!(
        timing.lifecycle[NativeLifecyclePhase::QuiescenceChecked as usize]
            .unwrap()
            .callbacks_in_flight,
        Some(1)
    );
    assert!(timing.lifecycle[NativeLifecyclePhase::ContextRetained as usize].is_some());
    assert!(timing.lifecycle[NativeLifecyclePhase::OwnerCompleted as usize].is_none());
    let mut pcm = [1.0_f32; 4];
    invoke(&retained, &mut buffers(&mut pcm), 0.0, 1);
    assert_eq!(ring.captured.load(Ordering::Relaxed), 0);
    drop(retained);
    assert!(weak.upgrade().is_some());
    // The fixture has no real in-flight callback. Recover exactly the Arc that
    // Owner deliberately forgot, solely to avoid leaking synthetic test state.
    let recovered = unsafe { Arc::from_raw(leaked_pointer) };
    recovered.in_flight.store(0, Ordering::Release);
    drop(recovered);
    assert!(weak.upgrade().is_none());
    RESERVED.get().unwrap().lock().unwrap().remove(uid);
}

#[test]
fn native_overload_is_distinct_from_packet_and_reentry_faults_and_keeps_actual_address() {
    let (context, _shared, telemetry) = context();
    let registered = address(
        kAudioDeviceProcessorOverload,
        kAudioObjectPropertyScopeGlobal,
    );
    let listener = listener_block(context.gate.clone(), 93, registered, AudioFault::Xrun);
    let mut notification = registered;
    notification.mElement = 19;
    crate::tests::OPERATIONS.with(|n| n.set(0));
    crate::tests::COUNTING.with(|on| on.set(true));
    listener.call((1, NonNull::from(&mut notification)));
    crate::tests::COUNTING.with(|on| on.set(false));
    assert_eq!(crate::tests::OPERATIONS.with(std::cell::Cell::get), 0);
    let attribution = telemetry.fault.snapshot().unwrap();
    assert_eq!(attribution.fault, AudioFault::Xrun);
    assert_eq!(attribution.origin, FaultOrigin::NativeInputOverload);
    let raw = attribution.metadata.unwrap();
    assert_eq!(raw.native_object, Some(93));
    assert_eq!(
        raw.property,
        Some(FaultProperty {
            selector: kAudioDeviceProcessorOverload,
            scope: kAudioObjectPropertyScopeGlobal,
            element: 19,
        })
    );
    assert_eq!(raw.packet_index, None);
    assert!(context.ring.native_timing.snapshot().is_none());
}
