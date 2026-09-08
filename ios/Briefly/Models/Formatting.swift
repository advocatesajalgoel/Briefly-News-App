import Foundation

/// Human-readable publication times.
///
/// News needs "22 minutes ago" for something breaking and "5 Sept" for something
/// from last week; a single formatter cannot do both well, so this switches on
/// the age of the item.
enum RelativeTime {
    #if canImport(Darwin)
    private static let relative: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        formatter.dateTimeStyle = .numeric
        return formatter
    }()
    #endif

    /// Plain phrasing used where `RelativeDateTimeFormatter` is unavailable.
    ///
    /// This exists so the model and formatting layer compiles and is testable on
    /// Linux, which is what lets the whole Codable surface be verified on a free
    /// CI runner without a Mac. On Apple platforms the localised formatter above
    /// is always the one used.
    private static func plainRelative(seconds: TimeInterval) -> String {
        if seconds < 3600 {
            let minutes = max(1, Int(seconds / 60))
            return minutes == 1 ? "1 minute ago" : "\(minutes) minutes ago"
        }
        let hours = Int(seconds / 3600)
        return hours == 1 ? "1 hour ago" : "\(hours) hours ago"
    }

    private static let sameYear: DateFormatter = {
        let formatter = DateFormatter()
        formatter.setLocalizedDateFormatFromTemplate("d MMM")
        return formatter
    }()

    private static let otherYear: DateFormatter = {
        let formatter = DateFormatter()
        formatter.setLocalizedDateFormatFromTemplate("d MMM yyyy")
        return formatter
    }()

    static func string(for date: Date?, now: Date = Date()) -> String {
        guard let date else { return "" }
        let interval = now.timeIntervalSince(date)

        if interval < 60 { return "Just now" }
        if interval < 60 * 60 * 22 {
            #if canImport(Darwin)
            return relative.localizedString(for: date, relativeTo: now)
            #else
            return plainRelative(seconds: interval)
            #endif
        }
        let calendar = Calendar.current
        if calendar.isDate(date, equalTo: now, toGranularity: .year) {
            return sameYear.string(from: date)
        }
        return otherYear.string(from: date)
    }

    /// Short form for dense rows: "22m", "3h", "5 Sept".
    static func compact(for date: Date?, now: Date = Date()) -> String {
        guard let date else { return "" }
        let interval = now.timeIntervalSince(date)
        if interval < 60 { return "now" }
        if interval < 3600 { return "\(Int(interval / 60))m" }
        if interval < 86_400 { return "\(Int(interval / 3600))h" }
        if interval < 86_400 * 7 { return "\(Int(interval / 86_400))d" }
        return sameYear.string(from: date)
    }
}

/// Durations for the audio player.
enum TimeFormatting {
    /// `m:ss` under an hour, `h:mm:ss` above it.
    static func formatted(seconds: Int) -> String {
        let total = max(0, seconds)
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let secs = total % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, secs)
        }
        return String(format: "%d:%02d", minutes, secs)
    }

    /// "About 8 min" — used on episode rows where precision is noise.
    static func approximate(seconds: Int) -> String {
        let minutes = Int((Double(max(0, seconds)) / 60.0).rounded())
        if minutes < 1 { return "Under a minute" }
        return "About \(minutes) min"
    }
}

/// Word counting, mirroring `backend/app/text/wordcount.py`.
///
/// The backend is the authority and the database refuses to store an over-length
/// summary, so this is a display-side assertion rather than a second
/// implementation of the rule: it lets the card show the count and lets the test
/// suite prove the bundled data respects the cap.
enum WordCount {
    static let cardLimit = 30

    static func count(_ text: String) -> Int {
        var count = 0
        var inWord = false
        for character in text.unicodeScalars {
            let isWordScalar = CharacterSet.alphanumerics.contains(character)
                || character == "'" || character == "\u{2019}" || character == "."
            if isWordScalar {
                if !inWord, CharacterSet.alphanumerics.contains(character) {
                    count += 1
                    inWord = true
                }
            } else {
                inWord = false
            }
        }
        return count
    }

    static func isWithinCardLimit(_ text: String) -> Bool {
        count(text) <= cardLimit
    }
}
