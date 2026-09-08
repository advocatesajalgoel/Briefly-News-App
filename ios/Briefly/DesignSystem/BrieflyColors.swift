import SwiftUI

/// Briefly's palette.
///
/// The identity is "printed page, not app chrome": a warm paper ground, near-black
/// ink, one restrained accent, and semantic colours reserved for the things that
/// actually carry editorial meaning — confirmed, disputed, official. Colour is
/// never the only signal; every state also has a label, because a reader who
/// cannot distinguish the hues still needs to know a claim is contested.
enum BrieflyColor {
    // MARK: Ground and ink

    /// Page background. Warm off-white in light, near-black in dark.
    static let paper = Color("Paper", bundle: .main, fallbackLight: 0xFAF9F6, fallbackDark: 0x0C0C0E)
    /// Slightly raised surface for sheets and cards-on-cards.
    static let surface = Color("Surface", bundle: .main, fallbackLight: 0xFFFFFF, fallbackDark: 0x16161A)
    /// Primary text.
    static let ink = Color("Ink", bundle: .main, fallbackLight: 0x17171A, fallbackDark: 0xF5F4F0)
    /// Secondary text: timestamps, source names, captions.
    static let inkMuted = Color("InkMuted", bundle: .main, fallbackLight: 0x66666D, fallbackDark: 0x9C9CA4)
    /// Tertiary text and disabled states.
    static let inkFaint = Color("InkFaint", bundle: .main, fallbackLight: 0x8E8E95, fallbackDark: 0x6E6E76)
    /// Hairline rules. Editorial products use rules, not shadows.
    static let rule = Color("Rule", bundle: .main, fallbackLight: 0xE3E1DA, fallbackDark: 0x2A2A31)

    // MARK: Accent and semantics

    /// The single brand accent — a deep pine that reads as ink-adjacent rather
    /// than as a "tech blue".
    static let accent = Color("Accent", bundle: .main, fallbackLight: 0x0F5C4E, fallbackDark: 0x53D2B6)
    /// Corroborated by several independent sources, or by a primary source.
    static let confirmed = Color("Confirmed", bundle: .main, fallbackLight: 0x1F6F3C, fallbackDark: 0x6BD08A)
    /// Sources contradict each other.
    static let disputed = Color("Disputed", bundle: .main, fallbackLight: 0x9A3412, fallbackDark: 0xF0925E)
    /// Reported but not independently confirmed.
    static let reported = Color("Reported", bundle: .main, fallbackLight: 0x8A6A12, fallbackDark: 0xE0BA5A)
    /// A government or institutional primary source is on the record.
    static let official = Color("Official", bundle: .main, fallbackLight: 0x1F4E79, fallbackDark: 0x76B4E8)

    /// Tint used behind chips and pills.
    static func wash(_ color: Color) -> Color { color.opacity(0.12) }
}

extension Color {
    /// Looks up a named colour from the asset catalogue and falls back to a
    /// literal if the asset is missing.
    ///
    /// The fallbacks are not decoration: they mean the app renders correctly even
    /// if the catalogue has not been generated yet, which keeps the project
    /// buildable from a fresh checkout.
    init(_ name: String, bundle: Bundle, fallbackLight: UInt32, fallbackDark: UInt32) {
        #if canImport(UIKit)
        if UIColor(named: name, in: bundle, compatibleWith: nil) != nil {
            self.init(name, bundle: bundle)
            return
        }
        self.init(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? fallbackDark : fallbackLight
            return UIColor(
                red: CGFloat((hex >> 16) & 0xFF) / 255.0,
                green: CGFloat((hex >> 8) & 0xFF) / 255.0,
                blue: CGFloat(hex & 0xFF) / 255.0,
                alpha: 1.0
            )
        })
        #else
        self.init(red: Double((fallbackLight >> 16) & 0xFF) / 255.0,
                  green: Double((fallbackLight >> 8) & 0xFF) / 255.0,
                  blue: Double(fallbackLight & 0xFF) / 255.0)
        #endif
    }
}
