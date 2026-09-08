import SwiftUI

/// A small labelled chip. Used for the category, the confidence level and the
/// source count.
struct BrieflyChip: View {
    let text: String
    var systemImage: String?
    var tint: Color = BrieflyColor.inkMuted
    var filled: Bool = false

    var body: some View {
        HStack(spacing: BrieflySpace.xs) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.caption2)
                    .accessibilityHidden(true)
            }
            Text(text)
                .font(BrieflyFont.label)
                .textCase(.uppercase)
                .tracking(0.8)
        }
        .foregroundStyle(tint)
        .padding(.horizontal, BrieflySpace.s)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: BrieflyRadius.chip, style: .continuous)
                .fill(filled ? BrieflyColor.wash(tint) : Color.clear)
        )
        .overlay(
            RoundedRectangle(cornerRadius: BrieflyRadius.chip, style: .continuous)
                .strokeBorder(filled ? Color.clear : BrieflyColor.rule, lineWidth: 1)
        )
        .accessibilityLabel(text)
    }
}

/// The thin editorial rule Briefly uses instead of card shadows.
struct BrieflyRule: View {
    var opacity: Double = 1

    var body: some View {
        Rectangle()
            .fill(BrieflyColor.rule)
            .frame(height: 1)
            .opacity(opacity)
            .accessibilityHidden(true)
    }
}

/// A bar showing how diverse the reporting is, with the caveat attached.
struct DiversityMeter: View {
    let diversity: SourceDiversity
    var compact: Bool = false

    private var tint: Color {
        switch diversity.levelRank {
        case 3:  return BrieflyColor.confirmed
        case 2:  return BrieflyColor.accent
        default: return BrieflyColor.reported
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            HStack(spacing: BrieflySpace.s) {
                Text("Source diversity").brieflySectionHeader()
                Spacer(minLength: 0)
                Text(diversity.levelLabel)
                    .font(BrieflyFont.label)
                    .tracking(0.8)
                    .foregroundStyle(tint)
            }

            HStack(spacing: 3) {
                ForEach(1...3, id: \.self) { step in
                    Capsule()
                        .fill(step <= diversity.levelRank ? tint : BrieflyColor.rule)
                        .frame(height: 4)
                }
            }
            .accessibilityHidden(true)

            if !compact {
                if diversity.lines.isEmpty {
                    Text("Reporting from \(diversity.independent) independent "
                         + (diversity.independent == 1 ? "source." : "sources."))
                        .font(BrieflyFont.caption)
                        .foregroundStyle(BrieflyColor.inkMuted)
                } else {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(diversity.lines, id: \.self) { line in
                            Text(line)
                                .font(BrieflyFont.caption)
                                .foregroundStyle(BrieflyColor.inkMuted)
                        }
                    }
                }

                Text(diversity.disclaimer)
                    .font(.caption2)
                    .foregroundStyle(BrieflyColor.inkFaint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "Source diversity \(diversity.level). "
            + diversity.lines.joined(separator: ", ")
            + ". " + diversity.disclaimer
        )
    }
}

/// One publisher, its own headline, when it filed, and a link out.
struct SourceRow: View {
    let source: StorySource
    let onOpen: (URL) -> Void

    var body: some View {
        Button {
            if let url = source.originalURL { onOpen(url) }
        } label: {
            HStack(alignment: .top, spacing: BrieflySpace.m) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: BrieflySpace.s) {
                        Text(source.sourceName)
                            .font(BrieflyFont.bodyStrong)
                            .foregroundStyle(BrieflyColor.ink)
                        if source.isPrimarySource {
                            BrieflyChip(text: "Primary", tint: BrieflyColor.official, filled: true)
                        }
                    }
                    // The publisher's own words, quoted exactly. Briefly never
                    // rewrites someone else's headline.
                    Text(source.originalHeadline)
                        .font(BrieflyFont.caption)
                        .foregroundStyle(BrieflyColor.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)

                    HStack(spacing: BrieflySpace.s) {
                        Text(source.kindLabel)
                        if !source.timestampText.isEmpty {
                            Text("·")
                            Text(source.timestampText)
                        }
                    }
                    .font(.caption2)
                    .foregroundStyle(BrieflyColor.inkFaint)
                }

                Spacer(minLength: 0)

                if source.originalURL != nil {
                    Image(systemName: "arrow.up.right")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(BrieflyColor.accent)
                        .padding(.top, 2)
                        .accessibilityHidden(true)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(source.originalURL == nil)
        .accessibilityLabel("\(source.sourceName). \(source.originalHeadline)")
        .accessibilityHint(source.originalURL == nil ? "No link available"
                                                     : "Opens the original article")
    }
}

/// Confirmed / Disputed / Reported, with an explanation available on tap.
struct ConfidenceBadge: View {
    let level: ConfidenceLevel

    private var tint: Color {
        switch level {
        case .confirmed: return BrieflyColor.confirmed
        case .disputed:  return BrieflyColor.disputed
        case .reported:  return BrieflyColor.reported
        }
    }

    var body: some View {
        BrieflyChip(text: level.label, systemImage: level.systemImage, tint: tint, filled: true)
            .accessibilityLabel("\(level.label). \(level.explanation)")
    }
}
