use super::*;
use ravelink_core::{Bus, DspConfig, Input, Send};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
};

struct CountingAllocator;
thread_local! {
    static COUNTING: Cell<bool> = const { Cell::new(false) };
    static OPERATIONS: Cell<usize> = const { Cell::new(0) };
}
fn allocation_event() {
    let _ = COUNTING.try_with(|on| {
        if on.get() {
            OPERATIONS.with(|n| n.set(n.get() + 1));
        }
    });
}
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        allocation_event();
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        allocation_event();
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        allocation_event();
        unsafe { System.realloc(ptr, layout, size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        allocation_event();
        unsafe { System.dealloc(ptr, layout) }
    }
}
#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

fn session() -> (Session, Uuid) {
    let mut session = Session::new("Offline transport fixture", 48000);
    let input = Input::new(
        "440 Hz",
        InputKind::TestTone {
            frequency_hz: 440.0,
            amplitude_db: -12.0,
        },
    );
    let input_id = input.id;
    session.add_input(input).unwrap();
    let bus = Bus::new("Chosen mix");
    let bus_id = bus.id;
    session.add_bus(bus).unwrap();
    session.add_send(Send::new(input_id, bus_id)).unwrap();
    (session, bus_id)
}
fn render(session: &Session, bus: Uuid, channels: usize) -> RenderState {
    let shared = Arc::new(Shared {
        state: Mutex::new(ControlState::default()),
        epoch: AtomicU64::new(0),
    });
    RenderState::new(
        session,
        bus,
        channels,
        0,
        Arc::new(AtomicBool::new(true)),
        shared,
    )
    .unwrap()
}
fn config(
    channels: u16,
    format: cpal::SampleFormat,
    min: u32,
    max: u32,
) -> cpal::SupportedStreamConfigRange {
    cpal::SupportedStreamConfigRange::new(
        channels,
        min,
        max,
        cpal::SupportedBufferSize::Unknown,
        format,
    )
}

#[test]
fn creation_and_stop_never_open_a_device() {
    let runtime = AudioRuntime::new().unwrap();
    let first = runtime.snapshot();
    assert!(!first.running);
    assert_eq!(first.callback_count, 0);
    assert!(first.configuration.is_none());
    runtime.stop().unwrap();
    assert!(!runtime.snapshot().running);
}

#[test]
fn configuration_requires_exact_session_rate_and_stereo_pcm() {
    let choices = vec![
        config(1, cpal::SampleFormat::F32, 48000, 48000),
        config(8, cpal::SampleFormat::F32, 44100, 96000),
        config(2, cpal::SampleFormat::I16, 48000, 48000),
        config(2, cpal::SampleFormat::F32, 48000, 48000),
    ];
    let chosen = select_config(choices.into_iter(), 48000).unwrap();
    assert_eq!(chosen.channels(), 2);
    assert_eq!(chosen.sample_format(), cpal::SampleFormat::F32);
    assert_eq!(chosen.sample_rate(), 48000);
    assert!(select_config(
        vec![config(2, cpal::SampleFormat::F32, 44100, 44100)].into_iter(),
        48000
    )
    .is_none());
    assert!(select_config(
        vec![config(2, cpal::SampleFormat::DsdU8, 48000, 48000)].into_iter(),
        48000
    )
    .is_none());
}

#[test]
fn selected_bus_pcm_matches_independent_sine_across_chunks_and_callbacks() {
    let (mut session, bus) = session();
    session.sends[0].controls.set_gain_db(-6.0);
    session.buses[0].controls.set_gain_db(-3.0);
    session.buses[0].controls.pan = 0.75;
    let other = Bus::new("Unselected mix");
    let other_id = other.id;
    session.add_bus(other).unwrap();
    session
        .add_send(Send::new(session.inputs[0].id, other_id))
        .unwrap();
    let mut render = render(&session, bus, 8);
    let mut data = vec![99.0_f32; 5003 * 8];
    render.write(&mut data);
    for frame in 0..5003 {
        let expected = (frame as f64 * std::f64::consts::TAU * 440.0 / 48000.0).sin() as f32
            * 10.0_f32.powf(-21.0 / 20.0);
        assert!(
            (data[frame * 8] - expected * 0.25).abs() < 0.000002,
            "left frame {frame}"
        );
        assert!(
            (data[frame * 8 + 1] - expected).abs() < 0.000002,
            "right frame {frame}"
        );
        assert!(data[frame * 8 + 2..frame * 8 + 8].iter().all(|v| *v == 0.0));
    }
    let mut next = [0.0_f32; 8];
    render.write(&mut next);
    let expected = (5003.0_f64 * std::f64::consts::TAU * 440.0 / 48000.0).sin() as f32
        * 10.0_f32.powf(-21.0 / 20.0);
    assert!((next[1] - expected).abs() < 0.000002);
    assert_eq!(render.telemetry.frames.load(Ordering::Relaxed), 5004);
    assert_eq!(render.telemetry.callbacks.load(Ordering::Relaxed), 2);
    assert!(render.telemetry.buses[0].read(true).peak[1] > 0.0);
}

#[test]
fn callback_has_no_application_allocation_or_deallocation() {
    let (session, bus) = session();
    let mut render = render(&session, bus, 2);
    let mut data = vec![0_i16; 8192];
    OPERATIONS.with(|n| n.set(0));
    COUNTING.with(|on| on.set(true));
    for _ in 0..8 {
        render.write(&mut data);
    }
    COUNTING.with(|on| on.set(false));
    assert_eq!(OPERATIONS.with(Cell::get), 0);
    assert!(data.iter().any(|sample| *sample != 0));
}

#[test]
fn timed_out_or_stopped_start_cannot_emit_late_audio() {
    let (session, bus) = session();
    let mut cancelled = render(&session, bus, 2);
    cancelled.wanted.store(false, Ordering::Release);
    let mut data = [999_i16; 128];
    cancelled.write(&mut data);
    assert!(data.iter().all(|v| *v == 0));
    assert_eq!(cancelled.telemetry.frames.load(Ordering::Relaxed), 0);
    let mut stopped = render(&session, bus, 2);
    stopped.shared.epoch.fetch_add(1, Ordering::AcqRel);
    data.fill(999);
    stopped.write(&mut data);
    assert!(data.iter().all(|v| *v == 0));
}

#[test]
fn faults_are_latched_and_unsigned_silence_uses_midpoint() {
    let (session, bus) = session();
    let mut render = render(&session, bus, 2);
    render.telemetry.fail(AudioFault::DeviceUnavailable);
    render.telemetry.fail(AudioFault::Backend);
    let mut data = [0_u16; 128];
    render.write(&mut data);
    assert!(data.iter().all(|v| *v == 32768));
    assert_eq!(
        AudioFault::from_code(render.telemetry.fault.load(Ordering::Acquire)),
        AudioFault::DeviceUnavailable
    );
}

#[test]
fn invalid_callback_buffers_stop_without_partially_writing_pcm() {
    let (session, bus) = session();
    for len in [3, (MAX_CALLBACK_FRAMES + 1) * 2] {
        let mut render = render(&session, bus, 2);
        let mut data = vec![0.9_f32; len];
        render.write(&mut data);
        assert!(data.iter().all(|v| *v == 0.0));
        assert_eq!(
            AudioFault::from_code(render.telemetry.fault.load(Ordering::Acquire)),
            AudioFault::InvalidBuffer
        );
        assert_eq!(render.telemetry.frames.load(Ordering::Relaxed), 0);
    }
}

#[test]
fn native_transport_clamps_unlimited_float_mix_before_integer_conversion() {
    let (mut session, bus) = session();
    session.inputs[0].kind = InputKind::TestTone {
        frequency_hz: 12000.0,
        amplitude_db: 0.0,
    };
    session.buses[0].dsp = DspConfig::default();
    session.buses[0].controls.set_gain_db(24.0);
    let mut render = render(&session, bus, 2);
    let mut data = [0_i16; 8];
    render.write(&mut data);
    assert_eq!(data[2], i16::MAX);
    assert_eq!(data[6], i16::MIN);
    assert!(render.telemetry.buses[0].read(true).clipped_samples[0] >= 2);
}

#[test]
fn unavailable_capture_features_and_missing_mix_are_explicit_errors() {
    let (mut session, bus) = session();
    assert!(matches!(
        validate_session(&session, Uuid::new_v4()),
        Err(AudioError::InvalidSession(_))
    ));
    session.inputs[0].kind = InputKind::Hardware {
        device_id: "real-device".into(),
    };
    let error = validate_session(&session, bus).unwrap_err();
    assert!(error.to_string().contains("capture is not implemented"));
    let runtime = AudioRuntime::new().unwrap();
    assert!(matches!(
        runtime.start(session, bus, OutputId("must-not-be-queried".into())),
        Err(AudioError::InvalidSession(_))
    ));
    assert!(runtime.snapshot().configuration.is_none());
}

#[test]
fn stopped_snapshot_hides_stale_meter_levels_and_keeps_diagnostics() {
    let (session, bus) = session();
    let runtime = AudioRuntime::new().unwrap();
    let mut render = render(&session, bus, 2);
    render.write(&mut [0_f32; 256]);
    {
        let mut state = runtime.shared.state();
        state.running = true;
        state.telemetry = Some(render.telemetry.clone());
        state.authorization = Some((render.wanted.clone(), 0));
    }
    assert!(runtime.snapshot().bus_meters[0].peak[0] > 0.0);
    runtime.shared.epoch.fetch_add(1, Ordering::AcqRel);
    let stopped = runtime.snapshot();
    assert!(!stopped.running);
    assert_eq!(stopped.bus_meters[0].peak, [0.0; 2]);
    assert_eq!(stopped.rendered_frames, 128);
}
