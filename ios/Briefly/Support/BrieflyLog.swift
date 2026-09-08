import Foundation
import os

/// Namespaced loggers. Using `Logger` rather than `print` means these show up in
/// Console.app with the subsystem filter and cost nothing in release builds.
enum BrieflyLog {
    static let subsystem = "com.briefly.app"

    static let networking = Logger(subsystem: subsystem, category: "networking")
    static let feed = Logger(subsystem: subsystem, category: "feed")
    static let audio = Logger(subsystem: subsystem, category: "audio")
    static let storage = Logger(subsystem: subsystem, category: "storage")
}
