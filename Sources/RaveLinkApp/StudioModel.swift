import AppKit
import Combine
import RaveLinkCore
import RaveLinkAudio

@MainActor final class StudioModel: ObservableObject {
    @Published var session: MixerSession { didSet { scheduleSave(previous: oldValue) } }
    @Published var selectedChannel: UUID?
    @Published var notice: String?
    @Published var saveStatus = "Saved locally"
    @Published var showingInput = false
    @Published var showingMix = false
    @Published var sourceTarget: UUID?
    @Published var sourceReplacement: Int?
    @Published var outputTarget: UUID?
    @Published var showingOutputs = false
    @Published var showingSettings = false
    @Published var showingDiagnostics = false
    let audio = AudioCoordinator()
    private let store = SessionStore.standard
    private var pending: Task<Void, Never>?
    private var allowsOverwrite = true
    init() {
        if FileManager.default.fileExists(atPath: store.url.path) {
            do { session = try store.load() }
            catch {
                session = .initial
                let failure = error.localizedDescription
                let backup = store.url.deletingLastPathComponent().appendingPathComponent("unreadable-\(UUID().uuidString).json")
                do {
                    try FileManager.default.copyItem(at: store.url, to: backup)
                    notice = "Your saved studio could not be opened. A copy has been preserved at \(backup.path). \(failure)"
                } catch {
                    allowsOverwrite = false
                    saveStatus = "Recovery needed · use Export studio"
                    notice = "Your saved studio could not be opened or backed up. Automatic saving is disabled to preserve it. Use Export studio to save changes elsewhere. \(failure)"
                }
            }
        } else { session = .initial }
        audio.refreshDevices()
    }
    private func audioSnapshot(_ value: MixerSession) -> MixerSession {
        var snapshot = value
        snapshot.name = "Studio"
        for index in snapshot.channels.indices { snapshot.channels[index].name = "Input" }
        for index in snapshot.buses.indices { snapshot.buses[index].name = "Mix" }
        return snapshot
    }
    private func scheduleSave(previous: MixerSession) {
        pending?.cancel()
        if allowsOverwrite { saveStatus = "Saving…" }
        if audio.running && audioSnapshot(previous) != audioSnapshot(session) {
            do { try audio.update(session: audioSnapshot(session)) }
            catch { notice = error.localizedDescription }
        }
        pending = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled, let self, allowsOverwrite else { return }
            do {
                _ = try session.validated()
                try store.save(session)
                saveStatus = "Saved locally"
            } catch { saveStatus = "Not saved: \(error.localizedDescription)" }
        }
    }
    func flush() { pending?.cancel(); guard allowsOverwrite else { return }; do { try store.save(session) } catch { notice = error.localizedDescription } }
    func toggleAudio() {
        if audio.running || audio.starting { audio.stop() }
        else { do { try audio.start(session: session) } catch { notice = error.localizedDescription } }
    }
    func beginInput(target: UUID? = nil, replacing: Int? = nil) {
        sourceTarget = target; sourceReplacement = replacing; showingInput = true
    }
    func add(_ input: MixerChannel) {
        if let target = sourceTarget, let i = session.channels.firstIndex(where: { $0.id == target }) {
            if let slot = sourceReplacement {
                if slot == 0 { session.channels[i].source = input.source }
                else if session.channels[i].additionalSources.indices.contains(slot - 1) { session.channels[i].additionalSources[slot - 1] = input.source }
            } else { session.channels[i].additionalSources.append(input.source) }
            selectedChannel = target
        } else { session.addChannel(input); selectedChannel = nil }
    }
    func add(_ bus: MixBus) { session.addBus(bus) }
    func removeChannel(_ id: UUID) { if selectedChannel == id { selectedChannel = nil }; session.removeChannel(id) }
    func exportSession() {
        let panel = NSSavePanel(); panel.nameFieldStringValue = session.name + ".ravelink.json"; panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try SessionStore(url: url).save(session) } catch { notice = error.localizedDescription }
    }
    func importSession() {
        let panel = NSOpenPanel(); panel.allowedContentTypes = [.json]; panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let imported = try SessionStore(url: url).load()
            audio.stop(); session = imported; selectedChannel = nil
        } catch { notice = "Could not import studio. \(error.localizedDescription)" }
    }
}
