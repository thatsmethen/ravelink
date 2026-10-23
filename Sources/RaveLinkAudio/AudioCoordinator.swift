import Foundation
import CoreAudio
import Combine
import AppKit
import AVFoundation
import RaveLinkCore
import RaveLinkRealtime

public struct AudioDeviceInfo: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let inputChannels: Int
    public let outputChannels: Int
    public let sampleRate: Double
    public let isVirtual: Bool
}
public struct AudioApplicationInfo: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
}
public struct AudioDiagnostics: Equatable, Sendable {
    public var capturedFrames: UInt64 = 0
    public var renderedFrames: UInt64 = 0
    public var droppedFrames: UInt64 = 0
    public var underrunFrames: UInt64 = 0
    public var oversizedBlocks: UInt64 = 0
}
public enum AudioRoutingError: LocalizedError {
    case configuration(String)
    case coreAudio(String, OSStatus)
    public var errorDescription: String? {
        switch self {
        case .configuration(let message): return message
        case .coreAudio(let operation, let status):
            let bytes = [24, 16, 8, 0].map { UInt8(truncatingIfNeeded: UInt32(bitPattern: status) >> $0) }
            let fourCC = bytes.allSatisfy { $0 >= 32 && $0 < 127 } ? " ('\(String(bytes: bytes, encoding: .ascii) ?? "" )')" : ""
            return "\(operation) failed: CoreAudio \(status)\(fourCC). Check that the device is connected and audio recording permission is allowed in System Settings → Privacy & Security."
        }
    }
}

private func checked(_ status: OSStatus, _ operation: String) throws {
    guard status == noErr else { throw AudioRoutingError.coreAudio(operation, status) }
}
private final class GraphCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    func check() throws {
        lock.lock(); let cancelled = self.cancelled; lock.unlock()
        if cancelled { throw CancellationError() }
    }
}
private enum Hardware {
    static let system = AudioObjectID(kAudioObjectSystemObject)
    static func address(_ selector: AudioObjectPropertySelector, _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> AudioObjectPropertyAddress {
        .init(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
    }
    static func ids(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> [AudioObjectID] {
        var addr = address(selector, scope), size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(object, &addr, 0, nil, &size) == noErr, size > 0 else { return [] }
        var result = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
        let status = result.withUnsafeMutableBytes { AudioObjectGetPropertyData(object, &addr, 0, nil, &size, $0.baseAddress!) }
        return status == noErr ? result : []
    }
    static func string(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
        var addr = address(selector), value: Unmanaged<CFString>?, size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &value) == noErr else { return nil }
        return value?.takeRetainedValue() as String?
    }
    static func isVirtual(_ object: AudioObjectID) -> Bool {
        var addr = address(kAudioDevicePropertyTransportType), value: UInt32 = 0, size = UInt32(MemoryLayout<UInt32>.size)
        guard AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &value) == noErr else { return false }
        return value == kAudioDeviceTransportTypeVirtual
    }
    static func rate(_ object: AudioObjectID) throws -> Double {
        var addr = address(kAudioDevicePropertyNominalSampleRate), result: Double = 0, size = UInt32(MemoryLayout<Double>.size)
        try checked(AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &result), "Read device sample rate")
        guard result.isFinite, result >= 8000 else { throw AudioRoutingError.configuration("The selected device reports an unsupported sample rate.") }
        return result
    }
    static func channels(_ object: AudioObjectID, _ scope: AudioObjectPropertyScope) -> Int {
        var addr = address(kAudioDevicePropertyStreamConfiguration, scope), size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(object, &addr, 0, nil, &size) == noErr, size >= MemoryLayout<AudioBufferList>.size else { return 0 }
        let memory = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { memory.deallocate() }
        guard AudioObjectGetPropertyData(object, &addr, 0, nil, &size, memory) == noErr else { return 0 }
        return UnsafeMutableAudioBufferListPointer(memory.assumingMemoryBound(to: AudioBufferList.self)).reduce(0) { $0 + Int($1.mNumberChannels) }
    }
    static func devices() -> [(AudioObjectID, AudioDeviceInfo)] {
        ids(system, kAudioHardwarePropertyDevices).compactMap { object in
            guard let uid = string(object, kAudioDevicePropertyDeviceUID), !uid.hasPrefix("au.textual.ravelink.tap.") else { return nil }
            return (object, AudioDeviceInfo(id: uid, name: string(object, kAudioObjectPropertyName) ?? uid,
                inputChannels: channels(object, kAudioObjectPropertyScopeInput), outputChannels: channels(object, kAudioObjectPropertyScopeOutput), sampleRate: (try? rate(object)) ?? 0, isVirtual: isVirtual(object)))
        }
    }
    static func validateFloatStreams(_ object: AudioObjectID, scope: AudioObjectPropertyScope) throws {
        let streams = ids(object, kAudioDevicePropertyStreams, scope)
        guard !streams.isEmpty else { throw AudioRoutingError.configuration("The selected device has no audio streams in the requested direction.") }
        for stream in streams {
            var addr = address(kAudioStreamPropertyVirtualFormat), format = AudioStreamBasicDescription(), size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
            try checked(AudioObjectGetPropertyData(stream, &addr, 0, nil, &size, &format), "Read stream format")
            guard format.mFormatID == kAudioFormatLinearPCM, format.mFormatFlags & kAudioFormatFlagIsFloat != 0,
                  format.mBitsPerChannel == 32, format.mFormatFlags & kAudioFormatFlagIsBigEndian == 0,
                  format.mFormatFlags & kAudioFormatFlagIsPacked != 0,
                  format.mFramesPerPacket == 1,
                  format.mBytesPerFrame == 4 * (format.mFormatFlags & kAudioFormatFlagIsNonInterleaved != 0 ? 1 : format.mChannelsPerFrame),
                  format.mBytesPerPacket == format.mBytesPerFrame,
                  abs(format.mSampleRate - (try rate(object))) < 0.01 else {
                throw AudioRoutingError.configuration("This device does not expose native Float32 audio. Select a CoreAudio Float32 device or an aggregate device in Audio MIDI Setup.")
            }
        }
    }
    static func processPID(_ object: AudioObjectID) -> pid_t? {
        var addr = address(kAudioProcessPropertyPID), value: pid_t = 0, size = UInt32(MemoryLayout<pid_t>.size)
        return AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &value) == noErr ? value : nil
    }
    static func processes() -> [(id: AudioObjectID, bundle: String, pid: pid_t)] {
        ids(system, kAudioHardwarePropertyProcessObjectList).compactMap {
            guard let pid = processPID($0) else { return nil }
            return ($0, string($0, kAudioProcessPropertyBundleID) ?? "", pid)
        }
    }
    static func ownProcess() -> AudioObjectID? {
        var addr = address(kAudioHardwarePropertyTranslatePIDToProcessObject), pid = getpid(), value: AudioObjectID = 0, size = UInt32(MemoryLayout<AudioObjectID>.size)
        guard AudioObjectGetPropertyData(system, &addr, UInt32(MemoryLayout<pid_t>.size), &pid, &size, &value) == noErr, value != 0 else { return nil }
        return value
    }
    static func applications() -> [AudioApplicationInfo] {
        var names: [String: String] = [:]
        for p in processes() where p.pid != getpid() && !p.bundle.isEmpty {
            names[p.bundle] = NSRunningApplication(processIdentifier: p.pid)?.localizedName ?? p.bundle
        }
        return names.map { AudioApplicationInfo(id: $0.key, name: $0.value) }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }
}

/// Owns an IOProc and, optionally, the private tap and aggregate that feed it.
/// Destroy order is stop → unregister callback → destroy aggregate → destroy tap.
private final class CaptureNode {
    let channelID: UUID
    let device: AudioObjectID
    let rate: Double
    let context: OpaquePointer
    var proc: AudioDeviceIOProcID?
    var tap: AudioObjectID = 0
    var tapDescription: CATapDescription?
    var aggregate: AudioObjectID = 0
    var started = false
    var abandoned = false
    init(channelID: UUID, device: AudioObjectID, rate: Double, context: OpaquePointer) {
        self.channelID = channelID; self.device = device; self.rate = rate; self.context = context
    }
    func start() throws {
        try checked(AudioDeviceCreateIOProcID(device, rl_capture_io_proc(), UnsafeMutableRawPointer(context), &proc), "Create input callback")
        try checked(AudioDeviceStart(device, proc), "Start input")
        started = true
    }
    @discardableResult func stop() -> Bool {
        if let proc {
            if started { _ = AudioDeviceStop(device, proc) }
            // A successful unregister is the boundary after which C memory can
            // be released. On failure, retain its storage until process exit.
            guard AudioDeviceDestroyIOProcID(device, proc) == noErr else { return false }
        }
        proc = nil; started = false
        return true
    }
    deinit {
        guard !abandoned, stop() else { return }
        if aggregate != 0 { AudioHardwareDestroyAggregateDevice(aggregate) }
        if tap != 0 { AudioHardwareDestroyProcessTap(tap) }
        rl_capture_destroy(context)
    }
}
private final class OutputNode {
    let device: AudioObjectID
    let uid: String
    let rate: Double
    let buses: [UUID]
    let context: OpaquePointer
    var proc: AudioDeviceIOProcID?
    var started = false
    var abandoned = false
    init(device: AudioObjectID, uid: String, rate: Double, buses: [UUID], context: OpaquePointer) {
        self.device = device; self.uid = uid; self.rate = rate; self.buses = buses; self.context = context
    }
    func prepare() throws {
        if proc == nil { try checked(AudioDeviceCreateIOProcID(device, rl_render_io_proc(), UnsafeMutableRawPointer(context), &proc), "Create output callback") }
    }
    func start() throws {
        try prepare()
        try checked(AudioDeviceStart(device, proc), "Start output")
        started = true
    }
    @discardableResult func stop() -> Bool {
        if let proc {
            if started { _ = AudioDeviceStop(device, proc) }
            guard AudioDeviceDestroyIOProcID(device, proc) == noErr else { return false }
        }
        proc = nil; started = false
        return true
    }
    deinit { if !abandoned, stop() { rl_render_destroy(context) } }
}
// Ownership transfers worker → main only after configure finishes; it transfers
// back before stop. Live control/meter access touches only lock-free C atomics.
private final class AudioGraph: @unchecked Sendable {
    var captures: [CaptureNode] = []
    var outputs: [OutputNode] = []
    var rings: [OpaquePointer] = []
    var session: MixerSession
    let channelParents: [UUID: UUID]
    var applicationProcesses: [String: [AudioObjectID]] = [:]
    static let maxFrames: UInt32 = 16384
    init(session: MixerSession, channelParents: [UUID: UUID]) { self.session = session; self.channelParents = channelParents }
    @discardableResult func stop() -> String? {
        var safe = true
        for capture in captures { if !capture.stop() { safe = false } }
        for output in outputs { if !output.stop() { safe = false } }
        if !safe {
            // Do not free any graph memory that a misbehaving driver might still
            // reference. This exceptional quarantine intentionally lasts until exit.
            captures.forEach { $0.abandoned = true }; outputs.forEach { $0.abandoned = true }
            captures.removeAll(); outputs.removeAll(); rings.removeAll()
            return "The audio driver failed to release an active callback. Quit RaveLink now to release audio safely before continuing."
        }
        captures.removeAll(); outputs.removeAll()
        rings.forEach(rl_ring_destroy); rings.removeAll()
        return nil
    }
    deinit { stop() }
    func silence() {
        for output in outputs {
            for (index, _) in output.buses.enumerated() { rl_render_bus_controls(output.context, UInt32(index), 0, true) }
        }
    }
    static func sameTopology(_ a: MixerSession, _ b: MixerSession) -> Bool {
        a.channels.map(\.id) == b.channels.map(\.id) && a.channels.map(\.source) == b.channels.map(\.source)
        && a.buses.map(\.id) == b.buses.map(\.id) && a.buses.map(\.deviceUID) == b.buses.map(\.deviceUID)
        && a.buses.map(\.channelOffset) == b.buses.map(\.channelOffset)
    }
    func controls(_ session: MixerSession) {
        let anySolo = session.channels.contains { $0.solo }
        let sendsByChannel = Dictionary(grouping: session.sends, by: \.channelID).mapValues {
            Dictionary(uniqueKeysWithValues: $0.map { ($0.busID, $0) })
        }
        let busesByID = Dictionary(uniqueKeysWithValues: session.buses.map { ($0.id, $0) })
        for capture in captures {
            // Effects are applied after grouped sources have been summed at each
            // destination rate. Capture remains raw to avoid per-source compression.
            rl_capture_controls(capture.context, 0, 0, -80, 0, 1)
        }
        for output in outputs {
            for (i, channel) in session.channels.enumerated() {
                let fx = channel.effects
                rl_render_source_controls(output.context, UInt32(i), !channel.muted && (!anySolo || channel.solo), fx.gainDB, fx.highPassHz, fx.gateThresholdDB, fx.compressorThresholdDB, fx.compressorRatio)
                for (b, busID) in output.buses.enumerated() {
                    let send = sendsByChannel[channel.id]?[busID]
                    rl_render_send_controls(output.context, UInt32(i), UInt32(b), send?.gainDB ?? 0, send?.pan ?? 0, send?.muted ?? true)
                }
            }
            for (b, id) in output.buses.enumerated() {
                guard let bus = busesByID[id] else { continue }
                rl_render_bus_controls(output.context, UInt32(b), bus.gainDB, bus.muted)
            }
        }
        self.session = session
    }
    func configure(cancellation: GraphCancellation) throws {
        try cancellation.check()
        var allocation = AudioAllocationBudget()
        guard session.channels.count <= UInt32.max, session.buses.count <= UInt32.max else { throw AudioRoutingError.configuration("This graph has too many nodes for the audio device API.") }
        let available = Dictionary(uniqueKeysWithValues: Hardware.devices().map { ($0.1.id, ($0.0, $0.1)) })
        let assigned = session.buses.filter { $0.deviceUID != nil }
        guard !session.channels.isEmpty else { throw AudioRoutingError.configuration("Add an input channel before starting audio.") }
        guard !assigned.isEmpty else { throw AudioRoutingError.configuration("Choose an output device on at least one mix bus before starting audio.") }
        // Bound memory by machine resources, rather than imposing a product channel limit.
        let outputGroups = Dictionary(grouping: assigned, by: { $0.deviceUID! })
        for uid in outputGroups.keys.sorted() {
            try cancellation.check()
            guard let (device, info) = available[uid], let buses = outputGroups[uid] else { throw AudioRoutingError.configuration("An output device is disconnected. Select an available device on each assigned mix bus.") }
            for bus in buses {
                guard bus.channelOffset >= 0, bus.channelOffset + 1 < info.outputChannels else { throw AudioRoutingError.configuration("\(bus.name): \(info.name) does not provide the requested stereo output pair.") }
            }
            try Hardware.validateFloatStreams(device, scope: kAudioObjectPropertyScopeOutput)
            let rate = try Hardware.rate(device)
            try allocation.reserve(try AudioAllocationBudget.output(sources: session.channels.count, buses: buses.count, frames: Self.maxFrames))
            guard let context = rl_render_create(rate, Self.maxFrames, UInt32(session.channels.count), UInt32(buses.count)) else { throw AudioRoutingError.configuration("Not enough memory to prepare this mix. Reduce channels or mix buses.") }
            let output = OutputNode(device: device, uid: uid, rate: rate, buses: buses.map(\.id), context: context)
            outputs.append(output)
            for (index, bus) in buses.enumerated() { rl_render_set_bus(context, UInt32(index), UInt32(bus.channelOffset)) }
            try output.prepare() // Registers our audio process before creating an exclusion tap.
            try cancellation.check()
        }
        for (index, channel) in session.channels.enumerated() {
            try cancellation.check()
            if channel.source.kind == .tone {
                for output in outputs { rl_render_set_source(output.context, UInt32(index), nil, output.rate, true) }
                continue
            }
            var device: AudioObjectID = 0, tap: AudioObjectID = 0, aggregate: AudioObjectID = 0
            var tapDescription: CATapDescription?
            do {
                if channel.source.kind == .device {
                    guard let uid = channel.source.deviceUID, let (id, info) = available[uid] else { throw AudioRoutingError.configuration("\(channel.name): choose an available input device.") }
                    guard channel.source.channelOffset >= 0, channel.source.channelOffset < info.inputChannels else { throw AudioRoutingError.configuration("\(channel.name): the selected input channel does not exist on \(info.name).") }
                    device = id
                } else {
                    let processes = Hardware.processes()
                    let description: CATapDescription
                    if channel.source.kind == .application {
                        guard let bundle = channel.source.bundleID, !bundle.isEmpty else { throw AudioRoutingError.configuration("\(channel.name): choose an application to capture.") }
                        let ids = processes.filter { $0.bundle == bundle && $0.pid != getpid() }.map(\.id)
                        guard !ids.isEmpty else { throw AudioRoutingError.configuration("\(channel.name): open the selected application and play audio before starting capture.") }
                        applicationProcesses[bundle] = ids.sorted()
                        description = CATapDescription(stereoMixdownOfProcesses: ids)
                    } else {
                        guard let own = Hardware.ownProcess() else { throw AudioRoutingError.configuration("CoreAudio could not identify RaveLink's audio process. Restart RaveLink before using system audio capture.") }
                        let dedicated = Set(session.channels.filter { $0.source.kind == .application }.compactMap { $0.source.bundleID })
                        let excluded = Set(processes.filter { $0.pid == getpid() || dedicated.contains($0.bundle) }.map(\.id) + [own])
                        description = CATapDescription(stereoGlobalTapButExcludeProcesses: Array(excluded))
                    }
                    description.name = "RaveLink — \(channel.name)"
                    description.isPrivate = true
                    // Preparation must never suppress another app. Playback is
                    // suppressed only after the main actor accepts this generation.
                    description.muteBehavior = .unmuted
                    tapDescription = description
                    try checked(AudioHardwareCreateProcessTap(description, &tap), "Create application audio tap")
                    let composition: [String: Any] = [
                        kAudioAggregateDeviceNameKey: "RaveLink private capture",
                        kAudioAggregateDeviceUIDKey: "au.textual.ravelink.tap.\(UUID().uuidString)",
                        kAudioAggregateDeviceIsPrivateKey: true,
                        kAudioAggregateDeviceTapAutoStartKey: false,
                        kAudioAggregateDeviceTapListKey: [[kAudioSubTapUIDKey: description.uuid.uuidString, kAudioSubTapDriftCompensationKey: true]]
                    ]
                    try checked(AudioHardwareCreateAggregateDevice(composition as CFDictionary, &aggregate), "Create private capture aggregate")
                    device = aggregate
                }
                try Hardware.validateFloatStreams(device, scope: kAudioObjectPropertyScopeInput)
                let rate = try Hardware.rate(device)
                try allocation.reserve(UInt64(Self.maxFrames) * 8 + UInt64(outputs.count) * 8 + 4096)
                guard let context = rl_capture_create(rate, UInt32(channel.source.kind == .device ? channel.source.channelOffset : 0), Self.maxFrames, UInt32(outputs.count)) else { throw AudioRoutingError.configuration("Not enough memory to prepare the input channel.") }
                let capture = CaptureNode(channelID: channel.id, device: device, rate: rate, context: context)
                capture.tap = tap; capture.aggregate = aggregate; tap = 0; aggregate = 0
                capture.tapDescription = tapDescription
                captures.append(capture)
                for (outputIndex, output) in outputs.enumerated() {
                    let ringPlan = try AudioAllocationBudget.ring(ratio: rate / output.rate, frames: Self.maxFrames)
                    try allocation.reserve(ringPlan.bytes)
                    guard let ring = rl_ring_create(ringPlan.capacity) else { throw AudioRoutingError.configuration("Not enough memory to prepare audio buffers.") }
                    rings.append(ring)
                    guard rl_ring_prepare_ratio(ring, rate / output.rate) else { throw AudioRoutingError.configuration("The input and output sample rates are too far apart. Choose rates between 8 kHz and 192 kHz in Audio MIDI Setup.") }
                    rl_capture_set_destination(context, UInt32(outputIndex), ring)
                    rl_render_set_source(output.context, UInt32(index), ring, rate, false)
                }
            } catch {
                if aggregate != 0 { AudioHardwareDestroyAggregateDevice(aggregate) }
                if tap != 0 { AudioHardwareDestroyProcessTap(tap) }
                throw error
            }
        }
        let indexes = Dictionary(uniqueKeysWithValues: session.channels.enumerated().map { ($0.element.id, $0.offset) })
        for output in outputs {
            for (index, channel) in session.channels.enumerated() {
                let parent = channelParents[channel.id] ?? channel.id
                guard let leader = indexes[parent] else { throw AudioRoutingError.configuration("An input group is missing its primary source.") }
                guard rl_render_set_source_group(output.context, UInt32(index), UInt32(leader)) else { throw AudioRoutingError.configuration("An input group has an invalid source ordering.") }
            }
        }
        controls(session)
        // Prepare/start a silent candidate. A stale or cancelled generation can
        // never broadcast old mix settings after a delayed HAL call returns.
        for output in outputs {
            for (index, _) in output.buses.enumerated() { rl_render_bus_controls(output.context, UInt32(index), 0, true) }
        }
        // All objects are configured before any device callbacks can run.
        for capture in captures { try cancellation.check(); try capture.start() }
        for output in outputs { try cancellation.check(); try output.start() }
        try cancellation.check()
    }
    func activateTaps(cancellation: GraphCancellation) throws {
        for capture in captures {
            try cancellation.check()
            guard let description = capture.tapDescription else { continue }
            description.muteBehavior = .mutedWhenTapped
            var reference = Unmanaged.passUnretained(description)
            var address = Hardware.address(kAudioTapPropertyDescription)
            try checked(AudioObjectSetPropertyData(capture.tap, &address, 0, nil, UInt32(MemoryLayout.size(ofValue: reference)), &reference), "Activate application monitoring")
            try cancellation.check()
        }
    }
}

@MainActor public final class AudioCoordinator: ObservableObject {
    @Published public private(set) var devices: [AudioDeviceInfo] = []
    @Published public private(set) var applications: [AudioApplicationInfo] = []
    @Published public private(set) var running = false
    @Published public private(set) var starting = false
    @Published public private(set) var errorMessage: String?
    @Published public private(set) var channelMeters: [UUID: Float] = [:]
    @Published public private(set) var busMeters: [UUID: Float] = [:]
    @Published public private(set) var diagnostics = AudioDiagnostics()
    private var graph: AudioGraph?
    private var routing: ExpandedRouting?
    private var timer: Timer?
    private var ticks = 0
    private let worker = DispatchQueue(label: "au.textual.ravelink.audio-control", qos: .userInitiated)
    private var generation: UInt64 = 0
    private var refreshing = false
    private var workerTimedOut = false
    private var pendingStart: GraphCancellation?

    public init() {
        refreshDevices()
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.poll() }
        }
    }
    deinit { timer?.invalidate(); if let graph { worker.async { graph.stop() } } }
    public func refreshDevices() {
        guard !refreshing, !workerTimedOut else { return }
        refreshing = true
        worker.async { [weak self] in
            let devices = Hardware.devices().map(\.1).sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
            let apps = Hardware.applications()
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.devices = devices; self.applications = apps; self.refreshing = false
            }
        }
    }
    public func start(session: MixerSession) throws {
        guard !workerTimedOut else { throw AudioRoutingError.configuration("The audio driver stopped responding. Quit and reopen RaveLink before starting another route.") }
        stop()
        do {
            let expanded = try session.expandedRouting()
            let routed = expanded.session
            try validateFeedback(routed)
            guard !routed.channels.isEmpty else { throw AudioRoutingError.configuration("Add an input channel before starting audio.") }
            guard routed.buses.contains(where: { $0.deviceUID != nil }) else { throw AudioRoutingError.configuration("Choose an output device on at least one mix bus before starting audio.") }
            let virtualIDs = Set(devices.filter(\.isVirtual).map(\.id))
            if routed.channels.contains(where: { $0.source.kind == .device && !virtualIDs.contains($0.source.deviceUID ?? "") }) {
                switch AVCaptureDevice.authorizationStatus(for: .audio) {
                case .denied, .restricted:
                    throw AudioRoutingError.configuration("Allow microphone access for RaveLink in System Settings → Privacy & Security → Microphone, then start audio again.")
                case .notDetermined:
                    AVCaptureDevice.requestAccess(for: .audio) { _ in }
                    throw AudioRoutingError.configuration("Microphone access has been requested. Allow it in the macOS prompt, then start audio again.")
                default: break
                }
            }
            starting = true; errorMessage = nil
            let request = generation
            let controlQueue = worker
            let cancellation = GraphCancellation()
            pendingStart = cancellation
            worker.async { [weak self] in
                let candidate = AudioGraph(session: routed, channelParents: expanded.channelParents)
                do {
                    try candidate.configure(cancellation: cancellation)
                    Task { @MainActor [weak self] in
                        guard let self else { controlQueue.async { candidate.stop() }; return }
                        guard self.generation == request else { self.worker.async { candidate.stop() }; return }
                        self.worker.async { [weak self] in
                            do {
                                try cancellation.check()
                                try candidate.activateTaps(cancellation: cancellation)
                                Task { @MainActor [weak self] in
                                    guard let self else { controlQueue.async { candidate.stop() }; return }
                                    guard self.generation == request else { controlQueue.async { candidate.stop() }; return }
                                    candidate.controls(routed)
                                    self.graph = candidate; self.routing = expanded; self.errorMessage = nil; self.diagnostics = .init(); self.starting = false; self.pendingStart = nil; self.running = true
                                }
                            } catch {
                                candidate.stop()
                                let message = error.localizedDescription
                                Task { @MainActor [weak self] in
                                    guard let self, self.generation == request else { return }
                                    self.starting = false; self.pendingStart = nil; self.errorMessage = message
                                }
                            }
                        }
                    }
                } catch {
                    candidate.stop()
                    let message = error.localizedDescription
                    Task { @MainActor [weak self] in
                        guard let self, self.generation == request else { return }
                        self.starting = false; self.pendingStart = nil; self.errorMessage = message
                    }
                }
            }
            // CoreAudio driver calls can block without cancellation. Keep the UI
            // responsive, invalidate late results, and require a fresh process.
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(10))
                guard let self, self.generation == request, self.starting else { return }
                self.pendingStart?.cancel(); self.pendingStart = nil
                self.generation &+= 1; self.starting = false; self.workerTimedOut = true
                self.errorMessage = "The audio driver did not respond within 10 seconds. Quit and reopen RaveLink. If it persists, reconnect the device or restart macOS. System audio settings were not changed."
            }
        } catch { starting = false; errorMessage = error.localizedDescription; throw error }
    }
    public func update(session: MixerSession) throws {
        do {
            let expanded = try session.expandedRouting()
            let routed = expanded.session
            try validateFeedback(routed)
            guard let graph else {
                if starting { try start(session: session) }
                return
            }
            if AudioGraph.sameTopology(graph.session, routed) { graph.controls(routed); routing = expanded }
            else { try start(session: session) }
        } catch {
            stop(); errorMessage = error.localizedDescription; throw error
        }
    }
    public func stop() {
        pendingStart?.cancel(); pendingStart = nil
        generation &+= 1; starting = false
        if let graph {
            graph.silence()
            worker.async { [weak self] in
                if let message = graph.stop() {
                    Task { @MainActor [weak self] in self?.workerTimedOut = true; self?.errorMessage = message }
                }
            }
        }
        graph = nil; routing = nil; running = false; channelMeters = [:]; busMeters = [:]
    }
    private func validateFeedback(_ session: MixerSession) throws {
        let virtualIDs = Set(devices.filter(\.isVirtual).map(\.id))
        if hasVirtualFeedbackCycle(session, virtualDeviceUIDs: virtualIDs) {
            throw AudioRoutingError.configuration("The active routes form a feedback loop through virtual devices. Mute a send or choose another output to break the loop before starting audio.")
        }
    }
    private func poll() {
        ticks += 1
        if ticks % 40 == 0 { refreshDevices(); checkDeviceHealth() }
        guard let graph else { return }
        var channels: [UUID: Float] = [:], buses: [UUID: Float] = [:], stats = AudioDiagnostics()
        for capture in graph.captures {
            _ = rl_capture_take_peak(capture.context)
            stats.capturedFrames += rl_capture_frames(capture.context)
        }
        for output in graph.outputs {
            for (i, id) in output.buses.enumerated() { buses[id] = rl_render_take_bus_peak(output.context, UInt32(i)) }
            for (i, channel) in graph.session.channels.enumerated() {
                channels[channel.id] = max(channels[channel.id] ?? 0, rl_render_take_source_peak(output.context, UInt32(i)))
            }
            stats.renderedFrames += rl_render_frames(output.context)
            stats.oversizedBlocks += rl_render_oversized_blocks(output.context)
        }
        for ring in graph.rings { stats.droppedFrames += rl_ring_dropped(ring); stats.underrunFrames += rl_ring_underruns(ring) }
        channelMeters = routing?.aggregateChannelPeaks(channels) ?? channels
        busMeters = routing?.aggregateBusPeaks(buses) ?? buses
        diagnostics = stats
        if stats.oversizedBlocks > 0 {
            stop(); errorMessage = "The audio device requested a buffer larger than 16,384 frames. Choose a smaller device buffer in Audio MIDI Setup and restart audio."
        }
    }
    private func checkDeviceHealth() {
        guard let graph else { return }
        let request = generation
        // Snapshot control state before leaving the main actor.
        let needed = graph.session.buses.compactMap(\.deviceUID) + graph.session.channels.filter { $0.source.kind == .device }.compactMap { $0.source.deviceUID }
        let captureRates = graph.captures.map { ($0.device, $0.rate) }
        let outputRates = graph.outputs.map { ($0.device, $0.rate) }
        let applications = graph.applicationProcesses
        worker.async { [weak self] in
            var message: String?
            let available = Set(Hardware.devices().map { $0.1.id })
            if needed.contains(where: { !available.contains($0) }) {
                message = "An active audio device was disconnected. Reconnect it or choose another device, then start audio."
            } else if (captureRates + outputRates).contains(where: { (try? Hardware.rate($0.0)) != $0.1 }) {
                message = "An audio device changed sample rate. Start audio again to rebuild its route."
            } else if !applications.isEmpty {
                let processes = Hardware.processes()
                for (bundle, ids) in applications where processes.filter({ $0.bundle == bundle && $0.pid != getpid() }).map(\.id).sorted() != ids {
                    message = "A captured application restarted or changed its audio processes. Start audio again to refresh application capture."; break
                }
            }
            if let message {
                Task { @MainActor [weak self] in
                    guard let self, self.generation == request else { return }
                    self.stop(); self.errorMessage = message
                }
            }
        }
    }
}
