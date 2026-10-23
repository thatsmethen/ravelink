import AppKit
import Combine
import RaveLinkCore
import RaveLinkAudio

@MainActor final class StudioModel: ObservableObject {
    @Published var session: MixerSession { didSet { scheduleSave() } }
    @Published var selectedChannel: UUID?
    @Published var notice: String?
    @Published var showingInput = false
    @Published var showingMix = false
    @Published var showingSettings = false
    let audio = AudioCoordinator()
    private let store = SessionStore.standard
    private var pending: Task<Void, Never>?
    init() {
        if FileManager.default.fileExists(atPath: store.url.path) {
            do { session = try store.load() }
            catch { session = .initial; let backup = store.url.deletingLastPathComponent().appendingPathComponent("unreadable-\(UUID().uuidString).json"); try? FileManager.default.copyItem(at: store.url, to: backup); notice = "Your saved studio could not be opened. A copy has been preserved at \(backup.path). \(error.localizedDescription)" }
        } else { session = .initial }
        audio.refreshDevices()
    }
    private func scheduleSave() {
        pending?.cancel()
        pending = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled, let self else { return }
            do {
                _ = try session.validated()
                if audio.running { try audio.update(session: session) }
                try store.save(session)
            } catch { notice = error.localizedDescription }
        }
    }
    func flush() { pending?.cancel(); do { try store.save(session) } catch { notice = error.localizedDescription } }
    func toggleAudio() {
        if audio.running { audio.stop() }
        else { do { try audio.start(session: session) } catch { notice = error.localizedDescription } }
    }
    func add(_ input: MixerChannel) { session.addChannel(input); selectedChannel = input.id }
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
