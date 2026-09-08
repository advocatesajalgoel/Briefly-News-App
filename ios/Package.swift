// swift-tools-version: 5.9
import PackageDescription

// BrieflyCore — the parts of the app that depend on nothing but Foundation.
//
// Why this exists: compiling a SwiftUI app needs Xcode and a Mac. The models,
// the Codable layer, the word counter and the formatters do not — they are
// plain Swift, and they are also where the subtle bugs live (a mis-mapped
// coding key breaks the whole feed). Exposing them as a SwiftPM package means
// they get *really compiled and really tested* on a free Linux CI runner, in
// seconds, with no Mac and no Apple account anywhere in the loop.
//
//   swift build          # compiles the model layer
//   swift test           # runs the Codable contract tests against the snapshot
//
// The Xcode project compiles the same files as part of the app target; nothing
// is duplicated.
let package = Package(
    name: "BrieflyCore",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "BrieflyCore", targets: ["BrieflyCore"])
    ],
    targets: [
        .target(
            name: "BrieflyCore",
            path: "Briefly/Models"
        ),
        .testTarget(
            name: "BrieflyCoreTests",
            dependencies: ["BrieflyCore"],
            path: "BrieflyCoreTests"
        )
    ]
)
