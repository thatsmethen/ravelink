// Compile-only verification against the official Microsoft WDK/SDK declarations.
// This file is never linked into the Rust driver. It intentionally contains no
// driver implementation, dispatch code, or sample-driver dependencies.
#include <portcls.h>
#include <stddef.h>
#ifdef __clang__
#undef offsetof
#define offsetof(T, M) __builtin_offsetof(T, M)
#endif

template<typename Left, typename Right>
constexpr bool same_type = false;
template<typename Type>
constexpr bool same_type<Type, Type> = true;
template<typename Base, typename Derived>
constexpr bool is_base = __is_base_of(Base, Derived);

static_assert(sizeof(void*) == 8, "The Rust binding currently targets x64/arm64.");
static_assert(sizeof(KEVENT) == 24 && alignof(KEVENT) == 8);
static_assert(sizeof(DRIVER_OBJECT) == 336);
static_assert(offsetof(DRIVER_OBJECT, MajorFunction) == 112);
static_assert(offsetof(DEVICE_OBJECT, DeviceExtension) == 64);
static_assert(offsetof(IRP, CurrentLocation) == 67);
static_assert(offsetof(IRP, Tail.Overlay.CurrentStackLocation) == 184);
static_assert(offsetof(IO_STACK_LOCATION, MinorFunction) == 1);
static_assert(PORT_CLASS_DEVICE_EXTENSION_SIZE == 512);
static_assert(IRP_MJ_PNP == 0x1b && IRP_MJ_MAXIMUM_FUNCTION == 0x1b);
static_assert(IRP_MN_REMOVE_DEVICE == 2 && IRP_MN_STOP_DEVICE == 4 && IRP_MN_SURPRISE_REMOVAL == 0x17);
static_assert(sizeof(GUID) == 16 && alignof(GUID) == 4);
static_assert(sizeof(PHYSICAL_ADDRESS) == 8 && alignof(PHYSICAL_ADDRESS) == 8);
static_assert(sizeof(POWER_STATE) == 4);
static_assert(sizeof(UNICODE_STRING) == 16);
static_assert(offsetof(UNICODE_STRING, Buffer) == 8);
static_assert(sizeof(DEVICE_DESCRIPTION) == 64);
static_assert(offsetof(DEVICE_DESCRIPTION, DeviceAddress) == 56);
static_assert(sizeof(KSDATAFORMAT) == 64 && alignof(KSDATAFORMAT) == 8);
static_assert(offsetof(KSDATAFORMAT, MajorFormat) == 16);
static_assert(offsetof(KSDATAFORMAT, SubFormat) == 32);
static_assert(offsetof(KSDATAFORMAT, Specifier) == 48);
static_assert(sizeof(KSIDENTIFIER) == 24 && alignof(KSIDENTIFIER) == 8);
static_assert(sizeof(KSDATARANGE_AUDIO) == 88);
static_assert(offsetof(KSDATARANGE_AUDIO, MaximumChannels) == 64);
static_assert(offsetof(KSDATARANGE_AUDIO, MaximumSampleFrequency) == 80);
static_assert(sizeof(WAVEFORMATEX) == 18 && alignof(WAVEFORMATEX) == 1);
static_assert(sizeof(WAVEFORMATEXTENSIBLE) == 40 && alignof(WAVEFORMATEXTENSIBLE) == 1);
static_assert(offsetof(WAVEFORMATEXTENSIBLE, SubFormat) == 24);
static_assert(sizeof(KSDATAFORMAT_WAVEFORMATEX) == 82);
static_assert(sizeof(KSDATAFORMAT_WAVEFORMATEXTENSIBLE) == 104);
static_assert(offsetof(KSDATAFORMAT_WAVEFORMATEXTENSIBLE, WaveFormatExt) == 64);
static_assert(sizeof(KSPIN_DESCRIPTOR) == 88);
static_assert(offsetof(KSPIN_DESCRIPTOR, Reserved) == 72);
static_assert(offsetof(KSPIN_DESCRIPTOR, ConstrainedDataRanges) == 80);
static_assert(sizeof(PCPIN_DESCRIPTOR) == 112);
static_assert(offsetof(PCPIN_DESCRIPTOR, KsPinDescriptor) == 24);
static_assert(sizeof(PCNODE_DESCRIPTOR) == 32);
static_assert(offsetof(PCNODE_DESCRIPTOR, Type) == 16);
static_assert(sizeof(PCFILTER_DESCRIPTOR) == 80);
static_assert(offsetof(PCFILTER_DESCRIPTOR, Pins) == 24);
static_assert(offsetof(PCFILTER_DESCRIPTOR, Nodes) == 40);
static_assert(offsetof(PCFILTER_DESCRIPTOR, Connections) == 56);
static_assert(offsetof(PCFILTER_DESCRIPTOR, Categories) == 72);
static_assert(sizeof(PCCONNECTION_DESCRIPTOR) == 16);
static_assert(sizeof(PCAUTOMATION_TABLE) == 56);
static_assert(sizeof(PCPROPERTY_ITEM) == 24);
static_assert(sizeof(PCPROPERTY_REQUEST) == 72);
static_assert(offsetof(PCPROPERTY_REQUEST, PropertyItem) == 24);
static_assert(offsetof(PCPROPERTY_REQUEST, Irp) == 64);
static_assert(sizeof(KSAUDIO_POSITION) == 16);
static_assert(sizeof(KSRTAUDIO_HWLATENCY) == 12);
static_assert(sizeof(KSRTAUDIO_HWREGISTER) == 40);
static_assert(offsetof(KSRTAUDIO_HWREGISTER, Register) == 0);
static_assert(offsetof(KSRTAUDIO_HWREGISTER, Width) == 8);
static_assert(offsetof(KSRTAUDIO_HWREGISTER, Numerator) == 16);
static_assert(offsetof(KSRTAUDIO_HWREGISTER, Accuracy) == 32);
static_assert(sizeof(KSSTATE) == 4 && sizeof(MEMORY_CACHING_TYPE) == 4);
static_assert(KSSTATE_STOP == 0 && KSSTATE_ACQUIRE == 1 && KSSTATE_PAUSE == 2 && KSSTATE_RUN == 3);
static_assert(KSPIN_DATAFLOW_IN == 1 && KSPIN_DATAFLOW_OUT == 2);
static_assert(KSPIN_COMMUNICATION_NONE == 0 && KSPIN_COMMUNICATION_SINK == 1);
static_assert(MmCached == 1 && PCFILTER_NODE == ULONG(-1));
static_assert(PcRebalanceNotSupported == 0 && PcRebalanceRemoveSubdevices == 1);

// C++ cannot portably take offsetof of vtable slots. These assertions establish
// the inheritance and exact signatures; slot order is transcribed from portcls.h
// and separately asserted in the Rust layout test.
static_assert(is_base<IUnknown, IMiniport>);
static_assert(is_base<IMiniport, IMiniportWaveRT>);
static_assert(is_base<IMiniport, IMiniportTopology>);
static_assert(is_base<IPort, IPortWaveRT>);
static_assert(is_base<IPort, IPortTopology>);
static_assert(is_base<IUnknown, IPortWaveRTStream>);
static_assert(is_base<IUnknown, IMiniportWaveRTStream>);
static_assert(is_base<IUnknown, IAdapterPowerManagement>);
static_assert(is_base<IUnknown, IAdapterPnpManagement>);
static_assert(sizeof(IMiniportWaveRT) == sizeof(void*));
static_assert(sizeof(IMiniportWaveRTStream) == sizeof(void*));

#define METHOD(Interface, Name, Return, ...) \
    static_assert(same_type<decltype(&Interface::Name), \
        Return (STDMETHODCALLTYPE Interface::*)(__VA_ARGS__) noexcept> || \
        same_type<decltype(&Interface::Name), Return (STDMETHODCALLTYPE Interface::*)(__VA_ARGS__)>)

METHOD(IMiniport, QueryInterface, NTSTATUS, REFIID, PVOID*);
METHOD(IMiniport, AddRef, ULONG);
METHOD(IMiniport, Release, ULONG);
METHOD(IMiniport, GetDescription, NTSTATUS, PPCFILTER_DESCRIPTOR*);
METHOD(IMiniport, DataRangeIntersection, NTSTATUS, ULONG, PKSDATARANGE, PKSDATARANGE, ULONG, PVOID, PULONG);
METHOD(IMiniportWaveRT, Init, NTSTATUS, PUNKNOWN, PRESOURCELIST, PPORTWAVERT);
METHOD(IMiniportWaveRT, NewStream, NTSTATUS, PMINIPORTWAVERTSTREAM*, PPORTWAVERTSTREAM, ULONG, BOOLEAN, PKSDATAFORMAT);
METHOD(IMiniportWaveRT, GetDeviceDescription, NTSTATUS, PDEVICE_DESCRIPTION);
METHOD(IMiniportTopology, Init, NTSTATUS, PUNKNOWN, PRESOURCELIST, PPORTTOPOLOGY);
METHOD(IPort, Init, NTSTATUS, PDEVICE_OBJECT, PIRP, PUNKNOWN, PUNKNOWN, PRESOURCELIST);
METHOD(IPortWaveRTStream, AllocatePagesForMdl, PMDL, PHYSICAL_ADDRESS, SIZE_T);
METHOD(IPortWaveRTStream, AllocateContiguousPagesForMdl, PMDL, PHYSICAL_ADDRESS, PHYSICAL_ADDRESS, SIZE_T);
METHOD(IPortWaveRTStream, MapAllocatedPages, PVOID, PMDL, MEMORY_CACHING_TYPE);
METHOD(IPortWaveRTStream, UnmapAllocatedPages, VOID, PVOID, PMDL);
METHOD(IPortWaveRTStream, FreePagesFromMdl, VOID, PMDL);
METHOD(IPortWaveRTStream, GetPhysicalPagesCount, ULONG, PMDL);
METHOD(IPortWaveRTStream, GetPhysicalPageAddress, PHYSICAL_ADDRESS, PMDL, ULONG);
METHOD(IMiniportWaveRTStream, SetFormat, NTSTATUS, PKSDATAFORMAT);
METHOD(IMiniportWaveRTStream, SetState, NTSTATUS, KSSTATE);
METHOD(IMiniportWaveRTStream, GetPosition, NTSTATUS, PKSAUDIO_POSITION);
METHOD(IMiniportWaveRTStream, AllocateAudioBuffer, NTSTATUS, ULONG, PMDL*, PULONG, PULONG, MEMORY_CACHING_TYPE*);
METHOD(IMiniportWaveRTStream, FreeAudioBuffer, VOID, PMDL, ULONG);
METHOD(IMiniportWaveRTStream, GetHWLatency, VOID, KSRTAUDIO_HWLATENCY*);
METHOD(IMiniportWaveRTStream, GetPositionRegister, NTSTATUS, KSRTAUDIO_HWREGISTER*);
METHOD(IMiniportWaveRTStream, GetClockRegister, NTSTATUS, KSRTAUDIO_HWREGISTER*);
METHOD(IAdapterPowerManagement, PowerChangeState, VOID, POWER_STATE);
METHOD(IAdapterPowerManagement, QueryPowerChangeState, NTSTATUS, POWER_STATE);
METHOD(IAdapterPowerManagement, QueryDeviceCapabilities, NTSTATUS, PDEVICE_CAPABILITIES);
METHOD(IAdapterPnpManagement, GetSupportedRebalanceType, PC_REBALANCE_TYPE);
METHOD(IAdapterPnpManagement, PnpQueryStop, VOID);
METHOD(IAdapterPnpManagement, PnpCancelStop, VOID);
METHOD(IAdapterPnpManagement, PnpStop, VOID);
METHOD(IMiniportPnpNotify, PnpStop, VOID);
METHOD(IPortClsPnp, RegisterAdapterPnpManagement, NTSTATUS, PUNKNOWN, PDEVICE_OBJECT);
METHOD(IPortClsPnp, UnregisterAdapterPnpManagement, NTSTATUS, PDEVICE_OBJECT);
METHOD(IUnregisterSubdevice, UnregisterSubdevice, NTSTATUS, PDEVICE_OBJECT, PUNKNOWN);
METHOD(IUnregisterPhysicalConnection, UnregisterPhysicalConnection, NTSTATUS, PDEVICE_OBJECT, PUNKNOWN, ULONG, PUNKNOWN, ULONG);
METHOD(IUnregisterPhysicalConnection, UnregisterPhysicalConnectionToExternal, NTSTATUS, PDEVICE_OBJECT, PUNKNOWN, ULONG, PUNICODE_STRING, ULONG);
METHOD(IUnregisterPhysicalConnection, UnregisterPhysicalConnectionFromExternal, NTSTATUS, PDEVICE_OBJECT, PUNICODE_STRING, ULONG, PUNKNOWN, ULONG);
#undef METHOD

static_assert(same_type<PCPFNPROPERTY_HANDLER, NTSTATUS (*)(PPCPROPERTY_REQUEST)>);
static_assert(same_type<decltype(&PcAddAdapterDevice),
    NTSTATUS (NTAPI*)(PDRIVER_OBJECT, PDEVICE_OBJECT, PCPFNSTARTDEVICE, ULONG, ULONG)>);
static_assert(same_type<decltype(&PcRegisterPhysicalConnection),
    NTSTATUS (NTAPI*)(PDEVICE_OBJECT, PUNKNOWN, ULONG, PUNKNOWN, ULONG)>);
