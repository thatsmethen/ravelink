import XCTest
@testable import RaveLinkCore

final class SessionTests: XCTestCase {
    func testDynamicMatrixBeyondReferenceLimits() throws {
        var s = MixerSession.initial
        for i in 0..<128 { s.addChannel(.init(name: "Input \(i)")) }
        for i in 0..<29 { s.addBus(.init(name: "Mix \(i)")) }
        XCTAssertEqual(s.channels.count, 128); XCTAssertEqual(s.buses.count, 32)
        XCTAssertEqual(s.sends.count, 4096); XCTAssertTrue(s.sends.allSatisfy(\.muted))
        _ = try s.validated()
        s.removeChannel(s.channels[0].id); s.removeBus(s.buses[0].id)
        XCTAssertEqual(s.sends.count, 127 * 31); _ = try s.validated()
    }
    func testPersistenceRoundTripAndAtomicReplacement() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let store = SessionStore(url: dir.appendingPathComponent("session.json"))
        var s = MixerSession.initial; s.addChannel(.init(name: "Voice", source: .init(kind: .application, bundleID: "example.app")))
        s.sends[0].gainDB = -12; s.sends[0].muted = false
        try store.save(s); XCTAssertEqual(try store.load(), s)
        s.name = "Replaced"; try store.save(s); XCTAssertEqual(try store.load(), s)
    }
    func testRejectDanglingDuplicateAndNonfiniteRoutes() throws {
        var s = MixerSession.initial; s.addChannel(.init(name: "Voice"))
        s.sends[0].channelID = UUID(); XCTAssertThrowsError(try s.validated())
        s.sends[0].channelID = s.channels[0].id; s.sends.append(s.sends[0]); XCTAssertThrowsError(try s.validated())
        s.sends.removeLast(); s.sends[0].gainDB = .nan; XCTAssertThrowsError(try s.validated())
    }
    func testRejectUnknownSchemaAndInvalidEffects() throws {
        var s = MixerSession.initial; s.schemaVersion = 2; XCTAssertThrowsError(try s.validated())
        s.schemaVersion = 1; s.addChannel(.init(name: "Voice")); s.channels[0].effects.compressorRatio = 0
        XCTAssertThrowsError(try s.validated())
    }
    func testInvalidSavePreservesPreviousSession() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let store = SessionStore(url: dir.appendingPathComponent("session.json"))
        let original = MixerSession.initial; try store.save(original)
        var invalid = original; invalid.buses[0].gainDB = .infinity
        XCTAssertThrowsError(try store.save(invalid)); XCTAssertEqual(try store.load(), original)
    }
}
