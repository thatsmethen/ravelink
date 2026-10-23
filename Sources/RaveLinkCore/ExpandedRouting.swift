import Foundation
import CryptoKit

/// A device-level graph derived from the user's grouped channel/mix model.
/// IDs are stable across control and label edits. Primary nodes retain their IDs;
/// additional nodes use UUID v5 identities derived from the parent and array slot.
public struct ExpandedRouting: Sendable, Equatable {
    public let session: MixerSession
    /// Expanded channel ID → original visible channel ID, including primary nodes.
    public let channelParents: [UUID: UUID]
    /// Expanded bus ID → original visible bus ID, including primary nodes.
    public let busParents: [UUID: UUID]

    /// Greatest member peak, representing activity in a source group. This is not
    /// a reconstructed waveform peak for the sum; scalar peaks cannot provide it.
    public func aggregateChannelPeaks(_ peaks: [UUID: Float]) -> [UUID: Float] {
        aggregate(peaks, parents: channelParents)
    }
    /// Greatest output peak for each visible mix, including rate-converted copies.
    public func aggregateBusPeaks(_ peaks: [UUID: Float]) -> [UUID: Float] {
        aggregate(peaks, parents: busParents)
    }
    private func aggregate(_ peaks: [UUID: Float], parents: [UUID: UUID]) -> [UUID: Float] {
        var result = Dictionary(Set(parents.values).map { ($0, Float.zero) }, uniquingKeysWith: max)
        for (child, peak) in peaks where peak.isFinite && peak >= 0 {
            guard let parent = parents[child] else { continue }
            result[parent] = max(result[parent] ?? 0, peak)
        }
        return result
    }
}

public extension MixerSession {
    /// Expands every grouped source into a capture channel and every additional
    /// output into a bus. Each parent send is copied to the cross-product of its
    /// source members and destinations, preserving gain, pan, and mute settings.
    /// Effect settings are copied to each member; nonlinear processing therefore
    /// occurs per source, not after summing the group.
    func expandedRouting() throws -> ExpandedRouting {
        _ = try validated()
        var channelGroups: [UUID: [UUID]] = [:], busGroups: [UUID: [UUID]] = [:]
        var channelParents: [UUID: UUID] = [:], busParents: [UUID: UUID] = [:]
        var lowered = MixerSession(name: name)
        lowered.schemaVersion = schemaVersion
        for parent in channels {
            var ids: [UUID] = []
            for (slot, source) in parent.allSources.enumerated() {
                var child = parent
                child.id = slot == 0 ? parent.id : routingChildID(parent.id, role: "channel-source", slot: slot)
                guard channelParents[child.id] == nil else {
                    throw SessionError.invalid("Expanded input identifiers collide. Recreate the affected input group.")
                }
                child.source = source
                child.additionalSources = []
                lowered.channels.append(child)
                channelParents[child.id] = parent.id
                ids.append(child.id)
            }
            channelGroups[parent.id] = ids
        }
        for parent in buses {
            var ids: [UUID] = []
            for (slot, destination) in parent.allOutputs.enumerated() {
                var child = parent
                child.id = slot == 0 ? parent.id : routingChildID(parent.id, role: "mix-output", slot: slot)
                guard busParents[child.id] == nil else {
                    throw SessionError.invalid("Expanded mix identifiers collide. Recreate the affected mix.")
                }
                child.deviceUID = destination.deviceUID
                child.channelOffset = destination.channelOffset
                child.additionalOutputs = []
                lowered.buses.append(child)
                busParents[child.id] = parent.id
                ids.append(child.id)
            }
            busGroups[parent.id] = ids
        }
        let (routeCount, overflow) = lowered.channels.count.multipliedReportingOverflow(by: lowered.buses.count)
        guard !overflow else { throw SessionError.invalid("The expanded routing matrix exceeds this machine's addressable size.") }
        // Every visible route must exist before expansion (validated above).
        // Do not reserve enormous virtual address ranges speculatively.
        if routeCount < 65_536 { lowered.sends.reserveCapacity(routeCount) }
        for send in sends {
            guard let children = channelGroups[send.channelID], let outputs = busGroups[send.busID] else {
                throw SessionError.invalid("A grouped route refers to a missing input or mix.")
            }
            for channel in children {
                for bus in outputs {
                    var copy = send
                    copy.channelID = channel; copy.busID = bus
                    lowered.sends.append(copy)
                }
            }
        }
        return ExpandedRouting(session: try lowered.validated(), channelParents: channelParents, busParents: busParents)
    }
}

private func routingChildID(_ parent: UUID, role: String, slot: Int) -> UUID {
    var namespace = parent.uuid
    var data = withUnsafeBytes(of: &namespace) { Data($0) }
    data.append(contentsOf: "ravelink.\(role).\(slot)".utf8)
    var bytes = Array(Insecure.SHA1.hash(data: data).prefix(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x50
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    return UUID(uuid: (bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
                       bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]))
}
