// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "RaveLink",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "RaveLink", targets: ["RaveLinkApp"]),
        .library(name: "RaveLinkCore", targets: ["RaveLinkCore"]),
        .library(name: "RaveLinkAudio", targets: ["RaveLinkAudio"])
    ],
    targets: [
        .target(name: "RaveLinkCore"),
        .target(name: "RaveLinkAudio", dependencies: ["RaveLinkCore"]),
        .executableTarget(name: "RaveLinkApp", dependencies: ["RaveLinkCore", "RaveLinkAudio"]),
        .testTarget(name: "RaveLinkCoreTests", dependencies: ["RaveLinkCore"])
    ],
    swiftLanguageModes: [.v5]
)
