import SwiftUI
import RaveLinkAudio

struct EngineDiagnosticsView: View {
    @ObservedObject var audio: EngineClient
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Engine diagnostics").font(.title2.weight(.semibold))
            LabeledContent("State", value: audio.starting ? "Connecting" : (audio.running ? "Running" : "Stopped"))
            Divider()
            LabeledContent("Captured frames", value: String(audio.diagnostics.capturedFrames))
            LabeledContent("Rendered frames", value: String(audio.diagnostics.renderedFrames))
            LabeledContent("Input overflow frames", value: String(audio.diagnostics.droppedFrames))
            LabeledContent("Buffer underrun frames", value: String(audio.diagnostics.underrunFrames))
            LabeledContent("Oversized device blocks", value: String(audio.diagnostics.oversizedBlocks))
            Text("Counters combine active paths in this run. Increasing overflow or underrun counts can explain clicks or gaps. Reduce active sources or align device sample rates, then start again.").font(.caption).foregroundStyle(.secondary)
            if let error = audio.errorMessage { Text(error).font(.callout).foregroundStyle(.orange).textSelection(.enabled) }
            HStack { Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.defaultAction).buttonStyle(AccentButtonStyle()) }
        }.padding(28).frame(width: 500)
    }
}
