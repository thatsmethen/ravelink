//! Disposable-runner acceptance client of the real public AudioRuntime API.
//! No callback or product implementation is replaced by this instrument.

#[cfg(target_os = "macos")]
mod native {
    use ravelink_audio::{
        AudioFault, AudioRuntime, AudioSnapshot, NativeCallbackOutcome, NativeCapturePacket,
        NativeLifecyclePhase, NativeTimingSnapshot, OutputId,
    };
    use ravelink_core::{Bus, DspConfig, Input, InputKind, Send, Session};
    use serde_json::{json, Value};
    use std::{
        env,
        fs::{self, File, OpenOptions},
        io::{BufWriter, Write},
        path::{Path, PathBuf},
        thread,
        time::{Duration, Instant},
    };

    extern "C" {
        fn mach_absolute_time() -> u64;
    }
    fn ticks() -> u64 {
        unsafe { mach_absolute_time() }
    }
    fn quoted(value: &str) -> String {
        let mut out = String::from("\"");
        for character in value.chars() {
            match character {
                '\"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                c if c <= '\u{1f}' => out.push_str(&format!("\\u{:04x}", c as u32)),
                c => out.push(c),
            }
        }
        out.push('\"');
        out
    }
    fn packet_json(packet: NativeCapturePacket) -> Value {
        json!({
            "packet_index": packet.packet_index, "queue_frame": packet.queue_frame,
            "sample_time": packet.sample_time, "sample_time_bits": packet.sample_time.to_bits(),
            "host_time": packet.host_time, "observed_host_time": packet.observed_host_time,
            "rate_scalar": packet.rate_scalar, "rate_scalar_bits": packet.rate_scalar.to_bits(),
            "flags": packet.flags, "frames": packet.frames, "epoch": packet.epoch,
        })
    }
    fn timing_json(timing: NativeTimingSnapshot) -> Value {
        let completed = timing.last_completed_callback.map(|callback| {
            let outcome = match callback.outcome {
                NativeCallbackOutcome::Published => json!({"kind":"published"}),
                NativeCallbackOutcome::Cancelled => json!({"kind":"cancelled"}),
                NativeCallbackOutcome::Rejected(fault) => json!({"kind":"rejected", "fault": fault as u32}),
            };
            json!({
                "packet_index": callback.packet_index, "entry_host_time": callback.entry_host_time,
                "after_pcm_host_time": callback.after_pcm_host_time, "completion_host_time": callback.completion_host_time,
                "os_now_sample_time": callback.os_now_sample_time, "os_now_sample_time_bits": callback.os_now_sample_time.to_bits(),
                "os_now_host_time": callback.os_now_host_time, "os_now_flags": callback.os_now_flags, "outcome": outcome,
            })
        });
        let first_fault = timing.first_fault.map(|fault| json!({
            "fault": fault.fault as u32, "previous": fault.previous.map(packet_json), "current": packet_json(fault.current),
        }));
        let lifecycle: Vec<Value> = timing
            .lifecycle
            .into_iter()
            .flatten()
            .map(|event| {
                json!({
                    "phase": format!("{:?}", event.phase), "host_time": event.host_time,
                    "status": event.status, "callbacks_in_flight": event.callbacks_in_flight,
                })
            })
            .collect();
        json!({
            "packets_seen": timing.packets_seen, "last_packet": timing.last_packet.map(packet_json),
            "last_packet_contended": timing.last_packet_contended, "first_fault": first_fault,
            "last_completed_callback": completed, "callback_completion_contended": timing.callback_completion_contended,
            "lifecycle": lifecycle,
        })
    }
    fn native_shutdown_observed(snapshot: &AudioSnapshot) -> bool {
        !snapshot.captures.is_empty()
            && snapshot.captures.iter().all(|capture| {
                capture.native_timing.is_some_and(|timing| {
                    timing.lifecycle[NativeLifecyclePhase::OwnerCompleted as usize].is_some()
                        || timing.lifecycle[NativeLifecyclePhase::ContextRetained as usize]
                            .is_some()
                })
            })
    }
    fn write_new(path: &Path, text: &str) -> Result<(), String> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|e| e.to_string())?;
        file.write_all(text.as_bytes()).map_err(|e| e.to_string())
    }
    fn publish_ready(directory: &Path, snapshot: &AudioSnapshot) -> Result<(), String> {
        let temporary = directory.join("runtime.ready.pending");
        write_new(&temporary, &format!("{{\"ready\":true,\"host_time\":{},\"rendered_frames\":{},\"captured_frames\":{}}}\n",
            ticks(), snapshot.rendered_frames, snapshot.captures[0].captured_frames))?;
        fs::hard_link(&temporary, directory.join("runtime.ready.json"))
            .map_err(|e| e.to_string())?;
        fs::remove_file(temporary).map_err(|e| e.to_string())
    }
    struct Evidence {
        events: BufWriter<File>,
        telemetry: BufWriter<File>,
        native_timing: BufWriter<File>,
    }
    impl Evidence {
        fn new(directory: &Path) -> Result<Self, String> {
            let create = |name| {
                OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(directory.join(name))
                    .map_err(|e| e.to_string())
            };
            let mut telemetry = BufWriter::new(create("runtime-telemetry.csv")?);
            writeln!(telemetry, "host_time,rendered_frames,callback_count,applied_control_version,captured_frames,buffered_frames,clock_correction_ppm,fault,running").map_err(|e| e.to_string())?;
            Ok(Self {
                events: BufWriter::new(create("runtime-events.jsonl")?),
                telemetry,
                native_timing: BufWriter::new(create("runtime-native-timing.jsonl")?),
            })
        }
        fn event(&mut self, text: &str) -> Result<(), String> {
            writeln!(self.events, "{text}")
                .and_then(|_| self.events.flush())
                .map_err(|e| e.to_string())
        }
        fn snapshot(&mut self, runtime: &AudioRuntime) -> Result<AudioSnapshot, String> {
            let snapshot = runtime.snapshot();
            self.native_snapshot(&snapshot, "running", None)?;
            let capture = snapshot.captures.first();
            writeln!(
                self.telemetry,
                "{},{},{},{},{},{},{},{},{}",
                ticks(),
                snapshot.rendered_frames,
                snapshot.callback_count,
                snapshot.applied_control_version,
                capture.map_or(0, |c| c.captured_frames),
                capture.map_or(0, |c| c.buffered_frames),
                capture.map_or(0.0, |c| c.clock_correction_ppm),
                snapshot.fault as u32,
                u8::from(snapshot.running)
            )
            .and_then(|_| self.telemetry.flush())
            .map_err(|e| e.to_string())?;
            if snapshot.fault != AudioFault::None || snapshot.error.is_some() || !snapshot.running {
                return Err(format!(
                    "runtime stopped: fault={:?}, error={:?}",
                    snapshot.fault, snapshot.error
                ));
            }
            Ok(snapshot)
        }
        fn native_snapshot(
            &mut self,
            snapshot: &AudioSnapshot,
            observation: &str,
            shutdown_complete: Option<bool>,
        ) -> Result<(), String> {
            let captures: Vec<Value> = snapshot
                .captures
                .iter()
                .map(|capture| {
                    json!({
                        "input_id": capture.device.0, "captured_frames": capture.captured_frames,
                        "native_timing": capture.native_timing.map(timing_json),
                    })
                })
                .collect();
            let record = json!({"schema":1, "observation":observation, "observed_host_time":ticks(),
                "running":snapshot.running, "fault": snapshot.fault as u32,
                "error":snapshot.error.as_ref().map(ToString::to_string), "captures": captures,
                "native_shutdown_observed":shutdown_complete});
            writeln!(self.native_timing, "{record}")
                .and_then(|_| self.native_timing.flush())
                .map_err(|e| e.to_string())
        }
        fn observe_shutdown(&mut self, runtime: &AudioRuntime) -> Result<(), String> {
            // Diagnostics only: preserve every acceptance threshold and legacy
            // CSV row. Bound the added process lifetime even if an OS call hangs.
            let deadline = Instant::now() + Duration::from_secs(2);
            loop {
                let snapshot = runtime.snapshot();
                let completed = native_shutdown_observed(&snapshot);
                let final_observation =
                    completed || snapshot.captures.is_empty() || Instant::now() >= deadline;
                self.native_snapshot(
                    &snapshot,
                    if final_observation {
                        "post-stop-final"
                    } else {
                        "post-stop"
                    },
                    final_observation.then_some(completed),
                )?;
                if final_observation {
                    return Ok(());
                }
                thread::sleep(Duration::from_millis(10));
            }
        }
    }
    struct StopOnDrop<'a>(&'a AudioRuntime);
    impl Drop for StopOnDrop<'_> {
        fn drop(&mut self) {
            self.0.cancel_output();
            let _ = self.0.stop();
        }
    }
    fn execute(
        directory: &Path,
        input: &str,
        output: &str,
        evidence: &mut Evidence,
    ) -> Result<(), String> {
        let runtime = AudioRuntime::new().map_err(|e| e.to_string())?;
        let _stop = StopOnDrop(&runtime);
        let result = execute_active(&runtime, directory, input, output, evidence);
        if result.is_err() {
            runtime.cancel_output();
            // Cleanup is always attempted; the original failure remains the
            // result, while JSONL retains the last available native diagnostics.
            let _ = runtime.stop();
        }
        let diagnostics = evidence.observe_shutdown(&runtime);
        result.and(diagnostics)
    }
    fn execute_active(
        runtime: &AudioRuntime,
        directory: &Path,
        input: &str,
        output: &str,
        evidence: &mut Evidence,
    ) -> Result<(), String> {
        if input != "coreaudio:au.textual.ravelink.cable.1"
            || output != "coreaudio:au.textual.ravelink.cable.2"
        {
            return Err(
                "This fixed protocol requires distinct explicit Cable1 input and Cable2 output IDs"
                    .into(),
            );
        }
        let inputs = runtime
            .enumerate_input_devices()
            .map_err(|e| e.to_string())?;
        let outputs = runtime
            .enumerate_output_devices()
            .map_err(|e| e.to_string())?;
        if inputs.iter().filter(|d| d.id.0 == input).count() != 1
            || outputs.iter().filter(|d| d.id.0 == output).count() != 1
        {
            return Err("Explicit runtime device identities were absent or ambiguous; no default substitution".into());
        }
        let mut session = Session::new("Installed capture acceptance", 48_000);
        let source = session
            .add_input(Input::new(
                "Independent Cable1 source",
                InputKind::Hardware {
                    device_id: input.into(),
                },
            ))
            .map_err(|e| e.to_string())?;
        let mut bus = Bus::new("Measured Cable2 output");
        bus.dsp = DspConfig::default();
        let bus = session.add_bus(bus).map_err(|e| e.to_string())?;
        let mut send = Send::new(source, bus);
        send.controls.set_gain_db(-6.0);
        session.add_send(send).map_err(|e| e.to_string())?;
        let configuration = runtime
            .start(session.clone(), bus, OutputId(output.into()))
            .map_err(|e| e.to_string())?;
        if configuration.sample_rate != 48_000
            || configuration.device_channels != 2
            || configuration.inputs.len() != 1
            || configuration.inputs[0].device.id.0 != input
            || configuration.inputs[0].device_channels != 2
        {
            return Err(format!(
                "Unexpected native configuration: {configuration:?}"
            ));
        }
        evidence.event(&format!("{{\"event\":\"started\",\"host_time\":{},\"input_id\":{},\"output_id\":{},\"sample_rate\":48000,\"input_format\":{},\"output_format\":{}}}",
            ticks(), quoted(input), quoted(output), quoted(&configuration.inputs[0].sample_format), quoted(&configuration.sample_format)))?;
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            let snapshot = evidence.snapshot(runtime)?;
            if snapshot.rendered_frames >= 4096
                && snapshot.callback_count >= 2
                && snapshot.captures.len() == 1
                && snapshot.captures[0].captured_frames >= 4096
                && snapshot
                    .bus_meters
                    .iter()
                    .any(|m| m.rms.iter().all(|&r| r > 0.01))
            {
                publish_ready(directory, &snapshot)?;
                break;
            }
            if Instant::now() >= deadline {
                return Err(
                    "Real input/mix callbacks did not become ready within five seconds".into(),
                );
            }
            thread::sleep(Duration::from_millis(10));
        }
        let deadline = Instant::now() + Duration::from_secs(10);
        while !directory.join("runtime.go").exists() {
            evidence.snapshot(runtime)?;
            if Instant::now() >= deadline {
                return Err("Independent recorder did not arm the phase sequence".into());
            }
            thread::sleep(Duration::from_millis(10));
        }
        // Protocol constants. The independent analyzer repeats these values;
        // events provide timing and acknowledgement, never acceptance limits.
        for (phase, gain, muted, seconds) in [
            (0, -6.0, false, 6),
            (1, -12.0, false, 6),
            (2, -12.0, true, 4),
            (3, -6.0, false, 6),
        ] {
            session.sends[0].controls.set_gain_db(gain);
            session.sends[0].controls.muted = muted;
            let requested = ticks();
            let version = runtime
                .update_controls(session.clone())
                .map_err(|e| e.to_string())?;
            let deadline = Instant::now() + Duration::from_secs(2);
            let snapshot = loop {
                let snapshot = evidence.snapshot(runtime)?;
                if snapshot.applied_control_version == version {
                    break snapshot;
                }
                if snapshot.applied_control_version > version {
                    return Err("Unexpected control version overtook the phase".into());
                }
                if Instant::now() >= deadline {
                    return Err("Control version was not acknowledged by an output callback".into());
                }
                thread::sleep(Duration::from_millis(5));
            };
            let acknowledged = ticks();
            evidence.event(&format!("{{\"event\":\"phase\",\"phase\":{phase},\"gain_db\":{gain},\"muted\":{muted},\"requested_host_time\":{requested},\"acknowledged_host_time\":{acknowledged},\"version\":{version},\"rendered_frames\":{},\"callback_count\":{}}}",
                snapshot.rendered_frames, snapshot.callback_count))?;
            let end = Instant::now() + Duration::from_secs(seconds);
            while Instant::now() < end {
                evidence.snapshot(runtime)?;
                thread::sleep(Duration::from_millis(20));
            }
        }
        let snapshot = evidence.snapshot(runtime)?;
        let requested = ticks();
        runtime.stop().map_err(|e| e.to_string())?;
        evidence.event(&format!("{{\"event\":\"stopped\",\"requested_host_time\":{requested},\"returned_host_time\":{},\"rendered_frames\":{},\"callback_count\":{}}}", ticks(), snapshot.rendered_frames, snapshot.callback_count))?;
        Ok(())
    }
    pub fn main() -> Result<(), String> {
        if env::var("GITHUB_ACTIONS").as_deref() != Ok("true")
            || env::var("RUNNER_OS").as_deref() != Ok("macOS")
            || env::var("RAVELINK_RUNTIME_ACCEPTANCE").as_deref() != Ok("1")
        {
            return Err(
                "This audio probe runs only in the explicitly enabled disposable macOS CI protocol"
                    .into(),
            );
        }
        let mut input = None;
        let mut output = None;
        let mut directory = None;
        let mut args = env::args().skip(1);
        while let Some(key) = args.next() {
            let value = args.next().ok_or("Missing option value")?;
            match key.as_str() {
                "--input-id" => input = Some(value),
                "--output-id" => output = Some(value),
                "--directory" => directory = Some(PathBuf::from(value)),
                _ => return Err(format!("Unknown option {key}")),
            }
        }
        let directory = directory.ok_or("Missing --directory")?;
        let mut evidence = Evidence::new(&directory)?;
        let result = execute(
            &directory,
            &input.ok_or("Missing --input-id")?,
            &output.ok_or("Missing --output-id")?,
            &mut evidence,
        );
        let error = result.as_ref().err().map_or("null".into(), |e| quoted(e));
        write_new(
            &directory.join("runtime-result.json"),
            &format!(
                "{{\"schema\":1,\"pass\":{},\"error\":{error}}}\n",
                result.is_ok()
            ),
        )?;
        result
    }
    #[cfg(test)]
    mod tests {
        use super::*;
        use ravelink_audio::{
            CaptureSnapshot, InputId, NativeCallbackCompletion, NativeCaptureFault,
            NativeLifecycleEvent, NATIVE_LIFECYCLE_PHASES,
        };

        fn timing() -> NativeTimingSnapshot {
            let packet = NativeCapturePacket {
                packet_index: 2,
                queue_frame: 512,
                sample_time: 52024.0,
                host_time: u64::MAX - 8,
                observed_host_time: u64::MAX - 7,
                rate_scalar: 1.0,
                flags: 7,
                frames: 512,
                epoch: 9,
            };
            let previous = NativeCapturePacket {
                packet_index: 1,
                queue_frame: 0,
                sample_time: 50944.0,
                host_time: u64::MAX - 100,
                observed_host_time: u64::MAX - 90,
                ..packet
            };
            NativeTimingSnapshot {
                packets_seen: 2,
                last_packet: Some(packet),
                first_fault: Some(NativeCaptureFault {
                    fault: AudioFault::Xrun,
                    previous: Some(previous),
                    current: packet,
                }),
                last_packet_contended: false,
                last_completed_callback: Some(NativeCallbackCompletion {
                    packet_index: 2,
                    entry_host_time: u64::MAX - 7,
                    after_pcm_host_time: u64::MAX - 6,
                    completion_host_time: u64::MAX - 5,
                    os_now_sample_time: 52088.0,
                    os_now_host_time: u64::MAX - 4,
                    os_now_flags: 3,
                    outcome: NativeCallbackOutcome::Rejected(AudioFault::Xrun),
                }),
                callback_completion_contended: false,
                lifecycle: [None; NATIVE_LIFECYCLE_PHASES],
            }
        }
        #[test]
        fn report_strings_escape_control_characters() {
            assert_eq!(super::quoted("a\"\\\n\0"), "\"a\\\"\\\\\\u000a\\u0000\"");
        }

        #[test]
        fn native_json_keeps_fault_pair_large_ticks_and_nonfinite_float_bits() {
            let mut timing = timing();
            let nan_bits = 0x7ff8_0000_0000_1234;
            timing.last_packet.as_mut().unwrap().sample_time = f64::from_bits(nan_bits);
            timing.last_packet.as_mut().unwrap().rate_scalar = f64::NEG_INFINITY;
            timing
                .last_completed_callback
                .as_mut()
                .unwrap()
                .os_now_sample_time = -0.0;
            timing.lifecycle[NativeLifecyclePhase::DestroyReturned as usize] =
                Some(NativeLifecycleEvent {
                    phase: NativeLifecyclePhase::DestroyReturned,
                    host_time: u64::MAX,
                    status: Some(-2000),
                    callbacks_in_flight: Some(1),
                });
            timing.lifecycle[NativeLifecyclePhase::HandleCancelled as usize] =
                Some(NativeLifecycleEvent {
                    phase: NativeLifecyclePhase::HandleCancelled,
                    host_time: u64::MAX - 1,
                    status: None,
                    callbacks_in_flight: None,
                });
            let serialized = timing_json(timing).to_string();
            let parsed: Value = serde_json::from_str(&serialized).unwrap();
            assert_eq!(parsed["last_packet"]["sample_time"], Value::Null);
            assert_eq!(
                parsed["last_packet"]["sample_time_bits"].as_u64(),
                Some(nan_bits)
            );
            assert_eq!(parsed["last_packet"]["rate_scalar"], Value::Null);
            assert_eq!(
                parsed["last_packet"]["rate_scalar_bits"].as_u64(),
                Some(f64::NEG_INFINITY.to_bits())
            );
            assert_eq!(
                parsed["last_packet"]["host_time"].as_u64(),
                Some(u64::MAX - 8)
            );
            assert_eq!(parsed["first_fault"]["previous"]["sample_time"], 50944.0);
            assert_eq!(parsed["first_fault"]["current"]["sample_time"], 52024.0);
            assert_eq!(
                parsed["last_completed_callback"]["os_now_sample_time_bits"].as_u64(),
                Some((-0.0_f64).to_bits())
            );
            assert_eq!(
                parsed["last_completed_callback"]["outcome"]["fault"],
                AudioFault::Xrun as u32
            );
            assert_eq!(parsed["lifecycle"][0]["phase"], "HandleCancelled");
            assert_eq!(parsed["lifecycle"][0]["callbacks_in_flight"], Value::Null);
            assert_eq!(parsed["lifecycle"][1]["host_time"].as_u64(), Some(u64::MAX));
            assert_eq!(parsed["lifecycle"][1]["status"], -2000);
        }

        #[test]
        fn native_shutdown_observation_requires_an_explicit_terminal_phase() {
            let runtime = AudioRuntime::new().unwrap(); // No device discovery or open.
            let mut snapshot = runtime.snapshot();
            assert!(!native_shutdown_observed(&snapshot));
            snapshot.captures.push(CaptureSnapshot {
                device: InputId("synthetic".into()),
                captured_frames: 512,
                buffered_frames: 0,
                clock_correction_ppm: 0.0,
                native_timing: Some(timing()),
            });
            assert!(!native_shutdown_observed(&snapshot));
            let timing = snapshot.captures[0].native_timing.as_mut().unwrap();
            timing.lifecycle[NativeLifecyclePhase::StopReturned as usize] =
                Some(NativeLifecycleEvent {
                    phase: NativeLifecyclePhase::StopReturned,
                    host_time: 123,
                    status: Some(0),
                    callbacks_in_flight: Some(0),
                });
            assert!(!native_shutdown_observed(&snapshot));
            let timing = snapshot.captures[0].native_timing.as_mut().unwrap();
            timing.lifecycle[NativeLifecyclePhase::ContextRetained as usize] =
                Some(NativeLifecycleEvent {
                    phase: NativeLifecyclePhase::ContextRetained,
                    host_time: 456,
                    status: None,
                    callbacks_in_flight: Some(1),
                });
            assert!(native_shutdown_observed(&snapshot));
            snapshot.captures.push(CaptureSnapshot {
                device: InputId("second-synthetic".into()),
                captured_frames: 0,
                buffered_frames: 0,
                clock_correction_ppm: 0.0,
                native_timing: None,
            });
            assert!(!native_shutdown_observed(&snapshot));
        }
    }
}

fn main() {
    #[cfg(target_os = "macos")]
    if let Err(error) = native::main() {
        eprintln!("{error}");
        std::process::exit(1);
    }
    #[cfg(not(target_os = "macos"))]
    {
        eprintln!("This fixed acceptance client requires macOS CoreAudio");
        std::process::exit(1);
    }
}
