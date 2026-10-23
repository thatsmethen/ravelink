use eframe::egui;
use ravelink_audio::{AudioRuntime, AudioSnapshot, OutputId};
use ravelink_core::Session;
use std::{
    sync::mpsc::{self, Receiver, SyncSender},
    thread,
    time::Duration,
};
use uuid::Uuid;

pub enum Request {
    Refresh,
    Start(Session, Uuid, String),
    Stop,
}
pub struct Device {
    pub id: String,
    pub name: String,
}
enum Event {
    Devices(Vec<Device>),
    Snapshot(Box<AudioSnapshot>),
    Finished(Result<(), String>),
}
pub struct AudioUi {
    commands: SyncSender<Request>,
    events: Receiver<Event>,
    pub devices: Vec<Device>,
    pub busy: bool,
    pub error: Option<String>,
    snapshot: Option<AudioSnapshot>,
}
impl AudioUi {
    pub fn new(ctx: egui::Context) -> Self {
        let (commands, requests) = mpsc::sync_channel(4);
        let (sender, events) = mpsc::sync_channel(8);
        thread::Builder::new()
            .name("ravelink-ui-audio".into())
            .spawn(move || {
                let runtime = match AudioRuntime::new() {
                    Ok(runtime) => runtime,
                    Err(e) => {
                        let _ = sender.send(Event::Finished(Err(e.to_string())));
                        ctx.request_repaint();
                        return;
                    }
                };
                loop {
                    match requests.recv_timeout(Duration::from_millis(50)) {
                        Ok(request) => {
                            let result = match request {
                                Request::Refresh => {
                                    runtime.enumerate_output_devices().map(|devices| {
                                        let devices = devices
                                            .into_iter()
                                            .map(|d| Device {
                                                id: d.id.0,
                                                name: d.name,
                                            })
                                            .collect();
                                        let _ = sender.send(Event::Devices(devices));
                                    })
                                }
                                Request::Start(session, bus, output) => {
                                    runtime.start(session, bus, OutputId(output)).map(|_| ())
                                }
                                Request::Stop => runtime.stop(),
                            }
                            .map_err(|e| e.to_string());
                            let _ = sender.send(Event::Snapshot(Box::new(runtime.snapshot())));
                            if sender.send(Event::Finished(result)).is_err() {
                                break;
                            }
                            ctx.request_repaint();
                        }
                        Err(mpsc::RecvTimeoutError::Timeout) => {
                            let snapshot = runtime.snapshot();
                            if snapshot.running || snapshot.error.is_some() {
                                let _ = sender.try_send(Event::Snapshot(Box::new(snapshot)));
                                ctx.request_repaint();
                            }
                        }
                        Err(mpsc::RecvTimeoutError::Disconnected) => {
                            let _ = runtime.stop();
                            break;
                        }
                    }
                }
            })
            .expect("create audio control thread");
        let mut result = Self {
            commands,
            events,
            devices: vec![],
            busy: false,
            error: None,
            snapshot: None,
        };
        result.send(Request::Refresh);
        result
    }
    pub fn send(&mut self, request: Request) {
        match self.commands.try_send(request) {
            Ok(()) => {
                self.busy = true;
                self.error = None;
            }
            Err(error) => self.error = Some(format!("Audio control unavailable: {error}")),
        }
    }
    pub fn poll(&mut self) {
        while let Ok(event) = self.events.try_recv() {
            match event {
                Event::Devices(devices) => self.devices = devices,
                Event::Snapshot(snapshot) => {
                    if snapshot.fault != ravelink_audio::AudioFault::None {
                        self.error = Some(snapshot.fault.message().to_string());
                    }
                    if let Some(error) = &snapshot.error {
                        self.error = Some(error.to_string());
                    }
                    self.snapshot = Some(*snapshot);
                }
                Event::Finished(result) => {
                    self.busy = false;
                    if let Err(error) = result {
                        self.error = Some(error);
                    }
                }
            }
        }
    }
    pub fn running(&self) -> bool {
        self.snapshot.as_ref().is_some_and(|s| s.running)
    }
    pub fn peak(&self) -> [f32; 2] {
        self.snapshot
            .as_ref()
            .and_then(|s| {
                s.configuration
                    .as_ref()
                    .and_then(|c| s.bus_meters.iter().find(|m| m.id == c.bus_id))
            })
            .map(|m| m.peak)
            .unwrap_or([0.0; 2])
    }
}
