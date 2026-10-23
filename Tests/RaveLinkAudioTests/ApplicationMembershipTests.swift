import Testing
@testable import RaveLinkAudio

@Suite struct ApplicationMembershipTests {
    @Test func initiallyAbsentExcludedApplicationRemainsWatched() {
        let ids: Set<String> = ["com.example.captured", "com.example.excluded"]
        let initial = applicationMemberships(bundleIDs: ids,
            processes: [(11, "com.example.captured", 101), (90, "com.other.app", 901)], excludingPID: 999)
        #expect(initial == ["com.example.captured": [11], "com.example.excluded": []])
        let afterLaunch = applicationMemberships(bundleIDs: ids,
            processes: [(11, "com.example.captured", 101), (22, "com.example.excluded", 202)], excludingPID: 999)
        #expect(afterLaunch != initial)
    }
    @Test func restartAdditionalProcessAndExitChangeExclusions() {
        let ids: Set<String> = ["com.example.excluded"]
        let before = applicationMemberships(bundleIDs: ids, processes: [(22, "com.example.excluded", 202)], excludingPID: 999)
        let restart = applicationMemberships(bundleIDs: ids, processes: [(23, "com.example.excluded", 203)], excludingPID: 999)
        let additional = applicationMemberships(bundleIDs: ids, processes: [(22, "com.example.excluded", 202), (24, "com.example.excluded", 204)], excludingPID: 999)
        let exited = applicationMemberships(bundleIDs: ids, processes: [], excludingPID: 999)
        #expect(restart != before && additional != before && exited != before)
    }
    @Test func orderingDuplicatesOwnProcessAndUnrelatedAppsDoNotChangeMembership() {
        let ids: Set<String> = ["com.example.excluded"]
        let initial = applicationMemberships(bundleIDs: ids, processes: [(22, "com.example.excluded", 202), (23, "com.example.excluded", 203)], excludingPID: 999)
        let unchanged = applicationMemberships(bundleIDs: ids, processes: [(23, "com.example.excluded", 203), (22, "com.example.excluded", 202),
            (22, "com.example.excluded", 202), (99, "com.example.excluded", 999), (33, "com.other", 303)], excludingPID: 999)
        #expect(initial == unchanged)
    }
}
