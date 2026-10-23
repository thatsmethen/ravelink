import SwiftUI
import RaveLinkCore
import RaveLinkAudio

private let canvas = Color(red: 0.065, green: 0.075, blue: 0.095)
private let panel = Color(red: 0.105, green: 0.12, blue: 0.15)
private let accent = Color(red: 0.42, green: 0.87, blue: 0.75)

struct StudioView: View {
    @ObservedObject var studio: StudioModel
    @ObservedObject var audio: AudioCoordinator
    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            HStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("YOUR STUDIO").font(.system(size: 10, weight: .semibold, design: .monospaced)).foregroundStyle(accent)
                            Text("Every source. Every destination.").font(.system(size: 22, weight: .semibold))
                        }
                        Spacer()
                        Button { studio.showingInput = true } label: { Label("Add input", systemImage: "plus") }.buttonStyle(.borderedProminent).tint(accent).foregroundStyle(.black)
                    }.padding(24)
                    matrix
                }
                if let id = studio.selectedChannel, let index = studio.session.channels.firstIndex(where: { $0.id == id }) {
                    Divider()
                    effects(index: index).frame(width: 265)
                }
            }
            Divider()
            footer
        }
        .background(canvas).tint(accent)
        .sheet(isPresented: $studio.showingInput) { InputSheet(studio: studio, audio: audio) }
        .sheet(isPresented: $studio.showingMix) { MixSheet(studio: studio, audio: audio) }
        .sheet(isPresented: $studio.showingSettings) { setupInfo }
        .alert("Studio needs attention", isPresented: Binding(get: { studio.notice != nil }, set: { if !$0 { studio.notice = nil } })) {
            Button("OK") { studio.notice = nil }
        } message: { Text(studio.notice ?? "") }
    }
    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "waveform.path").font(.system(size: 25, weight: .medium)).foregroundStyle(accent)
            Text("ravelink").font(.system(size: 22, weight: .semibold, design: .rounded))
            Rectangle().fill(.white.opacity(0.12)).frame(width: 1, height: 22).padding(.horizontal, 8)
            TextField("Studio name", text: $studio.session.name).textFieldStyle(.plain).frame(maxWidth: 220)
            Spacer()
            Menu {
                Button("Import studio…") { studio.importSession() }
                Button("Export studio…") { studio.exportSession() }
                Divider()
                Button("Audio setup…") { studio.showingSettings = true }
                Button("Refresh devices") { audio.refreshDevices() }
            } label: { Image(systemName: "ellipsis.circle").font(.title3) }.menuStyle(.borderlessButton).frame(width: 34).help("Studio options")
            Button { studio.toggleAudio() } label: {
                Label(audio.running ? "Stop audio" : "Start audio", systemImage: audio.running ? "stop.fill" : "play.fill").frame(width: 105)
            }.buttonStyle(.borderedProminent).tint(audio.running ? .red.opacity(0.75) : accent).foregroundStyle(audio.running ? .white : .black)
        }.padding(.horizontal, 24).padding(.top, 30).padding(.bottom, 18)
    }
    private var matrix: some View {
        ScrollView([.horizontal, .vertical]) {
            LazyVStack(alignment: .leading, spacing: 1) {
                HStack(alignment: .top, spacing: 1) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("INPUTS").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                        Text("Choose where each input goes").font(.caption).foregroundStyle(.secondary)
                    }.frame(width: 260, height: 148, alignment: .leading).padding(.horizontal, 18)
                    ForEach(studio.session.buses.indices, id: \.self) { index in busHeader(index) }
                    Button { studio.showingMix = true } label: { Image(systemName: "plus").frame(width: 42, height: 42) }.buttonStyle(.bordered).help("Add mix").padding(16)
                }
                if studio.session.channels.isEmpty {
                    VStack(spacing: 14) {
                        Image(systemName: "waveform.badge.plus").font(.system(size: 38)).foregroundStyle(accent)
                        Text("Build your first mix").font(.title2.weight(.semibold))
                        Text("Add a microphone, an app, or system audio.\nThen turn on the mixes that should hear it.").foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Button("Add your first input") { studio.showingInput = true }.buttonStyle(.borderedProminent).tint(accent).foregroundStyle(.black)
                        Button("Set up virtual outputs") { studio.showingSettings = true }.buttonStyle(.plain).foregroundStyle(.secondary)
                    }.frame(width: max(820, CGFloat(studio.session.buses.count * 196 + 296)), height: 330)
                } else {
                    ForEach(studio.session.channels.indices, id: \.self) { index in channelRow(index) }
                    Button { studio.showingInput = true } label: { Label("Add input", systemImage: "plus").frame(width: 260, height: 50, alignment: .leading) }.buttonStyle(.plain).foregroundStyle(accent).padding(.horizontal, 18)
                }
            }.padding(.horizontal, 24).padding(.bottom, 24)
        }
    }
    private func busHeader(_ index: Int) -> some View {
        let bus = studio.session.buses[index]
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: index == 0 ? "headphones" : "antenna.radiowaves.left.and.right").foregroundStyle(accent)
                TextField("Mix name", text: $studio.session.buses[index].name).textFieldStyle(.plain).font(.headline)
                Menu {
                    Button(bus.muted ? "Unmute mix" : "Mute mix") { studio.session.buses[index].muted.toggle() }
                    Button("Remove mix", role: .destructive) { studio.session.removeBus(bus.id) }
                } label: { Image(systemName: "ellipsis") }.menuStyle(.borderlessButton).frame(width: 18)
            }
            Picker("Output", selection: $studio.session.buses[index].deviceUID) {
                Text("Choose output…").tag(nil as String?)
                ForEach(audio.devices.filter { $0.outputChannels > 0 }) { Text($0.name).tag(Optional($0.id)) }
                if let uid = bus.deviceUID, !audio.devices.contains(where: { $0.id == uid }) { Text("Missing device").tag(Optional(uid)) }
            }.labelsHidden().frame(maxWidth: .infinity).accessibilityLabel("\(bus.name) output")
            HStack(spacing: 6) {
                Button { studio.session.buses[index].muted.toggle() } label: { Image(systemName: bus.muted ? "speaker.slash.fill" : "speaker.wave.2.fill").foregroundStyle(bus.muted ? .orange : .secondary) }.buttonStyle(.plain).accessibilityLabel("Mute \(bus.name)")
                Slider(value: $studio.session.buses[index].gainDB, in: -60...12).accessibilityLabel("\(bus.name) master level")
                Text(db(bus.gainDB)).font(.system(size: 10, design: .monospaced)).frame(width: 38)
            }
            LevelMeter(level: audio.busMeters[bus.id] ?? 0, active: audio.running && !bus.muted)
            if let d = audio.devices.first(where: { $0.id == bus.deviceUID }), d.outputChannels > 2 {
                Picker("Pair", selection: $studio.session.buses[index].channelOffset) {
                    ForEach(Array(stride(from: 0, to: d.outputChannels - 1, by: 2)), id: \.self) { offset in Text("\(offset + 1)–\(offset + 2)").tag(offset) }
                }.font(.caption)
            }
        }.padding(16).frame(width: 196, height: 148, alignment: .top).background(panel)
    }
    private func channelRow(_ index: Int) -> some View {
        let channel = studio.session.channels[index]
        return HStack(spacing: 1) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    Image(systemName: sourceIcon(channel.source.kind)).font(.title3).foregroundStyle(accent).frame(width: 24)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(channel.name).font(.headline).lineLimit(1)
                        Text(sourceDescription(channel)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    Menu {
                        Button("Input settings") { studio.selectedChannel = channel.id }
                        Button("Remove input", role: .destructive) { studio.removeChannel(channel.id) }
                    } label: { Image(systemName: "ellipsis") }.menuStyle(.borderlessButton).frame(width: 18)
                }
                LevelMeter(level: audio.channelMeters[channel.id] ?? 0, active: audio.running && !channel.muted)
                HStack(spacing: 8) {
                    Button(channel.muted ? "Muted" : "Mute") { studio.session.channels[index].muted.toggle() }.tint(channel.muted ? .orange : .gray)
                    Button("Solo") { studio.session.channels[index].solo.toggle() }.tint(channel.solo ? accent : .gray)
                    Spacer()
                    Button { studio.selectedChannel = studio.selectedChannel == channel.id ? nil : channel.id } label: { Label("Effects", systemImage: "slider.horizontal.3") }
                }.buttonStyle(.bordered).controlSize(.small)
            }.padding(18).frame(width: 296, height: 140).background(studio.selectedChannel == channel.id ? panel.opacity(1.5) : panel)
            ForEach(studio.session.buses) { bus in
                if let route = studio.session.sends.firstIndex(where: { $0.channelID == channel.id && $0.busID == bus.id }) { routeCell(route, channel: channel, bus: bus) }
                else { Color.clear.frame(width: 196, height: 140) }
            }
        }
    }
    private func routeCell(_ index: Int, channel: MixerChannel, bus: MixBus) -> some View {
        let send = studio.session.sends[index]
        return VStack(spacing: 12) {
            HStack {
                Toggle(isOn: Binding(get: { !studio.session.sends[index].muted }, set: { studio.session.sends[index].muted = !$0 })) { Text(send.muted ? "Off" : "On").font(.caption.weight(.medium)) }.toggleStyle(.switch).controlSize(.small)
                    .accessibilityLabel("Route \(channel.name) to \(bus.name)")
                Spacer()
                Text(db(send.gainDB)).font(.system(size: 12, design: .monospaced)).foregroundStyle(send.muted ? .secondary : accent)
            }
            Slider(value: $studio.session.sends[index].gainDB, in: -60...12).disabled(send.muted).accessibilityLabel("\(channel.name) level in \(bus.name)")
            HStack {
                Text("L").font(.system(size: 9, weight: .medium))
                Slider(value: $studio.session.sends[index].pan, in: -1...1).disabled(send.muted).accessibilityLabel("\(channel.name) pan in \(bus.name)")
                Text("R").font(.system(size: 9, weight: .medium))
            }.foregroundStyle(.secondary).opacity(0.7)
        }.padding(18).frame(width: 196, height: 140).background(send.muted ? panel.opacity(0.4) : panel)
    }
    private func effects(index: Int) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack {
                    Text("INPUT SETTINGS").font(.system(size: 11, weight: .semibold)).foregroundStyle(accent)
                    Spacer()
                    Button { studio.selectedChannel = nil } label: { Image(systemName: "xmark") }.buttonStyle(.plain).help("Close input settings")
                }
                TextField("Input name", text: $studio.session.channels[index].name).font(.title2).textFieldStyle(.plain)
                Text("Applied before this input reaches your mixes.").font(.caption).foregroundStyle(.secondary)
                effectSlider("Input gain", value: $studio.session.channels[index].effects.gainDB, range: -60...24, suffix: "dB")
                effectSlider("High-pass filter", value: $studio.session.channels[index].effects.highPassHz, range: 0...1000, suffix: "Hz")
                effectSlider("Noise gate", value: $studio.session.channels[index].effects.gateThresholdDB, range: -100...0, suffix: "dB")
                effectSlider("Compressor threshold", value: $studio.session.channels[index].effects.compressorThresholdDB, range: -60...0, suffix: "dB")
                effectSlider("Compressor ratio", value: $studio.session.channels[index].effects.compressorRatio, range: 1...20, suffix: ":1")
                Button("Reset effects") { studio.session.channels[index].effects = .init() }.buttonStyle(.bordered)
                Divider()
                Text("Stereo pairs").font(.headline)
                Stepper("First channel: \(studio.session.channels[index].source.channelOffset + 1)", value: $studio.session.channels[index].source.channelOffset, in: 0...4094, step: 2).font(.caption)
                Text("Select the first channel of a stereo pair for multichannel hardware. Mono inputs are duplicated to both sides.").font(.caption).foregroundStyle(.secondary)
            }.padding(22)
        }.background(panel.opacity(0.6))
    }
    private func effectSlider(_ title: String, value: Binding<Float>, range: ClosedRange<Float>, suffix: String) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack { Text(title).font(.callout); Spacer(); Text("\(Int(value.wrappedValue)) \(suffix)").font(.system(size: 11, design: .monospaced)).foregroundStyle(accent) }
            Slider(value: value, in: range).accessibilityLabel(title)
        }
    }
    private var footer: some View {
        HStack(spacing: 8) {
            Circle().fill(audio.running ? accent : .gray).frame(width: 6, height: 6)
            Text(audio.running ? "Audio running" : "Audio stopped").font(.caption.weight(.medium))
            if let error = audio.errorMessage { Text(error).font(.caption).foregroundStyle(.orange).lineLimit(2) }
            Spacer()
            Text("\(studio.session.channels.count) inputs  ·  \(studio.session.buses.count) mixes").font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
            Button { studio.showingSettings = true } label: { Image(systemName: "questionmark.circle") }.buttonStyle(.plain).help("Audio setup")
        }.padding(.horizontal, 24).padding(.vertical, 14)
    }
    private var setupInfo: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Connect your studio").font(.title2.weight(.semibold))
            Text("Listen locally").font(.headline)
            Text("Select your headphones or audio interface as the Personal mix output. Add an input, enable its Personal route, then start audio.")
            Text("Send a mix to another app").font(.headline)
            Text("Select a RaveLink virtual device or BlackHole as the Stream output. In OBS, Discord or your recording app, select that same device as the microphone. Each independent mix needs its own virtual device or channel pair.")
            Text("Application audio").font(.headline)
            Text("macOS may request permission to capture system audio. If a source is missing, open it and play audio, then refresh devices. A missing or denied source appears as an error.")
            Link("Virtual device build and installation guide", destination: URL(string: "https://github.com/thatsmethen/ravelink/blob/main/docs/virtual-devices.md")!)
            HStack { Spacer(); Button("Done") { studio.showingSettings = false }.keyboardShortcut(.defaultAction) }
        }.font(.callout).frame(width: 520).padding(30)
    }
    private func sourceDescription(_ channel: MixerChannel) -> String {
        switch channel.source.kind {
        case .device: return audio.devices.first(where: { $0.id == channel.source.deviceUID })?.name ?? "Device unavailable"
        case .application: return channel.source.bundleID ?? "Application"
        case .system: return "System audio"
        case .tone: return "Test tone · 440 Hz"
        }
    }
}
func sourceIcon(_ kind: SourceKind) -> String {
    switch kind { case .device: return "mic.fill"; case .application: return "app.dashed"; case .system: return "desktopcomputer"; case .tone: return "waveform" }
}
func db(_ value: Float) -> String { value <= -60 ? "−∞" : String(format: "%+.0f dB", value) }
struct LevelMeter: View {
    let level: Float
    let active: Bool
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(.white.opacity(0.08))
                Capsule().fill(level > 0.95 ? Color.orange : accent).frame(width: geo.size.width * CGFloat(active && level.isFinite ? min(1, max(0, (20 * log10(max(level, 0.001)) + 60) / 60)) : 0))
            }
        }.frame(height: 4).accessibilityLabel("Audio level").accessibilityValue(active ? "\(Int(20 * log10(max(level.isFinite ? level : 0, 0.001)))) decibels" : "Stopped")
    }
}
