import SwiftUI

/// Loading, error and empty states.
///
/// Every screen in the app uses these three, so the app never shows a blank
/// rectangle and never leaves the reader without something to do next.
struct LoadingStateView: View {
    var message: String = "Gathering today's stories"

    var body: some View {
        VStack(spacing: BrieflySpace.l) {
            ProgressView()
                .controlSize(.large)
                .tint(BrieflyColor.accent)
            Text(message)
                .font(BrieflyFont.caption)
                .foregroundStyle(BrieflyColor.inkMuted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(BrieflyColor.paper)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(message)
    }
}

/// A skeleton card. Used for the first load of the feed so the layout does not
/// jump when the real card arrives.
struct StorySkeletonView: View {
    @State private var shimmer = false

    var body: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.l) {
            block(width: 120, height: 14)
            VStack(alignment: .leading, spacing: BrieflySpace.s) {
                block(width: .infinity, height: 30)
                block(width: 260, height: 30)
            }
            VStack(alignment: .leading, spacing: BrieflySpace.s) {
                block(width: .infinity, height: 18)
                block(width: .infinity, height: 18)
                block(width: 180, height: 18)
            }
            Spacer()
            block(width: .infinity, height: 60)
        }
        .padding(BrieflySpace.pageMargin)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .background(BrieflyColor.paper)
        .opacity(shimmer ? 0.55 : 1)
        .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: shimmer)
        .onAppear { shimmer = true }
        .accessibilityHidden(true)
    }

    private func block(width: CGFloat, height: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: 6, style: .continuous)
            .fill(BrieflyColor.rule)
            .frame(maxWidth: width == .infinity ? .infinity : width, alignment: .leading)
            .frame(height: height)
    }
}

struct ErrorStateView: View {
    let title: String
    let message: String
    var systemImage: String = "exclamationmark.triangle"
    var retryTitle: String = "Try again"
    var onRetry: (() -> Void)?
    var secondaryTitle: String?
    var onSecondary: (() -> Void)?

    var body: some View {
        VStack(spacing: BrieflySpace.l) {
            Image(systemName: systemImage)
                .font(.system(size: 34, weight: .light))
                .foregroundStyle(BrieflyColor.inkFaint)
            VStack(spacing: BrieflySpace.s) {
                Text(title)
                    .font(BrieflyFont.headline(.compact))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(BrieflyColor.ink)
                Text(message)
                    .font(BrieflyFont.caption)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(BrieflyColor.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(spacing: BrieflySpace.s) {
                if let onRetry {
                    Button(retryTitle, action: onRetry)
                        .buttonStyle(BrieflyPrimaryButtonStyle())
                }
                if let secondaryTitle, let onSecondary {
                    Button(secondaryTitle, action: onSecondary)
                        .buttonStyle(BrieflySecondaryButtonStyle())
                }
            }
        }
        .padding(BrieflySpace.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(BrieflyColor.paper)
    }
}

struct EmptyStateView: View {
    let title: String
    let message: String
    var systemImage: String = "tray"
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        VStack(spacing: BrieflySpace.l) {
            Image(systemName: systemImage)
                .font(.system(size: 34, weight: .light))
                .foregroundStyle(BrieflyColor.inkFaint)
            VStack(spacing: BrieflySpace.s) {
                Text(title)
                    .font(BrieflyFont.headline(.compact))
                    .foregroundStyle(BrieflyColor.ink)
                Text(message)
                    .font(BrieflyFont.caption)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(BrieflyColor.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(BrieflySecondaryButtonStyle())
            }
        }
        .padding(BrieflySpace.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(BrieflyColor.paper)
    }
}

/// Shown above the feed when the app is serving its bundled snapshot instead of
/// live reporting. Saying so is not optional: presenting sample data as today's
/// news would undermine the entire premise of the app.
struct SampleDataBanner: View {
    var reason: String?
    var onConfigure: () -> Void

    var body: some View {
        Button(action: onConfigure) {
            HStack(spacing: BrieflySpace.s) {
                Image(systemName: "info.circle")
                    .font(.footnote)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Sample stories")
                        .font(BrieflyFont.label)
                    Text(reason ?? "No Briefly server configured. Tap to set one up.")
                        .font(.caption2)
                        .foregroundStyle(BrieflyColor.inkMuted)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(BrieflyColor.inkFaint)
            }
            .foregroundStyle(BrieflyColor.ink)
            .padding(.horizontal, BrieflySpace.pageMargin)
            .padding(.vertical, BrieflySpace.s)
            .background(BrieflyColor.wash(BrieflyColor.reported))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens settings so you can point the app at a Briefly server")
    }
}

// MARK: - Button styles

struct BrieflyPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(BrieflyFont.bodyStrong)
            .foregroundStyle(BrieflyColor.paper)
            .padding(.horizontal, BrieflySpace.xl)
            .padding(.vertical, BrieflySpace.m)
            .background(
                RoundedRectangle(cornerRadius: BrieflyRadius.chip + 3, style: .continuous)
                    .fill(BrieflyColor.accent)
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
            .animation(BrieflyMotion.subtle, value: configuration.isPressed)
    }
}

struct BrieflySecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(BrieflyFont.body)
            .foregroundStyle(BrieflyColor.accent)
            .padding(.horizontal, BrieflySpace.l)
            .padding(.vertical, BrieflySpace.s)
            .background(
                RoundedRectangle(cornerRadius: BrieflyRadius.chip + 3, style: .continuous)
                    .strokeBorder(BrieflyColor.rule, lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.7 : 1)
            .animation(BrieflyMotion.subtle, value: configuration.isPressed)
    }
}
