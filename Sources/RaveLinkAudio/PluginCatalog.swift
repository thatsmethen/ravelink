import Foundation
import Darwin

public struct AudioUnitComponentID: Codable, Hashable, Sendable {
    public let type: UInt32
    public let subtype: UInt32
    public let manufacturer: UInt32
    public init(type: UInt32, subtype: UInt32, manufacturer: UInt32) {
        self.type = type; self.subtype = subtype; self.manufacturer = manufacturer
    }
    public var key: String { String(format: "%08x:%08x:%08x", type, subtype, manufacturer) }
}
public struct AudioUnitDescriptor: Codable, Equatable, Identifiable, Sendable {
    public let component: AudioUnitComponentID
    public let name: String
    public let version: UInt32?
    public let flags: UInt32
    public var id: String { component.key }
}
public struct AudioUnitBusReport: Codable, Equatable, Sendable {
    public let index: Int
    public let name: String?
    public let sampleRate: Double
    public let channels: UInt32
    public let interleaved: Bool
    public let commonFormat: UInt
    public let channelLayoutTag: UInt32?
    public let enabled: Bool
}
public struct AudioUnitParameterReport: Codable, Equatable, Sendable {
    public let address: UInt64
    public let identifier: String
    public let name: String
    public let minimum: Float?
    public let maximum: Float?
    public let initialValue: Float?
    public let declaredDefaultValue: Float?
    public let unit: UInt32
    public let unitName: String?
    public let flags: UInt32
}
public struct AudioUnitProbeReport: Codable, Equatable, Sendable {
    public let descriptor: AudioUnitDescriptor
    public let inputBuses: [AudioUnitBusReport]
    public let outputBuses: [AudioUnitBusReport]
    public let channelCapabilities: [Int]?
    public let parameters: [AudioUnitParameterReport]
    public let requestedSampleRate: Double
    public let requestedChannels: UInt32
    public let configurationAccepted: Bool
    public let renderResourcesAllocated: Bool
    public let configurationError: String?
    public let latencySeconds: Double?
    public let tailSeconds: Double?
    public let limitations: [String]
}
public enum PluginCatalogError: Error, LocalizedError, Equatable {
    case helperUnavailable
    case launchFailed(String)
    case invalidRequest
    case timeout
    case cancelled
    case outputLimit
    case crashed(Int32)
    case failed(Int32)
    case malformedResponse
    case unsupportedProtocol(Int)
    case operationMismatch
    case helperError(String, String)
    public var errorDescription: String? {
        switch self {
        case .helperUnavailable: return "The Audio Unit helper is missing. Reinstall RaveLink or build RaveLinkPluginHost beside the app."
        case .launchFailed(let message): return "Could not start the Audio Unit helper: \(message)"
        case .invalidRequest: return "The Audio Unit probe request is invalid."
        case .timeout: return "The Audio Unit helper timed out and was stopped."
        case .cancelled: return "Audio Unit inspection was cancelled."
        case .outputLimit: return "The Audio Unit helper exceeded its response limit and was stopped."
        case .crashed(let signal): return "The Audio Unit helper crashed (signal \(signal)). RaveLink is still running."
        case .failed(let status): return "The Audio Unit helper exited with status \(status)."
        case .malformedResponse: return "The Audio Unit helper returned an invalid response."
        case .unsupportedProtocol(let version): return "Unsupported Audio Unit helper protocol: \(version)."
        case .operationMismatch: return "The Audio Unit helper replied to a different request."
        case .helperError(_, let message): return message
        }
    }
}

private struct PluginRequest: Encodable {
    let protocolVersion = 1
    let operation: String
    var component: AudioUnitComponentID?
    var expectedVersion: UInt32?
    var sampleRate: Double?
    var channels: UInt32?
}
struct PluginResponse: Decodable {
    struct Failure: Decodable { let code: String; let message: String }
    let protocolVersion: Int
    let operation: String
    let status: String
    let components: [AudioUnitDescriptor]?
    let probe: AudioUnitProbeReport?
    let error: Failure?
    let limitations: [String]?

    static func parse(_ data: Data, operation: String) throws -> PluginResponse {
        guard data.count <= PluginCatalog.maximumResponseBytes,
              let response = try? JSONDecoder().decode(Self.self, from: data) else { throw PluginCatalogError.malformedResponse }
        guard response.protocolVersion == 1 else { throw PluginCatalogError.unsupportedProtocol(response.protocolVersion) }
        guard response.operation == operation else { throw PluginCatalogError.operationMismatch }
        if response.status == "error", let failure = response.error {
            throw PluginCatalogError.helperError(failure.code, String(failure.message.prefix(2048)))
        }
        guard response.status == "ok", response.error == nil else { throw PluginCatalogError.malformedResponse }
        switch operation {
        case "list":
            guard let entries = response.components, response.probe == nil,
                  entries.count <= 4096, Set(entries.map(\.id)).count == entries.count,
                  entries.allSatisfy({ isEffect($0.component) && !$0.name.isEmpty && $0.name.count <= 512 }) else { throw PluginCatalogError.malformedResponse }
        case "probe":
            guard let probe = response.probe, response.components == nil,
                  isEffect(probe.descriptor.component), probe.parameters.count <= 4096,
                  probe.inputBuses.count <= 64, probe.outputBuses.count <= 64,
                  probe.requestedSampleRate.isFinite, (8_000...384_000).contains(probe.requestedSampleRate),
                  (1...2).contains(probe.requestedChannels),
                  !probe.renderResourcesAllocated || probe.configurationAccepted,
                  probe.parameters.allSatisfy({ [$0.minimum, $0.maximum, $0.initialValue, $0.declaredDefaultValue].allSatisfy { $0?.isFinite ?? true } }),
                  (probe.inputBuses + probe.outputBuses).allSatisfy({ $0.sampleRate.isFinite && $0.sampleRate > 0 }),
                  probe.latencySeconds?.isFinite ?? true,
                  probe.tailSeconds?.isFinite ?? true else { throw PluginCatalogError.malformedResponse }
        default: throw PluginCatalogError.operationMismatch
        }
        return response
    }
}
private func isEffect(_ id: AudioUnitComponentID) -> Bool {
    // Apple's aufx / aumf identifiers. Metadata only; no AU is loaded in this module.
    (id.type == 0x61756678 || id.type == 0x61756d66) && id.subtype != 0 && id.manufacturer != 0
}

private final class PluginCatalogBundleMarker: NSObject {}

public struct PluginCatalog: Sendable {
    public static let maximumResponseBytes = 4 * 1024 * 1024
    public let helperURL: URL?
    public init(helperURL: URL? = PluginCatalog.defaultHelperURL()) { self.helperURL = helperURL }

    public static func defaultHelperURL(bundle: Bundle = .main) -> URL? {
        var candidates: [URL] = []
        // SwiftPM may execute tests through its own runner. The class bundle
        // identifies our loaded image instead of that external runner.
        for source in [bundle, Bundle(for: PluginCatalogBundleMarker.self)] {
            candidates.append(source.bundleURL.appendingPathComponent("Contents/Helpers/RaveLinkPluginHost"))
            if source.bundleURL.pathExtension == "xctest" {
                candidates.append(source.bundleURL.deletingLastPathComponent().appendingPathComponent("RaveLinkPluginHost"))
            }
        }
        if let executable = bundle.executableURL { candidates.append(executable.deletingLastPathComponent().appendingPathComponent("RaveLinkPluginHost")) }
        if let command = CommandLine.arguments.first {
            let executable = URL(fileURLWithPath: command).standardizedFileURL
            candidates.append(executable.deletingLastPathComponent().appendingPathComponent("RaveLinkPluginHost"))
            // Swift Testing's runner is inside an xctest bundle even when the
            // Foundation main bundle points at the runner's MacOS directory.
            var ancestor = executable.deletingLastPathComponent()
            for _ in 0..<3 {
                if ancestor.pathExtension == "xctest" {
                    candidates.append(ancestor.deletingLastPathComponent().appendingPathComponent("RaveLinkPluginHost"))
                    break
                }
                ancestor.deleteLastPathComponent()
            }
        }
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }
    public func discover(timeout: TimeInterval = 10) async throws -> [AudioUnitDescriptor] {
        let response = try await request(PluginRequest(operation: "list"), timeout: timeout)
        return response.components!.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }
    public func probe(_ descriptor: AudioUnitDescriptor, sampleRate: Double = 48_000, channels: UInt32 = 2, timeout: TimeInterval = 10) async throws -> AudioUnitProbeReport {
        guard isEffect(descriptor.component), sampleRate.isFinite, (8_000...384_000).contains(sampleRate), (1...2).contains(channels) else { throw PluginCatalogError.invalidRequest }
        let request = PluginRequest(operation: "probe", component: descriptor.component, expectedVersion: descriptor.version, sampleRate: sampleRate, channels: channels)
        let response = try await self.request(request, timeout: timeout)
        guard let probe = response.probe, probe.descriptor.component == descriptor.component,
              probe.requestedSampleRate == sampleRate, probe.requestedChannels == channels,
              descriptor.version == nil || probe.descriptor.version == descriptor.version else { throw PluginCatalogError.malformedResponse }
        return probe
    }
    private func request(_ request: PluginRequest, timeout: TimeInterval) async throws -> PluginResponse {
        guard timeout.isFinite, (0.05...60).contains(timeout) else { throw PluginCatalogError.invalidRequest }
        guard let helperURL, FileManager.default.isExecutableFile(atPath: helperURL.path) else { throw PluginCatalogError.helperUnavailable }
        let bytes = try JSONEncoder().encode(request)
        let run = PluginHelperProcess()
        let result = try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<PluginHelperResult, Error>) in
                DispatchQueue.global(qos: .userInitiated).async {
                    do { continuation.resume(returning: try run.execute(helperURL, request: bytes, timeout: timeout)) }
                    catch { continuation.resume(throwing: error) }
                }
            }
        } onCancel: { run.cancel() }
        if result.reason == .uncaughtSignal { throw PluginCatalogError.crashed(result.status) }
        if result.status != 0 {
            // Typed helper failures remain useful; arbitrary crash text stays out of the UI.
            if let response = try? JSONDecoder().decode(PluginResponse.self, from: result.stdout), response.status == "error" {
                _ = try PluginResponse.parse(result.stdout, operation: request.operation)
            }
            throw PluginCatalogError.failed(result.status)
        }
        return try PluginResponse.parse(result.stdout, operation: request.operation)
    }
}

struct PluginHelperResult { let stdout: Data; let status: Int32; let reason: Process.TerminationReason }

// One background worker owns the Process and both nonblocking pipe reads.
// No UI thread waits, pipe-reader tasks, or unbounded output buffers survive a run.
final class PluginHelperProcess: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    private var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }

    func execute(_ executable: URL, request: Data, timeout: TimeInterval) throws -> PluginHelperResult {
        if isCancelled { throw PluginCatalogError.cancelled }
        guard request.count <= 4096 else { throw PluginCatalogError.invalidRequest }
        let process = Process(), input = Pipe(), output = Pipe(), errors = Pipe()
        process.executableURL = executable
        process.standardInput = input; process.standardOutput = output; process.standardError = errors
        let exited = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in exited.signal() }
        // The bounded request fits in the pipe before launch. Writing while our
        // read end is open avoids SIGPIPE if a crashing helper exits immediately.
        try input.fileHandleForWriting.write(contentsOf: request)
        try input.fileHandleForWriting.close()
        do { try process.run() } catch { throw PluginCatalogError.launchFailed(error.localizedDescription) }
        try? input.fileHandleForReading.close()
        try? output.fileHandleForWriting.close(); try? errors.fileHandleForWriting.close()
        defer {
            try? input.fileHandleForWriting.close()
            try? output.fileHandleForReading.close(); try? errors.fileHandleForReading.close()
        }
        let outFD = output.fileHandleForReading.fileDescriptor, errFD = errors.fileHandleForReading.fileDescriptor
        _ = fcntl(outFD, F_SETFL, fcntl(outFD, F_GETFL) | O_NONBLOCK)
        _ = fcntl(errFD, F_SETFL, fcntl(errFD, F_GETFL) | O_NONBLOCK)
        let started = DispatchTime.now().uptimeNanoseconds
        let budget = UInt64(timeout * 1_000_000_000)
        var stdout = Data(), stderrCount = 0, outEOF = false, errEOF = false
        var buffer = [UInt8](repeating: 0, count: 16_384)

        func drain(_ fd: Int32, retain: Bool) throws -> Bool {
            while true {
                let count = read(fd, &buffer, buffer.count)
                if count > 0 {
                    if retain {
                        guard stdout.count + count <= PluginCatalog.maximumResponseBytes else { throw PluginCatalogError.outputLimit }
                        stdout.append(contentsOf: buffer.prefix(count))
                    } else {
                        stderrCount += count
                        guard stderrCount <= 256 * 1024 else { throw PluginCatalogError.outputLimit }
                    }
                } else if count == 0 { return true }
                else if errno == EAGAIN || errno == EWOULDBLOCK { return false }
                else if errno != EINTR { throw PluginCatalogError.malformedResponse }
            }
        }
        do {
            while true {
                if isCancelled { throw PluginCatalogError.cancelled }
                if DispatchTime.now().uptimeNanoseconds - started >= budget { throw PluginCatalogError.timeout }
                if !outEOF { outEOF = try drain(outFD, retain: true) }
                if !errEOF { errEOF = try drain(errFD, retain: false) }
                if !process.isRunning {
                    if !outEOF { _ = try drain(outFD, retain: true) }
                    if !errEOF { _ = try drain(errFD, retain: false) }
                    return .init(stdout: stdout, status: process.terminationStatus, reason: process.terminationReason)
                }
                var events = [pollfd(fd: outEOF ? -1 : outFD, events: Int16(POLLIN), revents: 0), pollfd(fd: errEOF ? -1 : errFD, events: Int16(POLLIN), revents: 0)]
                _ = poll(&events, nfds_t(events.count), 20)
            }
        } catch { stop(process, exited: exited); throw error }
    }
    private func stop(_ process: Process, exited: DispatchSemaphore) {
        guard process.isRunning else { return }
        process.terminate()
        if exited.wait(timeout: .now() + 0.2) == .timedOut, process.isRunning {
            _ = kill(process.processIdentifier, SIGKILL)
            _ = exited.wait(timeout: .now() + 1)
        }
    }
}
