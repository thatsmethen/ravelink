use eframe::egui;
use ravelink_audio::{AudioRuntime, AudioSnapshot, OutputId, StartCancellation};
use ravelink_core::Session;
use std::{
    sync::{
        mpsc::{self, Receiver, SyncSender},
        Arc,
    },
    thread,
    time::Duration,
};
use uuid::Uuid;

pub enum Request {
    Refresh,
    Start(Session, Uuid, String),
    Update(Session),
    Stop,
}
#[derive(Clone, Copy)]
enum Operation {
    Refresh,
    Start,
    Update,
    Stop,
}
impl Request {
    fn operation(&self) -> Operation {
        match self {
            Self::Refresh => Operation::Refresh,
            Self::Start(..) => Operation::Start,
            Self::Update(_) => Operation::Update,
            Self::Stop => Operation::Stop,
        }
    }
}
struct Command {
    request: Request,
    cancellation: StartCancellation,
}
pub struct Device {
    pub id: String,
    pub name: String,
}
enum Event {
    Devices(Vec<Device>),
    Inputs(Vec<Device>),
    Snapshot(Box<AudioSnapshot>),
    Finished {
        operation: Operation,
        result: Result<Option<u64>, String>,
    },
}
pub struct AudioUi {
    commands: SyncSender<Command>,
    events: Receiver<Event>,
    runtime: Option<Arc<AudioRuntime>>,
    pub devices: Vec<Device>,
    pub inputs: Vec<Device>,
    pub busy: bool,
    pub error: Option<String>,
    snapshot: Option<AudioSnapshot>,
    updating: bool,
    pending_update: Option<Session>,
    wanted_version: u64,
    cancelled: bool,
    starting: bool,
    pending_operations: usize,
    cancellation: StartCancellation,
}
impl AudioUi {
    pub fn new(ctx: egui::Context) -> Self {
        let (commands, requests) = mpsc::sync_channel::<Command>(4);
        let (sender, events) = mpsc::sync_channel(8);
        let (runtime, mut error) = match AudioRuntime::new() {
            Ok(r) => (Some(Arc::new(r)), None),
            Err(e) => (None, Some(e.to_string())),
        };
        if let Some(owner) = runtime.clone() {
            let spawned = thread::Builder::new()
                .name("ravelink-ui-audio".into())
                .spawn(move || loop {
                    match requests.recv_timeout(Duration::from_millis(50)) {
                        Ok(Command {
                            request,
                            cancellation,
                        }) => {
                            let operation = request.operation();
                            let result = match request {
                                Request::Refresh => {
                                    owner.enumerate_output_devices().and_then(|devices| {
                                        let _ = sender.send(Event::Devices(
                                            devices
                                                .into_iter()
                                                .map(|d| Device {
                                                    id: d.id.0,
                                                    name: d.name,
                                                })
                                                .collect(),
                                        ));
                                        owner.enumerate_input_devices().map(|devices| {
                                            let _ = sender.send(Event::Inputs(
                                                devices
                                                    .into_iter()
                                                    .map(|d| Device {
                                                        id: d.id.0,
                                                        name: d.name,
                                                    })
                                                    .collect(),
                                            ));
                                            None
                                        })
                                    })
                                }
                                Request::Start(session, bus, output) => owner
                                    .start_cancellable(session, bus, OutputId(output), cancellation)
                                    .map(|_| None),
                                Request::Update(session) => {
                                    owner.update_controls(session).map(Some)
                                }
                                Request::Stop => owner.stop().map(|_| None),
                            }
                            .map_err(|e| e.to_string());
                            if matches!(operation, Operation::Update) && result.is_err() {
                                owner.cancel_output();
                            }
                            let _ = sender.send(Event::Snapshot(Box::new(owner.snapshot())));
                            if sender.send(Event::Finished { operation, result }).is_err() {
                                break;
                            }
                            ctx.request_repaint();
                        }
                        Err(mpsc::RecvTimeoutError::Timeout) => {
                            let snapshot = owner.snapshot();
                            if snapshot.running
                                || snapshot.error.is_some()
                                || snapshot.fault != ravelink_audio::AudioFault::None
                            {
                                let _ = sender.try_send(Event::Snapshot(Box::new(snapshot)));
                                ctx.request_repaint();
                            }
                        }
                        Err(mpsc::RecvTimeoutError::Disconnected) => {
                            owner.cancel_output();
                            let _ = owner.stop();
                            break;
                        }
                    }
                });
            if let Err(e) = spawned {
                error = Some(format!("Cannot create audio control worker: {e}"));
            }
        }
        let mut result = Self {
            commands,
            events,
            runtime,
            devices: vec![],
            inputs: vec![],
            busy: false,
            error,
            snapshot: None,
            updating: false,
            pending_update: None,
            wanted_version: 0,
            cancelled: false,
            starting: false,
            pending_operations: 0,
            cancellation: StartCancellation::default(),
        };
        if result.error.is_none() {
            result.send(Request::Refresh);
        }
        result
    }
    pub fn send(&mut self, request: Request) {
        let operation = request.operation();
        if matches!(operation, Operation::Stop) {
            // Cancel the queued start itself as well as active callback output.
            // Hardware-queued samples cannot be recalled.
            self.cancellation.cancel();
            if let Some(runtime) = &self.runtime {
                runtime.cancel_output();
            }
            self.cancelled = true;
            self.pending_update = None;
        }
        if matches!(operation, Operation::Start) {
            self.cancellation = StartCancellation::default();
            self.cancelled = false;
            self.wanted_version = 0;
        }
        match self.commands.try_send(Command {
            request,
            cancellation: self.cancellation.clone(),
        }) {
            Ok(()) => {
                if matches!(operation, Operation::Update) {
                    self.updating = true;
                } else {
                    self.pending_operations += 1;
                    self.busy = true;
                }
                if matches!(operation, Operation::Start) {
                    self.starting = true;
                }
                self.error = None;
            }
            Err(e) => self.error = Some(format!("Audio control unavailable: {e}")),
        }
    }
    pub fn queue_controls(&mut self, session: Session) {
        if self.running() {
            self.pending_update = Some(session);
        }
    }
    pub fn poll(&mut self) {
        while let Ok(event) = self.events.try_recv() {
            match event {
                Event::Devices(devices) => self.devices = devices,
                Event::Inputs(devices) => self.inputs = devices,
                Event::Snapshot(snapshot) => {
                    if !snapshot.running
                        && (snapshot.error.is_some()
                            || snapshot.fault != ravelink_audio::AudioFault::None)
                    {
                        self.pending_update = None;
                    }
                    if !self.cancelled {
                        if snapshot.fault != ravelink_audio::AudioFault::None {
                            self.error = Some(snapshot.fault.message().into());
                        }
                        if let Some(e) = &snapshot.error {
                            self.error = Some(e.to_string());
                        }
                    }
                    self.snapshot = Some(*snapshot);
                }
                Event::Finished { operation, result } => {
                    if matches!(operation, Operation::Update) {
                        self.updating = false;
                    } else {
                        self.pending_operations = self.pending_operations.saturating_sub(1);
                        self.busy = self.pending_operations > 0;
                    }
                    if matches!(operation, Operation::Start) {
                        self.starting = false;
                    }
                    match result {
                        Ok(Some(version)) => self.wanted_version = version,
                        Err(e) => {
                            if !self.cancelled
                                || matches!(operation, Operation::Stop | Operation::Refresh)
                            {
                                self.error = Some(e);
                            }
                            if matches!(operation, Operation::Update) {
                                self.pending_update = None;
                                self.cancelled = true;
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
        if !self.busy && !self.updating && self.running() {
            if let Some(session) = self.pending_update.take() {
                self.send(Request::Update(session));
            }
        }
    }
    pub fn running(&self) -> bool {
        !self.cancelled && self.snapshot.as_ref().is_some_and(|s| s.running)
    }
    pub fn can_stop(&self) -> bool {
        self.running() || (self.starting && !self.cancelled)
    }
    pub fn controls_pending(&self) -> bool {
        self.pending_update.is_some()
            || self.updating
            || (self.running()
                && self
                    .snapshot
                    .as_ref()
                    .is_some_and(|s| s.applied_control_version < self.wanted_version))
    }
    pub fn peak(&self) -> [f32; 2] {
        if !self.running() {
            return [0.0; 2];
        }
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
    pub fn input_peak(&self, id: Uuid) -> [f32; 2] {
        if !self.running() {
            return [0.0; 2];
        }
        self.snapshot
            .as_ref()
            .and_then(|s| s.input_meters.iter().find(|m| m.id == id))
            .map(|m| m.peak)
            .unwrap_or([0.0; 2])
    }
}
impl Drop for AudioUi {
    fn drop(&mut self) {
        self.cancellation.cancel();
        if let Some(r) = &self.runtime {
            r.cancel_output();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (AudioUi, Receiver<Command>, SyncSender<Event>) {
        let (commands, requests) = mpsc::sync_channel(4);
        let (sender, events) = mpsc::sync_channel(8);
        (
            AudioUi {
                commands,
                events,
                runtime: None,
                devices: vec![],
                inputs: vec![],
                busy: false,
                error: None,
                snapshot: None,
                updating: false,
                pending_update: None,
                wanted_version: 0,
                cancelled: false,
                starting: false,
                pending_operations: 0,
                cancellation: StartCancellation::default(),
            },
            requests,
            sender,
        )
    }

    #[test]
    fn stop_cancels_start_while_it_is_still_in_the_ui_queue() {
        let (mut ui, requests, events) = fixture();
        ui.send(Request::Start(
            Session::new("Queued", 48000),
            Uuid::new_v4(),
            "unused".into(),
        ));
        assert!(ui.can_stop());
        assert!(ui.busy);
        ui.send(Request::Stop);
        let start = requests.recv().unwrap();
        assert!(matches!(start.request, Request::Start(..)));
        assert!(start.cancellation.is_cancelled());
        assert!(!ui.can_stop());
        assert!(matches!(requests.recv().unwrap().request, Request::Stop));
        events
            .send(Event::Finished {
                operation: Operation::Start,
                result: Err("cancelled".into()),
            })
            .unwrap();
        ui.poll();
        assert!(ui.busy, "Stop is still waiting for resource cleanup");
        assert!(
            ui.error.is_none(),
            "Intentional cancellation is not a failure"
        );
        events
            .send(Event::Finished {
                operation: Operation::Stop,
                result: Ok(None),
            })
            .unwrap();
        ui.poll();
        assert!(!ui.busy);
        assert!(!ui.can_stop());
    }

    #[test]
    fn dropping_ui_cancels_an_undispatched_start() {
        let (mut ui, requests, _events) = fixture();
        ui.send(Request::Start(
            Session::new("Queued", 48000),
            Uuid::new_v4(),
            "unused".into(),
        ));
        drop(ui);
        assert!(requests.recv().unwrap().cancellation.is_cancelled());
    }
}
