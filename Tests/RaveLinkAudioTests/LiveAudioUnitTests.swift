import Foundation
import Testing
import AudioToolbox
import RaveLinkCore
import RaveLinkRealtime
import RaveLinkAudioUnitBridge
@testable import RaveLinkAudio

private final class AUToneFixture {
    let render: OpaquePointer
    init(sources: UInt32 = 1) throws {
        render = try #require(rl_render_create(48000, 512, sources, 1))
        for source in 0..<sources {
            rl_render_set_source(render, source, nil, 48000, true)
            rl_render_source_controls(render, source, true, 0, 0, -80, 0, 1)
            rl_render_send_controls(render, source, 0, 0, 0, false)
        }
        rl_render_set_bus(render, 0, 0); rl_render_bus_controls(render, 0, 0, false)
    }
    deinit { rl_render_destroy(render) }
    func block() -> [Float] {
        var samples = [Float](repeating: 0.75, count: 1024)
        samples.withUnsafeMutableBytes { bytes in
            var list = AudioBufferList(mNumberBuffers: 1, mBuffers: .init(mNumberChannels: 2, mDataByteSize: UInt32(bytes.count), mData: bytes.baseAddress))
            #expect(rl_render_callback(0, nil, nil, nil, &list, nil, UnsafeMutableRawPointer(render)) == noErr)
        }
        return samples
    }
}

@Suite struct LiveAudioUnitTests {
    private var descriptor: AudioUnitDescriptor { .init(component: .init(type: 0x61756678, subtype: 0x6c6d7472, manufacturer: 0x6170706c), name: "Apple: AUPeakLimiter", version: 67072) }
    private func session() -> MixerSession {
        var session = MixerSession.initial
        session.addChannel(.init(name: "Tone", source: .init(kind: .tone), audioUnitEffects: [.init(descriptor: descriptor, parameters: [.init(address: 2, value: 6.0206)])]))
        return session
    }
    @Test func effectTopologyExcludesSafeLiveControls() {
        let initial = session()
        var changed = initial
        changed.channels[0].audioUnitEffects[0].isBypassed = true
        changed.channels[0].audioUnitEffects[0].parameters = [.init(address: 2, value: -6)]
        #expect(LiveAudioUnitGraph.topologyEquivalent(initial, changed))
        changed.channels[0].audioUnitEffects[0].id = UUID()
        #expect(!LiveAudioUnitGraph.topologyEquivalent(initial, changed))
    }
    @Test func renderErrorLatchesSilenceAcrossTheEntireOutput() throws {
        let bridge = try #require(rl_au_graph_create(2, 512, 48000))
        defer { rl_au_graph_destroy(bridge) }
        let fixture = try AUToneFixture(sources: 2)
        let failing: AURenderBlock = { _, _, _, _, _, _ in -12345 }
        #expect(rl_au_graph_append(bridge, 1, 7, failing, nil, false))
        rl_render_set_group_processor(fixture.render, rl_au_graph_process, UnsafeMutableRawPointer(bridge))
        #expect(fixture.block().allSatisfy { $0 == 0 })
        #expect(rl_render_processor_error(fixture.render) == -12345)
        var source: UInt32 = 0, slot: UInt32 = 0
        #expect(rl_au_graph_error(bridge, &source, &slot) == -12345)
        #expect(source == 1 && slot == 7)
        // Even disconnecting the failed processor while stopped cannot clear its
        // existing render graph latch. Recovery requires an explicit new graph.
        rl_render_set_group_processor(fixture.render, nil, nil)
        #expect(fixture.block().allSatisfy { $0 == 0 })
    }
    @Test func malformedEffectOutputLatchesFailure() throws {
        let bridge = try #require(rl_au_graph_create(1, 512, 48000))
        defer { rl_au_graph_destroy(bridge) }
        let fixture = try AUToneFixture()
        let invalid: AURenderBlock = { _, _, frames, _, output, _ in
            let list = UnsafeMutableAudioBufferListPointer(output)
            for buffer in list { buffer.mData?.assumingMemoryBound(to: Float.self).update(repeating: .nan, count: Int(frames)) }
            return noErr
        }
        #expect(rl_au_graph_append(bridge, 0, 3, invalid, nil, false))
        rl_render_set_group_processor(fixture.render, rl_au_graph_process, UnsafeMutableRawPointer(bridge))
        #expect(fixture.block().allSatisfy { $0 == 0 })
        #expect(rl_render_processor_error(fixture.render) == -70003)
    }
    @Test(.enabled(if: ProcessInfo.processInfo.environment["RAVELINK_PLUGIN_RENDER_APPLE"] == "1"))
    func appleEffectRunsInNativeCallbackAndChangesWithoutRebuild() throws {
        var session = session()
        let id = session.channels[0].id
        session.channels[0].additionalSources = [.init(kind: .application, bundleID: "test.second-source")]
        let expanded = try session.expandedRouting()
        let graph = try LiveAudioUnitGraph(session: expanded.session, channelParents: expanded.channelParents, sampleRate: 48000, maxFrames: 512)
        let dry = try AUToneFixture(sources: 2), wet = try AUToneFixture(sources: 2)
        #expect(rl_render_set_source_group(dry.render, 1, 0))
        #expect(rl_render_set_source_group(wet.render, 1, 0))
        graph.install(on: wet.render)
        var drySamples: [Float] = [], wetSamples: [Float] = []
        for _ in 0..<32 { drySamples += dry.block(); wetSamples += wet.block() }
        var maxError: Float = 0
        for frame in 4096..<16384 { maxError = max(maxError, abs(wetSamples[frame * 2] - drySamples[(frame - 96) * 2] * 2)) }
        #expect(maxError < 0.000_03)
        #expect(graph.failureMessage == nil)
        session.channels[0].audioUnitEffects[0].parameters = [.init(address: 2, value: -6.0206)]
        try graph.updateControls(session: session.expandedRouting().session)
        drySamples = []; wetSamples = []
        for _ in 0..<16 { drySamples += dry.block(); wetSamples += wet.block() }
        maxError = 0
        for frame in 2048..<8192 { maxError = max(maxError, abs(wetSamples[frame * 2] - drySamples[(frame - 96) * 2] * 0.5)) }
        #expect(maxError < 0.000_03)
        session.channels[0].audioUnitEffects[0].isBypassed = true
        try graph.updateControls(session: session.expandedRouting().session)
        drySamples = []; wetSamples = []
        for _ in 0..<16 { drySamples += dry.block(); wetSamples += wet.block() }
        maxError = 0
        for index in 8192..<16384 { maxError = max(maxError, abs(wetSamples[index] - drySamples[index])) }
        #expect(maxError < 0.000_01)
        #expect(try graph.snapshotStates()[id]?.count == 1)
        #expect(rl_render_processor_error(wet.render) == 0)
    }
    @Test(.enabled(if: ProcessInfo.processInfo.environment["RAVELINK_PLUGIN_RENDER_APPLE"] == "1"))
    func failedPreparationCanReleasePartlyCreatedGraph() throws {
        var session = session()
        session.channels[0].audioUnitEffects[0].parameters = [.init(address: 2, value: 100)]
        #expect(throws: (any Error).self) {
            try LiveAudioUnitGraph(session: session, channelParents: [:], sampleRate: 48000, maxFrames: 512)
        }
        session.channels[0].audioUnitEffects[0].parameters = []
        session.channels[0].audioUnitEffects[0].state = .init(component: descriptor.component, componentVersion: descriptor.version, propertyList: Data([1, 2, 3]))
        #expect(throws: (any Error).self) {
            try LiveAudioUnitGraph(session: session, channelParents: [:], sampleRate: 48000, maxFrames: 512)
        }
        session.channels[0].audioUnitEffects[0].state = nil
        // Prepare a real first unit before failing a missing second unit, so the
        // partially built bridge and its retained block ownership are exercised.
        session.channels[0].audioUnitEffects.append(.init(descriptor: .init(component: .init(type: 0x61756678, subtype: 0xdeadbeef, manufacturer: 0xdeadbeef), name: "Missing test unit", version: nil)))
        #expect(throws: (any Error).self) {
            try LiveAudioUnitGraph(session: session, channelParents: [:], sampleRate: 48000, maxFrames: 512)
        }
    }
}
