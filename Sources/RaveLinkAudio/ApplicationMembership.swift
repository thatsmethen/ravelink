import Foundation

/// Exact bundle-ID membership used by the current tap implementation. Keep
/// empty entries: a previously idle excluded app becoming active is a change.
func applicationMemberships(bundleIDs: Set<String>, processes: [(id: UInt32, bundle: String, pid: Int32)], excludingPID: Int32) -> [String: [UInt32]] {
    var result = Dictionary(uniqueKeysWithValues: bundleIDs.map { ($0, Set<UInt32>()) })
    for process in processes where process.pid != excludingPID && bundleIDs.contains(process.bundle) {
        result[process.bundle, default: []].insert(process.id)
    }
    return result.mapValues { $0.sorted() }
}
