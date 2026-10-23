import Foundation
import Testing
@testable import RaveLinkCore

@Suite struct ExpandedRoutingTests {
    private func groupedSession() -> MixerSession {
        var effects = ChannelEffects()
        effects.gainDB = -3; effects.highPassHz = 90; effects.compressorRatio = 3
        let channel = MixerChannel(id: UUID(uuidString: "00000000-0000-4000-8000-000000000001")!, name: "Music and browser",
                                   source: .init(kind: .application, bundleID: "example.music"), muted: true, solo: true,
                                   effects: effects, additionalSources: [.init(kind: .application, bundleID: "example.browser")])
        let monitor = MixBus(id: UUID(uuidString: "00000000-0000-4000-8000-000000000002")!, name: "Personal", deviceUID: "headphones", gainDB: -6,
                             additionalOutputs: [.init(deviceUID: "speakers", channelOffset: 2)])
        let stream = MixBus(id: UUID(uuidString: "00000000-0000-4000-8000-000000000003")!, name: "Stream", deviceUID: "stream")
        return MixerSession(channels: [channel], buses: [monitor, stream], sends: [
            .init(channelID: channel.id, busID: monitor.id, gainDB: -9, pan: -0.25),
            .init(channelID: channel.id, busID: stream.id, gainDB: -18, pan: 0.5, muted: true)
        ])
    }

    @Test func groupedSourcesAndDestinationsPreserveIndependentMixes() throws {
        let original = groupedSession(), expanded = try original.expandedRouting()
        #expect(expanded.session.channels.count == 2)
        #expect(expanded.session.buses.count == 3)
        #expect(expanded.session.sends.count == 6)
        #expect(expanded.session.channels[0].id == original.channels[0].id)
        #expect(expanded.session.buses[0].id == original.buses[0].id)
        #expect(expanded.session.channels.map(\.source) == original.channels[0].allSources)
        #expect(expanded.session.buses.map(\.deviceUID) == ["headphones", "speakers", "stream"])
        #expect(expanded.session.buses.map(\.channelOffset) == [0, 2, 0])
        for channel in expanded.session.channels {
            #expect(channel.additionalSources.isEmpty)
            #expect(channel.effects == original.channels[0].effects)
            #expect(channel.muted && channel.solo)
            #expect(expanded.channelParents[channel.id] == original.channels[0].id)
        }
        for bus in expanded.session.buses {
            #expect(bus.additionalOutputs.isEmpty)
            let parent = try #require(original.buses.first { $0.id == expanded.busParents[bus.id] })
            #expect(bus.gainDB == parent.gainDB && bus.muted == parent.muted)
        }
        for send in expanded.session.sends {
            let originalSend = try #require(original.sends.first { $0.channelID == expanded.channelParents[send.channelID] && $0.busID == expanded.busParents[send.busID] })
            #expect(send.gainDB == originalSend.gainDB)
            #expect(send.pan == originalSend.pan)
            #expect(send.muted == originalSend.muted)
        }
    }

    @Test func generatedIdentitiesStayStableAcrossControlAndLabelEdits() throws {
        var session = groupedSession()
        let first = try session.expandedRouting()
        session.channels[0].name = "Renamed"; session.channels[0].muted = false
        session.channels[0].effects.gainDB = 2; session.buses[0].gainDB = -1
        session.sends[0].pan = 0.75
        let second = try session.expandedRouting()
        #expect(first.session.channels.map(\.id) == second.session.channels.map(\.id))
        #expect(first.session.buses.map(\.id) == second.session.buses.map(\.id))
        #expect(first.channelParents == second.channelParents && first.busParents == second.busParents)
        #expect(first.session != second.session)
        #expect(try second.session.expandedRouting().session == second.session)
    }

    @Test func meterMappingUsesGreatestMemberAndDoesNotInventSummedPeak() throws {
        let session = groupedSession(), expanded = try session.expandedRouting()
        let childIDs = expanded.session.channels.map(\.id), busIDs = expanded.session.buses.map(\.id)
        let channels = expanded.aggregateChannelPeaks([childIDs[0]: 0.4, childIDs[1]: 0.7, UUID(): 9])
        #expect(channels == [session.channels[0].id: 0.7])
        let buses = expanded.aggregateBusPeaks([busIDs[0]: 0.2, busIDs[1]: 0.6, busIDs[2]: 0.3])
        #expect(buses == [session.buses[0].id: 0.6, session.buses[1].id: 0.3])
        #expect(expanded.aggregateChannelPeaks([childIDs[0]: .nan, childIDs[1]: -1])[session.channels[0].id] == 0)
    }

    @Test func oldSchemaOneSessionsDecodeWithoutNewFields() throws {
        var original = groupedSession()
        original.channels[0].additionalSources = []; original.buses[0].additionalOutputs = []
        var json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(original)) as? [String: Any])
        var channels = try #require(json["channels"] as? [[String: Any]])
        var buses = try #require(json["buses"] as? [[String: Any]])
        for index in channels.indices { channels[index].removeValue(forKey: "additionalSources") }
        for index in buses.indices { buses[index].removeValue(forKey: "additionalOutputs") }
        json["channels"] = channels; json["buses"] = buses
        let decoded = try JSONDecoder().decode(MixerSession.self, from: JSONSerialization.data(withJSONObject: json))
        #expect(decoded == original)
        #expect(try decoded.expandedRouting().session == original)
    }

    @Test func groupsRoundTripThroughPersistence() throws {
        let original = groupedSession()
        let decoded = try JSONDecoder().decode(MixerSession.self, from: JSONEncoder().encode(original))
        #expect(decoded == original)
        #expect(try decoded.expandedRouting() == original.expandedRouting())
    }

    @Test func generatedIDCollisionFailsClosed() throws {
        var original = groupedSession()
        let collision = try original.expandedRouting().session.channels[1].id
        original.addChannel(.init(id: collision, name: "Collision", source: .init(kind: .tone)))
        #expect(throws: (any Error).self) { try original.expandedRouting() }
    }

    @Test func additionalOutputWorksWhenPrimaryIsUnassigned() throws {
        var original = groupedSession()
        original.buses[0].deviceUID = nil
        let expanded = try original.expandedRouting()
        #expect(expanded.session.buses[0].deviceUID == nil)
        #expect(expanded.session.buses[1].deviceUID == "speakers")
        #expect(expanded.busParents[expanded.session.buses[1].id] == original.buses[0].id)
    }
}
