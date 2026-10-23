import Foundation

public enum SessionError: LocalizedError {
    case invalid(String)
    public var errorDescription: String? { if case let .invalid(message) = self { return message }; return nil }
}
public extension MixerSession {
    func validated() throws -> MixerSession {
        func require(_ condition: Bool, _ message: String) throws { if !condition { throw SessionError.invalid(message) } }
        try require(schemaVersion == 1, "This session was saved by an unsupported version of RaveLink.")
        try require(!name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, "Give the session a name.")
        try require(Set(channels.map(\.id)).count == channels.count, "Duplicate input identifiers.")
        try require(Set(buses.map(\.id)).count == buses.count, "Duplicate mix identifiers.")
        try require(Set(sends.map(\.id)).count == sends.count, "Duplicate routes.")
        let channelIDs = Set(channels.map(\.id)), busIDs = Set(buses.map(\.id))
        for channel in channels {
            try require(!channel.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, "Input names cannot be empty.")
            try require(channel.source.channelOffset >= 0 && channel.source.channelOffset < 4096, "Input channel offset is invalid.")
            let e = channel.effects
            try require(e.gainDB.isFinite && (-60...24).contains(e.gainDB), "Input gain must be between −60 and +24 dB.")
            try require(e.highPassHz.isFinite && (0...2000).contains(e.highPassHz), "High-pass frequency is invalid.")
            try require(e.gateThresholdDB.isFinite && (-100...0).contains(e.gateThresholdDB), "Gate threshold is invalid.")
            try require(e.compressorThresholdDB.isFinite && (-60...0).contains(e.compressorThresholdDB), "Compressor threshold is invalid.")
            try require(e.compressorRatio.isFinite && (1...20).contains(e.compressorRatio), "Compressor ratio is invalid.")
        }
        for bus in buses {
            try require(!bus.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, "Mix names cannot be empty.")
            try require(bus.channelOffset >= 0 && bus.channelOffset < 4096, "Output channel offset is invalid.")
            try require(bus.gainDB.isFinite && (-60...12).contains(bus.gainDB), "Mix gain is invalid.")
        }
        for send in sends {
            try require(channelIDs.contains(send.channelID) && busIDs.contains(send.busID), "A route refers to a missing input or mix.")
            try require(send.gainDB.isFinite && (-60...12).contains(send.gainDB), "Route gain is invalid.")
            try require(send.pan.isFinite && (-1...1).contains(send.pan), "Pan must be between −1 and +1.")
        }
        return self
    }
}

public struct SessionStore {
    public let url: URL
    public init(url: URL) { self.url = url }
    public static var standard: SessionStore {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return .init(url: base.appendingPathComponent("RaveLink/session.json"))
    }
    public func load() throws -> MixerSession {
        let data = try Data(contentsOf: url)
        guard data.count < 32 * 1024 * 1024 else { throw SessionError.invalid("Session exceeds the 32 MB import safety limit.") }
        return try JSONDecoder().decode(MixerSession.self, from: data).validated()
    }
    public func save(_ session: MixerSession) throws {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(session.validated())
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url, options: .atomic)
    }
}
