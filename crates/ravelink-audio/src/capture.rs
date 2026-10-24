use super::capture_transport::{Consumer, Kernel, Producer, Ring, TransportError};
#[cfg(any(not(target_os = "macos"), test))]
use super::supported_pcm;
use super::{
    backend, native_host, AudioError, AudioFault, InputDevice, InputId, RunningInput, Shared,
    Telemetry, RENDER_CHUNK,
};
use cpal::traits::{DeviceTrait, HostTrait};
use ravelink_core::{InputKind, Session, Uuid};
use std::{
    collections::BTreeMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};

pub(crate) fn enumerate() -> Result<Vec<InputDevice>, AudioError> {
    let host = native_host()?;
    let mut inputs = Vec::new();
    for device in host
        .input_devices()
        .map_err(|e| backend("input discovery", None, e))?
    {
        let id = device
            .id()
            .map_err(|e| backend("input identity", None, e))?
            .to_string();
        let name = device
            .description()
            .map_err(|e| backend("input description", Some(id.clone()), e))?
            .name()
            .to_owned();
        inputs.push(InputDevice {
            id: InputId(id),
            name,
        });
    }
    inputs.sort_by(|a, b| a.name.cmp(&b.name).then_with(|| a.id.0.cmp(&b.id.0)));
    Ok(inputs)
}

pub(crate) fn source_groups(session: &Session) -> BTreeMap<String, Vec<Uuid>> {
    let mut groups: BTreeMap<String, Vec<Uuid>> = BTreeMap::new();
    for input in &session.inputs {
        let id = match &input.kind {
            InputKind::Hardware { device_id } => device_id,
            InputKind::Virtual { endpoint_id } => endpoint_id,
            _ => continue,
        };
        groups.entry(id.clone()).or_default().push(input.id);
    }
    groups
}
pub(crate) struct Selected {
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    device: cpal::Device,
    #[cfg(target_os = "macos")]
    native: super::native_capture::Selection,
    pub(crate) config: cpal::SupportedStreamConfig,
    pub(crate) configuration: RunningInput,
}
pub(crate) fn select(session: &Session, host: &cpal::Host) -> Result<Vec<Selected>, AudioError> {
    let mut selected = Vec::new();
    for (id, source_ids) in source_groups(session) {
        let native_id: cpal::DeviceId = id
            .parse()
            .map_err(|_| AudioError::InvalidInputId(id.clone()))?;
        let mut matching = None;
        for device in host
            .devices()
            .map_err(|e| backend("input discovery", None, e))?
        {
            if device
                .id()
                .map_err(|e| backend("input identity", None, e))?
                == native_id
            {
                matching = Some(device);
                break;
            }
        }
        let device = matching.ok_or_else(|| AudioError::InputUnavailable(InputId(id.clone())))?;
        let name = device
            .description()
            .map_err(|e| backend("input description", Some(id.clone()), e))?
            .name()
            .to_owned();
        #[cfg(target_os = "macos")]
        let native = super::native_capture::select(&id, session.sample_rate)?;
        #[cfg(target_os = "macos")]
        let config = native.configuration();
        #[cfg(not(target_os = "macos"))]
        let config = select_config(
            device
                .supported_input_configs()
                .map_err(|e| backend("input format discovery", Some(name.clone()), e))?,
            session.sample_rate,
        )
        .ok_or_else(|| AudioError::UnsupportedInputConfiguration {
            device: name.clone(),
            sample_rate: session.sample_rate,
        })?;
        let configuration = RunningInput {
            device: InputDevice {
                id: InputId(id),
                name,
            },
            source_ids,
            device_channels: config.channels(),
            sample_format: {
                #[cfg(target_os = "macos")]
                {
                    native.description()
                }
                #[cfg(not(target_os = "macos"))]
                {
                    config.sample_format().to_string()
                }
            },
        };
        selected.push(Selected {
            #[cfg(not(any(target_os = "windows", target_os = "macos")))]
            device,
            #[cfg(target_os = "macos")]
            native,
            config,
            configuration,
        });
    }
    Ok(selected)
}
#[cfg(any(not(target_os = "macos"), test))]
pub(crate) fn select_config(
    configs: impl Iterator<Item = cpal::SupportedStreamConfigRange>,
    sample_rate: u32,
) -> Option<cpal::SupportedStreamConfig> {
    configs
        .filter(|c| {
            (1..=super::MAX_DEVICE_CHANNELS).contains(&c.channels())
                && supported_pcm(c.sample_format())
                && native_encoding_supported(c.sample_format())
        })
        .filter_map(|c| c.try_with_sample_rate(sample_rate))
        .min_by_key(|c| {
            (
                match c.channels() {
                    2 => 0,
                    1 => 1,
                    _ => 2,
                },
                c.channels(),
                match c.sample_format() {
                    cpal::SampleFormat::F32 => 0,
                    cpal::SampleFormat::F64 => 1,
                    _ => 2,
                },
            )
        })
}

#[cfg(any(not(target_os = "macos"), test))]
fn native_encoding_supported(format: cpal::SampleFormat) -> bool {
    #[cfg(target_os = "windows")]
    {
        super::wasapi_packet::Encoding::from_cpal(format).is_some()
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = format;
        true
    }
}
#[cfg(target_os = "windows")]
pub(crate) type CaptureStream = super::wasapi_capture::WasapiCapture;
#[cfg(target_os = "macos")]
pub(crate) type CaptureStream = super::native_capture::NativeCapture;
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub(crate) type CaptureStream = cpal::Stream;

pub(crate) struct CaptureRender {
    pub(crate) source_ids: Vec<Uuid>,
    pub(crate) consumer: Consumer,
    pub(crate) left: Vec<f32>,
    pub(crate) right: Vec<f32>,
}
impl CaptureRender {
    pub(crate) fn new(source_ids: Vec<Uuid>, sample_rate: u32, kernel: Arc<Kernel>) -> Self {
        Self {
            source_ids,
            consumer: Consumer::new(Ring::new(), kernel, sample_rate),
            left: vec![0.0; RENDER_CHUNK],
            right: vec![0.0; RENDER_CHUNK],
        }
    }
}
pub(crate) fn bytes_per_capture() -> usize {
    Ring::bytes()
        + 2 * RENDER_CHUNK * std::mem::size_of::<f32>()
        + std::mem::size_of::<CaptureRender>()
}

pub(crate) struct CaptureState {
    producer: Producer,
    #[cfg(any(not(any(target_os = "windows", target_os = "macos")), test))]
    channels: usize,
    permit: CapturePermit,
}
#[derive(Clone)]
pub(crate) struct CapturePermit {
    epoch: u64,
    wanted: Arc<AtomicBool>,
    shared: Arc<Shared>,
    telemetry: Arc<Telemetry>,
}
impl CapturePermit {
    pub(crate) fn authorized(&self) -> bool {
        self.wanted.load(Ordering::Acquire)
            && self.shared.epoch.load(Ordering::Acquire) == self.epoch
            && self.telemetry.fault.load(Ordering::Acquire) == 0
    }
    pub(crate) fn fail(&self, fault: AudioFault) {
        self.telemetry.fail(fault);
    }
    #[cfg(target_os = "macos")]
    pub(crate) fn epoch(&self) -> u64 {
        self.epoch
    }
}
impl CaptureState {
    pub(crate) fn new(
        ring: Arc<Ring>,
        channels: usize,
        epoch: u64,
        wanted: Arc<AtomicBool>,
        shared: Arc<Shared>,
        telemetry: Arc<Telemetry>,
    ) -> Self {
        #[cfg(all(any(target_os = "windows", target_os = "macos"), not(test)))]
        let _ = channels;
        Self {
            producer: Producer::new(ring),
            #[cfg(any(not(any(target_os = "windows", target_os = "macos")), test))]
            channels,
            permit: CapturePermit {
                epoch,
                wanted,
                shared,
                telemetry,
            },
        }
    }
    pub(crate) fn authorized(&self) -> bool {
        self.permit.authorized()
    }
    #[cfg(any(not(target_os = "macos"), test))]
    pub(crate) fn fail(&self, fault: AudioFault) {
        self.permit.fail(fault);
    }
    #[cfg(target_os = "macos")]
    pub(crate) fn permit(&self) -> CapturePermit {
        self.permit.clone()
    }
    #[cfg(target_os = "macos")]
    pub(crate) fn ring(&self) -> Arc<Ring> {
        self.producer.ring.clone()
    }
    #[cfg(any(not(any(target_os = "windows", target_os = "macos")), test))]
    pub(crate) fn push<T: cpal::Sample>(&mut self, samples: &[T])
    where
        f32: cpal::FromSample<T>,
    {
        if !self.authorized() {
            return;
        }
        if let Err(error) = self.producer.push(samples, self.channels) {
            self.fail(fault(error));
        }
    }
    #[cfg(any(target_os = "windows", test))]
    pub(crate) fn push_frames(&mut self, frames: usize, read: impl FnMut(usize) -> [f32; 2]) {
        if !self.authorized() {
            return;
        }
        if let Err(error) = self.producer.push_frames(frames, read) {
            self.fail(fault(error));
        }
    }
    #[cfg(target_os = "macos")]
    pub(crate) fn push_native_frames(
        &mut self,
        frames: usize,
        read: impl FnMut(usize) -> [f32; 2],
    ) -> Result<bool, AudioFault> {
        if !self.authorized() {
            return Ok(false);
        }
        self.producer.push_frames(frames, read).map_err(fault)?;
        Ok(true)
    }
}
pub(crate) fn fault(error: TransportError) -> AudioFault {
    match error {
        TransportError::Underflow => AudioFault::CaptureUnderflow,
        TransportError::Overflow => AudioFault::CaptureOverflow,
        TransportError::InvalidBuffer => AudioFault::InvalidBuffer,
    }
}
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn make_typed<T: cpal::SizedSample>(
    selected: &Selected,
    mut state: CaptureState,
) -> Result<cpal::Stream, cpal::Error>
where
    f32: cpal::FromSample<T>,
{
    let telemetry = state.permit.telemetry.clone();
    selected.device.build_input_stream_raw(
        selected.config.config(),
        T::FORMAT,
        move |data, _| {
            if let Some(samples) = data.as_slice::<T>() {
                state.push(samples);
            } else {
                state.fail(AudioFault::InvalidBuffer);
            }
        },
        move |error| {
            telemetry.fail(super::stream_fault(error.kind()));
        },
        Some(super::COMMAND_TIMEOUT),
    )
}
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub(crate) fn make_stream(
    selected: &Selected,
    state: CaptureState,
) -> Result<cpal::Stream, AudioError> {
    macro_rules! build {
        ($t:ty) => {
            make_typed::<$t>(selected, state)
        };
    }
    let stream = match selected.config.sample_format() {
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
            return Err(AudioError::UnsupportedInputConfiguration {
                device: selected.configuration.device.name.clone(),
                sample_rate: selected.config.sample_rate(),
            })
        }
    };
    stream.map_err(|e| {
        backend(
            "input stream creation",
            Some(selected.configuration.device.name.clone()),
            e,
        )
    })
}

#[cfg(target_os = "windows")]
pub(crate) fn make_stream(
    selected: &Selected,
    state: CaptureState,
) -> Result<CaptureStream, AudioError> {
    CaptureStream::build(&selected.configuration, &selected.config, state)
}

#[cfg(target_os = "macos")]
pub(crate) fn make_stream(
    selected: &Selected,
    state: CaptureState,
) -> Result<CaptureStream, AudioError> {
    CaptureStream::build(&selected.native, state)
}
