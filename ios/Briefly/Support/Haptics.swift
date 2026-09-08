import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// Feedback for the swipe gesture and for saving a story.
///
/// Deliberately restrained: one soft tick when a card changes, nothing at all if
/// the reader has turned it off. A news app that buzzes constantly is a news app
/// people stop opening.
enum Haptics {
    @MainActor
    static func pageTurn(enabled: Bool) {
        guard enabled else { return }
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: .soft)
        generator.impactOccurred(intensity: 0.55)
        #endif
    }

    @MainActor
    static func saved(enabled: Bool) {
        guard enabled else { return }
        #if canImport(UIKit)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        #endif
    }

    @MainActor
    static func selection(enabled: Bool) {
        guard enabled else { return }
        #if canImport(UIKit)
        UISelectionFeedbackGenerator().selectionChanged()
        #endif
    }
}
