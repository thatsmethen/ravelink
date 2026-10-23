// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "RaveLink",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "RaveLink", targets: ["RaveLinkApp"]),
        .executable(name: "RaveLinkEngine", targets: ["RaveLinkEngine"]),
        .executable(name: "RaveLinkPluginHost", targets: ["RaveLinkPluginHost"]),
        .library(name: "RaveLinkCore", targets: ["RaveLinkCore"]),
        .library(name: "RaveLinkAudio", targets: ["RaveLinkAudio"])
    ],
    targets: [
        .target(name: "RaveLinkCore"),
        .executableTarget(name: "RaveLinkPluginHost"),
        .executableTarget(name: "RaveLinkEngine", dependencies: ["RaveLinkAudio", "RaveLinkCore"]),
        .target(name: "RaveLinkRealtime", publicHeadersPath: "include"),
        .target(name: "RaveLinkAudioUnitBridge", publicHeadersPath: "include", cSettings: [.unsafeFlags(["-fno-objc-arc"])], linkerSettings: [.linkedFramework("AVFoundation"), .linkedFramework("AudioToolbox")]),
        .target(name: "RaveLinkAudio", dependencies: ["RaveLinkCore", "RaveLinkRealtime", "RaveLinkAudioUnitBridge"]),
        .executableTarget(name: "RaveLinkApp", dependencies: ["RaveLinkCore", "RaveLinkAudio"]),
        .testTarget(name: "RaveLinkCoreTests", dependencies: ["RaveLinkCore"]),
        .testTarget(name: "RaveLinkAudioTests", dependencies: ["RaveLinkAudio", "RaveLinkCore", "RaveLinkRealtime"])
    ],
    swiftLanguageModes: [.v5]
)
