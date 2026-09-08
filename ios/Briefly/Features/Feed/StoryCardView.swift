import SwiftUI

/// One story, one screen.
///
/// The layout is a printed page: a rule and a slug line at the top, a serif
/// headline with room to breathe, the ≤30-word summary set large enough to read
/// at arm's length, and a footer that answers "who says so?" before the reader
/// has to ask. No image — Briefly has no licence to a publisher's photography,
/// and going text-only makes the card load instantly and read cleanly at any
/// Dynamic Type size.
struct StoryCardView: View {
    let story: Story
    let isSaved: Bool
    var showConfidence: Bool = true
    let onOpenSources: () -> Void
    let onToggleSave: () -> Void
    let onShare: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var headlineSize: BrieflyFont.HeadlineSize {
        // At the largest accessibility sizes a "large title" serif headline eats
        // the whole screen, so step it down rather than let it push the summary
        // off the page.
        if dynamicTypeSize >= .accessibility1 { return .compact }
        return story.headline.count > 76 ? .regular : .large
    }

    var body: some View {
        GeometryReader { proxy in
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 0) {
                    slugLine
                    headline
                    summary
                    Spacer(minLength: BrieflySpace.xl)
                    footer
                }
                .padding(.horizontal, BrieflySpace.pageMargin)
                .padding(.top, BrieflySpace.l)
                .padding(.bottom, BrieflySpace.xl)
                .frame(minHeight: proxy.size.height, alignment: .top)
            }
            .scrollIndicators(.hidden)
            // The card itself only scrolls when its content genuinely overflows —
            // at default text sizes it never does, so the vertical swipe belongs
            // to the feed and paging stays crisp.
            .scrollBounceBehavior(.basedOnSize)
        }
        .background(BrieflyColor.paper)
    }

    // MARK: - Sections

    private var slugLine: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            HStack(spacing: BrieflySpace.s) {
                if let category = story.categoryName {
                    Text(category)
                        .font(BrieflyFont.label)
                        .textCase(.uppercase)
                        .tracking(1.2)
                        .foregroundStyle(BrieflyColor.accent)
                }
                Circle()
                    .fill(BrieflyColor.inkFaint)
                    .frame(width: 3, height: 3)
                    .accessibilityHidden(true)
                Text(story.timestampText)
                    .font(BrieflyFont.label)
                    .foregroundStyle(BrieflyColor.inkMuted)
                Spacer(minLength: 0)
                if showConfidence {
                    ConfidenceBadge(level: story.confidenceLevel)
                }
            }
            BrieflyRule()
        }
        .padding(.bottom, BrieflySpace.l)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "\(story.categoryName ?? "Story"), \(story.timestampText), \(story.confidenceLevel.label)"
        )
    }

    private var headline: some View {
        Text(story.headline)
            .font(BrieflyFont.headline(headlineSize))
            .foregroundStyle(BrieflyColor.ink)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.leading)
            .padding(.bottom, BrieflySpace.l)
            .accessibilityAddTraits(.isHeader)
    }

    private var summary: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            Text(story.summary)
                .font(BrieflyFont.summary)
                .foregroundStyle(BrieflyColor.ink.opacity(0.88))
                .lineSpacing(5)
                .fixedSize(horizontal: false, vertical: true)

            if story.hasDisputedClaims {
                disputeNote
            }
        }
    }

    private var disputeNote: some View {
        HStack(alignment: .top, spacing: BrieflySpace.s) {
            Image(systemName: "exclamationmark.bubble")
                .font(.footnote)
                .foregroundStyle(BrieflyColor.disputed)
                .accessibilityHidden(true)
            Text("Sources disagree on part of this story.")
                .font(BrieflyFont.caption)
                .foregroundStyle(BrieflyColor.disputed)
        }
        .padding(.top, BrieflySpace.xs)
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            BrieflyRule()

            Button(action: onOpenSources) {
                HStack(alignment: .center, spacing: BrieflySpace.m) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(story.sourceCountText.uppercased())
                            .font(BrieflyFont.label)
                            .tracking(1.0)
                            .foregroundStyle(BrieflyColor.ink)
                        Text(sourceSummaryLine)
                            .font(BrieflyFont.caption)
                            .foregroundStyle(BrieflyColor.inkMuted)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    diversityPip
                    Image(systemName: "chevron.right")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(BrieflyColor.inkFaint)
                        .accessibilityHidden(true)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(story.sourceCountText). \(sourceSummaryLine)")
            .accessibilityHint("Shows every source, when it reported, and links to the originals")

            actionRow
        }
    }

    private var sourceSummaryLine: String {
        let names = story.sourcesByTime.prefix(3).map(\.sourceName)
        if names.isEmpty { return "No sources recorded" }
        let listed = names.joined(separator: ", ")
        let remaining = story.sourceCount - names.count
        return remaining > 0 ? "\(listed) and \(remaining) more" : listed
    }

    private var diversityPip: some View {
        HStack(spacing: 2) {
            ForEach(1...3, id: \.self) { step in
                Capsule()
                    .fill(step <= story.diversity.levelRank
                          ? BrieflyColor.accent : BrieflyColor.rule)
                    .frame(width: 10, height: 3)
            }
        }
        .accessibilityHidden(true)
    }

    private var actionRow: some View {
        HStack(spacing: BrieflySpace.l) {
            Button(action: onToggleSave) {
                Label(isSaved ? "Saved" : "Save",
                      systemImage: isSaved ? "bookmark.fill" : "bookmark")
                    .font(BrieflyFont.label)
                    .foregroundStyle(isSaved ? BrieflyColor.accent : BrieflyColor.inkMuted)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(isSaved ? "Remove from saved" : "Save this story")

            Button(action: onShare) {
                Label("Share", systemImage: "square.and.arrow.up")
                    .font(BrieflyFont.label)
                    .foregroundStyle(BrieflyColor.inkMuted)
            }
            .buttonStyle(.plain)

            Spacer(minLength: 0)

            HStack(spacing: BrieflySpace.xs) {
                Image(systemName: "chevron.up")
                    .font(.caption2.weight(.semibold))
                Text("Swipe")
                    .font(.caption2)
            }
            .foregroundStyle(BrieflyColor.inkFaint)
            .accessibilityHidden(true)
        }
        .padding(.top, BrieflySpace.xs)
    }
}
