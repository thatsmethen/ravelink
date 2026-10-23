//! Disposable-runner acceptance client of the real public AudioRuntime API.
//! No callback or product implementation is replaced by this instrument.

#[cfg(target_os = "macos")]
mod native {
    use ravelink_audio::{AudioFault, AudioRuntime, AudioSnapshot, OutputId};
    use ravelink_core::{Bus, DspConfig, Input, InputKind, Send, Session};
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
            })
        }
        fn event(&mut self, text: &str) -> Result<(), String> {
            writeln!(self.events, "{text}")
                .and_then(|_| self.events.flush())
                .map_err(|e| e.to_string())
        }
        fn snapshot(&mut self, runtime: &AudioRuntime) -> Result<AudioSnapshot, String> {
            let snapshot = runtime.snapshot();
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
        if input != "coreaudio:au.textual.ravelink.cable.1"
            || output != "coreaudio:au.textual.ravelink.cable.2"
        {
            return Err(
                "This fixed protocol requires distinct explicit Cable1 input and Cable2 output IDs"
                    .into(),
            );
        }
        let runtime = AudioRuntime::new().map_err(|e| e.to_string())?;
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
        let _stop = StopOnDrop(&runtime);
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
            let snapshot = evidence.snapshot(&runtime)?;
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
            evidence.snapshot(&runtime)?;
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
                let snapshot = evidence.snapshot(&runtime)?;
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
                evidence.snapshot(&runtime)?;
                thread::sleep(Duration::from_millis(20));
            }
        }
        let snapshot = evidence.snapshot(&runtime)?;
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
        #[test]
        fn report_strings_escape_control_characters() {
            assert_eq!(super::quoted("a\"\\\n\0"), "\"a\\\"\\\\\\u000a\\u0000\"");
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
