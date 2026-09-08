import SwiftUI

/// Spacing, radii and motion. One place to change the rhythm of the whole app.
enum BrieflySpace {
    static let hairline: CGFloat = 1.0 / 3.0
    static let xs: CGFloat = 4
    static let s: CGFloat = 8
    static let m: CGFloat = 12
    static let l: CGFloat = 16
    static let xl: CGFloat = 24
    static let xxl: CGFloat = 32
    static let xxxl: CGFloat = 48

    /// Horizontal page margin. Generous by design — whitespace is the point.
    static let pageMargin: CGFloat = 24
}

enum BrieflyRadius {
    static let chip: CGFloat = 7
    static let card: CGFloat = 18
    static let sheet: CGFloat = 24
}

enum BrieflyMotion {
    /// Card-to-card transitions: quick, no bounce, never in the reader's way.
    static let page = Animation.interpolatingSpring(stiffness: 320, damping: 34)
    /// Small state changes — a chip appearing, a count updating.
    static let subtle = Animation.easeOut(duration: 0.18)
    /// Sheet and overlay presentation.
    static let sheet = Animation.spring(response: 0.36, dampingFraction: 0.86)
}
