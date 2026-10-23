import Foundation
import Testing
import Darwin
import RaveLinkCore
@testable import RaveLinkAudio

@Suite struct EngineProtocolTests {
    @Test func boundsPartialLinesAndRejectsVersionMismatch() throws {
        var framing = EngineLineBuffer()
        #expect(try framing.append(Data("{\"a\":".utf8)).isEmpty)
        #expect(try framing.append(Data("1}\n{\"b\":2}\n".utf8)).count == 2)
        #expect(!framing.hasPartialLine)
        var oversized = EngineLineBuffer()
        #expect(throws: (any Error).self) { try oversized.append(Data(repeating: 65, count: EngineWire.maximumLineBytes + 1)) }
        let request = EngineRequest(generation: 1, operation: .discover)
        var object = try #require(JSONSerialization.jsonObject(with: EngineWire.encode(request)) as? [String: Any])
        object["version"] = 999
        #expect(throws: (any Error).self) { try EngineWire.request(JSONSerialization.data(withJSONObject: object)) }
    }
    @Test func rejectsContradictoryAndNonfiniteState() throws {
        var snapshot = EngineSnapshot(); snapshot.running = true; snapshot.starting = true
        let bytes = try EngineWire.encode(EngineResponse(generation: 1, kind: .state, snapshot: snapshot))
        #expect(throws: (any Error).self) { try EngineWire.response(bytes) }
        snapshot.starting = false; snapshot.channelMeters[UUID()] = .nan
        #expect(throws: (any Error).self) { try EngineWire.encode(EngineResponse(generation: 1, kind: .state, snapshot: snapshot)) }
    }
}

private struct EngineFixture {
    let directory: URL
    let executable: URL
    let pidFile: URL
    init(_ mode: String) throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("ravelink-engine-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        executable = directory.appendingPathComponent("fixture.py"); pidFile = directory.appendingPathComponent("pid")
        let script = """
        #!/usr/bin/python3
        import json, os, signal, sys, time
        from pathlib import Path
        mode = '\(mode)'
        pid_file = Path(__file__).with_name('pid')
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), 0)
                Path(__file__).with_name('overlap').write_text('previous process was still alive')
            except ProcessLookupError: pass
        pid_file.write_text(str(os.getpid()))
        with Path(__file__).with_name('launches').open('a') as stream: stream.write(str(os.getpid()) + '\\n')
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if mode == 'crash': os._exit(17)
        if mode == 'hang': time.sleep(30)
        if mode == 'flood':
            sys.stdout.write('X' * (5 * 1024 * 1024)); sys.stdout.flush(); time.sleep(30)
        running = False
        def snapshot(active=False):
            return {'devices': [], 'applications': [], 'running': active, 'starting': False,
                    'channelMeters': [], 'busMeters': [],
                    'diagnostics': {'capturedFrames':0,'renderedFrames':0,'droppedFrames':0,'underrunFrames':0,'oversizedBlocks':0}}
        for line in sys.stdin:
            request = json.loads(line)
            operation = request['operation']
            if operation == 'start':
                with Path(__file__).with_name('starts').open('a') as stream: stream.write(request['session']['name'] + '\\n')
            if operation == 'update':
                with Path(__file__).with_name('updates').open('a') as stream: stream.write(request['session']['name'] + '\\n')
            if operation == 'stop' and mode == 'hang_stop': time.sleep(30)
            if operation == 'start' and mode == 'slow_start' and request['session']['name'] == 'old': time.sleep(30)
            if operation == 'start': running = True
            if operation == 'stop': running = False
            generation = request['generation']
            reply = {'version':1,'id':request['id'],'generation':generation,'kind':'reply','success':True,'snapshot':snapshot(running)}
            print(json.dumps(reply), flush=True)
            if mode == 'stale' and operation == 'stop':
                print(json.dumps({'version':1,'generation':generation-1,'kind':'state','success':True,'snapshot':snapshot(True)}),flush=True)
        """
        try script.write(to: executable, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
    }
    func remove() { try? FileManager.default.removeItem(at: directory) }
    var recordedPID: Int32? { (try? String(contentsOf: pidFile, encoding: .utf8)).flatMap { Int32($0) } }
}
@MainActor private func eventually(_ predicate: () -> Bool, timeout: TimeInterval = 3) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while !predicate(), Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
    try #require(predicate())
}
private func processGone(_ pid: Int32) -> Bool { kill(pid, 0) == -1 && errno == ESRCH }

@Suite(.serialized) struct EngineClientTests {
    @Test @MainActor func discoveryTimeoutKillsAndReapsUncooperativeChild() async throws {
        let fixture = try EngineFixture("hang"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, timeouts: .init(discovery: 1.5))
        defer { client.shutdown() }
        try await eventually { client.helperProcessID != nil }
        let pid = try #require(client.helperProcessID)
        try await eventually { client.errorMessage != nil }
        #expect(client.errorMessage?.contains("device discovery") == true)
        #expect(!client.running && !client.starting)
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func abruptExitDoesNotRaiseSIGPIPEInClient() async throws {
        let fixture = try EngineFixture("crash"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, timeouts: .init(discovery: 0.5))
        defer { client.shutdown() }
        try await eventually { client.errorMessage != nil && fixture.recordedPID != nil }
        let pid = try #require(fixture.recordedPID)
        try await eventually { processGone(pid) }
        #expect(!client.running)
    }
    @Test @MainActor func malformedFloodIsBoundedAndChildReaped() async throws {
        let fixture = try EngineFixture("flood"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable)
        defer { client.shutdown() }
        try await eventually { client.errorMessage != nil && fixture.recordedPID != nil }
        let pid = try #require(fixture.recordedPID)
        #expect(client.errorMessage?.contains("4 MiB") == true)
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func stopHasIndependentDeadlineAndReapsHungHelper() async throws {
        let fixture = try EngineFixture("hang_stop"); defer { fixture.remove() }
        // Startup latency is independent of the stop deadline under test.
        let client = EngineClient(helperURL: fixture.executable, timeouts: .init(start: 5, stop: 0.2), autoDiscover: false)
        defer { client.shutdown() }
        try client.start(session: .initial)
        try await eventually({ client.running || client.errorMessage != nil }, timeout: 6)
        try #require(client.running, Comment(rawValue: client.errorMessage ?? "Fixture did not finish startup"))
        let pid = try #require(client.helperProcessID)
        client.stop()
        try await eventually { client.errorMessage?.contains("finish stop") == true }
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func startHasHardRoutingDeadline() async throws {
        let fixture = try EngineFixture("slow_start"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, timeouts: .init(start: 1.5), autoDiscover: false)
        defer { client.shutdown() }
        var session = MixerSession.initial; session.name = "old"
        try client.start(session: session)
        try await eventually { client.helperProcessID != nil }
        let pid = try #require(client.helperProcessID)
        try await eventually { client.errorMessage != nil }
        #expect(client.errorMessage?.contains("audio routing") == true)
        #expect(!client.running && !client.starting)
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func staleTelemetryCannotRestartStoppedSession() async throws {
        let fixture = try EngineFixture("stale"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, autoDiscover: false)
        defer { client.shutdown() }
        try client.start(session: .initial)
        try await eventually { client.running }
        let pid = try #require(client.helperProcessID)
        client.stop()
        try await Task.sleep(for: .milliseconds(150))
        #expect(!client.running && !client.starting)
        #expect(client.errorMessage == nil)
        client.shutdown()
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func editDuringStartReplacesOldProcessWithLatestSession() async throws {
        let fixture = try EngineFixture("slow_start"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, autoDiscover: false)
        defer { client.shutdown() }
        var session = MixerSession.initial; session.name = "old"
        try client.start(session: session)
        try await eventually { client.helperProcessID != nil }
        let oldPID = try #require(client.helperProcessID)
        session.name = "new"
        try client.update(session: session)
        try await eventually { client.running }
        let newPID = try #require(client.helperProcessID)
        #expect(newPID != oldPID)
        #expect(!FileManager.default.fileExists(atPath: fixture.directory.appendingPathComponent("overlap").path), "Replacement must start after the previous child is reaped")
        try await eventually { processGone(oldPID) }
        client.shutdown()
        try await eventually { processGone(newPID) }
    }
    @Test @MainActor func sustainedControlInputSendsUpdatesBeforeProducerStops() async throws {
        let fixture = try EngineFixture("echo"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, autoDiscover: false)
        defer { client.shutdown() }
        try client.start(session: .initial)
        try await eventually { client.running }
        let log = fixture.directory.appendingPathComponent("updates")
        var deliveredDuringInput = false
        for index in 0..<40 {
            var session = MixerSession.initial; session.name = "edit-\(index)"
            try client.update(session: session)
            try await Task.sleep(for: .milliseconds(5))
            if index < 35 && FileManager.default.fileExists(atPath: log.path) { deliveredDuringInput = true }
        }
        #expect(deliveredDuringInput, "A continuous drag must not postpone every update until release")
        try await eventually { (try? String(contentsOf: log, encoding: .utf8).contains("edit-39")) == true }
        let pid = try #require(client.helperProcessID)
        client.shutdown()
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func pendingReplacementCoalescesRapidStartEdits() async throws {
        let fixture = try EngineFixture("slow_start"); defer { fixture.remove() }
        let client = EngineClient(helperURL: fixture.executable, autoDiscover: false)
        defer { client.shutdown() }
        var session = MixerSession.initial; session.name = "old"
        try client.start(session: session)
        let starts = fixture.directory.appendingPathComponent("starts")
        try await eventually { (try? String(contentsOf: starts, encoding: .utf8).contains("old")) == true }
        for index in 0..<100 {
            session.name = "pending-\(index)"
            try client.update(session: session)
        }
        try await eventually { client.running }
        let launches = try String(contentsOf: fixture.directory.appendingPathComponent("launches"), encoding: .utf8).split(separator: "\n")
        #expect(launches.count == 2)
        #expect(try String(contentsOf: starts, encoding: .utf8).contains("pending-99"))
        #expect(!FileManager.default.fileExists(atPath: fixture.directory.appendingPathComponent("overlap").path))
        let pid = try #require(client.helperProcessID)
        client.shutdown()
        try await eventually { processGone(pid) }
    }
    @Test @MainActor func realHelperExitsWhenParentControlPipeCloses() async throws {
        let helper = try #require(EngineClient.defaultHelperURL())
        let process = Process(), input = Pipe()
        process.executableURL = helper; process.standardInput = input
        process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
        try process.run()
        let pid = process.processIdentifier
        try input.fileHandleForWriting.close()
        try await eventually { !process.isRunning }
        process.waitUntilExit()
        #expect(process.terminationStatus == 0)
        #expect(processGone(pid))
    }
    @Test(.enabled(if: ProcessInfo.processInfo.environment["RAVELINK_TEST_SILENT_OUTPUT"] == "1")) @MainActor func realSilentOutputThroughSupervisedProcess() async throws {
        let helper = try #require(EngineClient.defaultHelperURL())
        let client = EngineClient(helperURL: helper)
        defer { client.shutdown() }
        let uid = ProcessInfo.processInfo.environment["RAVELINK_SILENT_OUTPUT_UID"] ?? "BuiltInSpeakerDevice"
        try await eventually({ client.devices.contains { $0.id == uid } }, timeout: 10)
        let source = MixerChannel(name: "Silent IPC check", source: .init(kind: .tone), muted: true)
        let bus = MixBus(name: "Silent output", deviceUID: uid)
        let session = MixerSession(channels: [source], buses: [bus], sends: [.init(channelID: source.id, busID: bus.id, muted: true)])
        try client.start(session: session)
        try await eventually({ client.running || client.errorMessage != nil }, timeout: 14)
        try #require(client.running, Comment(rawValue: client.errorMessage ?? "Engine did not start"))
        let pid = try #require(client.helperProcessID)
        try await eventually { client.diagnostics.renderedFrames > 10000 }
        #expect(client.busMeters[bus.id] == 0)
        print("SUPERVISED_SILENT_OUTPUT uid=\(uid) frames=\(client.diagnostics.renderedFrames) peak=\(client.busMeters[bus.id] ?? -1) helperPID=\(pid)")
        client.stop()
        try await Task.sleep(for: .milliseconds(150))
        #expect(client.errorMessage == nil)
        client.shutdown()
        try await eventually { processGone(pid) }
    }
}
