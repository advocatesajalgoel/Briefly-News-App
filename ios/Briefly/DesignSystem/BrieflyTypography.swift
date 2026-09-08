import SwiftUI

/// Type scale.
///
/// Headlines are set in a serif, body copy in the system sans. That pairing is
/// what makes a card read as an edited page rather than a feed item, and it is
/// the most recognisable part of Briefly's identity.
///
/// Every style is built on a `Font.TextStyle`, so all of it scales with Dynamic
/// Type. Nothing here uses a fixed point size.
enum BrieflyFont {
    /// Card headline. Serif, tight, large.
    static func headline(_ size: HeadlineSize = .regular) -> Font {
        switch size {
        case .large:   return .system(.largeTitle, design: .serif, weight: .semibold)
        case .regular: return .system(.title, design: .serif, weight: .semibold)
        case .compact: return .system(.title3, design: .serif, weight: .semibold)
        }
    }

    enum HeadlineSize { case large, regular, compact }

    /// The 30-word summary.
    static let summary = Font.system(.title3, design: .default, weight: .regular)
    /// Standard body copy in sheets and lists.
    static let body = Font.system(.body, design: .default)
    /// Emphasised body.
    static let bodyStrong = Font.system(.body, design: .default, weight: .semibold)
    /// Source names, publication times.
    static let caption = Font.system(.subheadline, design: .default)
    /// Chips, counters and the smallest labels.
    static let label = Font.system(.footnote, design: .default, weight: .medium)
    /// Section headers — small caps feel, achieved with tracking rather than a
    /// separate face.
    static let sectionHeader = Font.system(.caption, design: .default, weight: .semibold)
    /// Numerals that must line up in a column (durations, counts).
    static let mono = Font.system(.caption, design: .monospaced, weight: .medium)
}

extension View {
    /// Letter-spaced uppercase treatment used for section headers and the
    /// source-transparency labels.
    func brieflySectionHeader() -> some View {
        self.font(BrieflyFont.sectionHeader)
            .textCase(.uppercase)
            .tracking(1.1)
            .foregroundStyle(BrieflyColor.inkMuted)
    }
}
