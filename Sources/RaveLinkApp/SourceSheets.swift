import SwiftUI
import RaveLinkCore
import RaveLinkAudio

struct InputSheet: View {
    @ObservedObject var studio: StudioModel
    @ObservedObject var audio: AudioCoordinator
    @Environment(\.dismiss) private var dismiss
    @State private var kind: SourceKind = .device
    @State private var name = ""
    @State private var deviceUID = ""
    @State private var bundleID = ""
    private var valid: Bool { (kind == .device && !deviceUID.isEmpty) || (kind == .application && !bundleID.isEmpty) || kind == .system || kind == .tone }
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack { Text("Add an input").font(.title2.weight(.semibold)); Spacer(); Button { audio.refreshDevices() } label: { Label("Refresh", systemImage: "arrow.clockwise") } }
            Text("Bring audio into your studio, then choose which mixes can hear it.").foregroundStyle(.secondary)
            Picker("Source", selection: $kind) {
                Text("Device").tag(SourceKind.device)
                Text("Application").tag(SourceKind.application)
                Text("System").tag(SourceKind.system)
                Text("Test tone").tag(SourceKind.tone)
            }.pickerStyle(.segmented)
            Group {
                switch kind {
                case .device:
                    Picker("Audio device", selection: $deviceUID) {
                        Text("Choose an input…").tag("")
                        ForEach(audio.devices.filter { $0.inputChannels > 0 }) { Text("\($0.name) (\($0.inputChannels) ch)").tag($0.id) }
                    }
                    Text("Microphones, interfaces and virtual devices are supported. Use Input settings to select a different stereo pair.").font(.caption).foregroundStyle(.secondary)
                case .application:
                    Picker("Application", selection: $bundleID) {
                        Text("Choose an application…").tag("")
                        ForEach(audio.applications) { Text($0.name).tag($0.id) }
                    }
                    Text("Open an app and play audio if it is missing here. macOS will ask for audio capture permission when needed.").font(.caption).foregroundStyle(.secondary)
                case .system:
                    Label("All system audio", systemImage: "desktopcomputer").font(.headline)
                    Text("Captures applications outside dedicated app inputs. RaveLink’s own output is excluded to prevent feedback.").font(.caption).foregroundStyle(.secondary)
                case .tone:
                    Label("440 Hz calibration tone", systemImage: "waveform").font(.headline)
                    Text("A quiet signal for checking your route. Starts only after you enable a mix and start audio.").font(.caption).foregroundStyle(.secondary)
                }
            }.frame(minHeight: 80, alignment: .top)
            TextField("Name (optional)", text: $name).textFieldStyle(.roundedBorder)
            HStack { Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction); Spacer(); Button("Add input") { add() }.buttonStyle(.borderedProminent).disabled(!valid).keyboardShortcut(.defaultAction) }
        }.padding(30).frame(width: 560)
    }
    private func add() {
        let suggested: String
        switch kind {
        case .device: suggested = audio.devices.first { $0.id == deviceUID }?.name ?? "Input"
        case .application: suggested = audio.applications.first { $0.id == bundleID }?.name ?? "Application"
        case .system: suggested = "System audio"
        case .tone: suggested = "Test tone"
        }
        studio.add(MixerChannel(name: name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? suggested : name, source: InputSource(kind: kind, deviceUID: deviceUID.isEmpty ? nil : deviceUID, bundleID: bundleID.isEmpty ? nil : bundleID)))
        dismiss()
    }
}
struct MixSheet: View {
    @ObservedObject var studio: StudioModel
    @ObservedObject var audio: AudioCoordinator
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var deviceUID: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Add a mix").font(.title2.weight(.semibold))
            Text("Give a destination its own balance of your inputs.").foregroundStyle(.secondary)
            TextField("Mix name", text: $name).textFieldStyle(.roundedBorder)
            Picker("Output", selection: $deviceUID) {
                Text("Choose later").tag(nil as String?)
                ForEach(audio.devices.filter { $0.outputChannels > 0 }) { Text($0.name).tag(Optional($0.id)) }
            }
            Text("For a streaming or chat app, choose a virtual device such as RaveLink Stream or BlackHole. For listening, choose your headphones.").font(.caption).foregroundStyle(.secondary)
            HStack { Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction); Spacer(); Button("Add mix") { studio.add(MixBus(name: name, deviceUID: deviceUID)); dismiss() }.buttonStyle(.borderedProminent).disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).keyboardShortcut(.defaultAction) }
        }.padding(30).frame(width: 500)
    }
}
