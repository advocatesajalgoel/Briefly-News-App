import SwiftUI

/// The transparency panel: every source, what each one said, when, and a link.
///
/// This is the screen the whole product is arguing for, so it leads with the
/// count and the diversity indicator, lists the sources in the order they filed,
/// and separates what is corroborated from what is only claimed.
struct SourcesSheet: View {
    let story: Story
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: BrieflySpace.xl) {
                    header
                    diversitySection
                    sourcesSection
                    if !story.disputedFacts.isEmpty { disagreementSection }
                    factsSection
                    footerNote
                }
                .padding(.horizontal, BrieflySpace.pageMargin)
                .padding(.vertical, BrieflySpace.l)
            }
            .background(BrieflyColor.paper)
            .navigationTitle("Sources")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDragIndicator(.visible)
    }

    // MARK: - Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Text(story.sourceCountText.uppercased())
                .font(BrieflyFont.label)
                .tracking(1.2)
                .foregroundStyle(BrieflyColor.inkMuted)
            Text(story.headline)
                .font(BrieflyFont.headline(.compact))
                .foregroundStyle(BrieflyColor.ink)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: BrieflySpace.s) {
                ConfidenceBadge(level: story.confidenceLevel)
                if story.hasOfficialSource {
                    BrieflyChip(text: "Official source",
                                systemImage: "building.columns",
                                tint: BrieflyColor.official, filled: true)
                }
            }
            .padding(.top, BrieflySpace.xs)

            Text(story.confidenceLevel.explanation)
                .font(BrieflyFont.caption)
                .foregroundStyle(BrieflyColor.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var diversitySection: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            DiversityMeter(diversity: story.diversity)
        }
        .padding(BrieflySpace.l)
        .background(
            RoundedRectangle(cornerRadius: BrieflyRadius.card, style: .continuous)
                .fill(BrieflyColor.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: BrieflyRadius.card, style: .continuous)
                .strokeBorder(BrieflyColor.rule, lineWidth: 1)
        )
    }

    private var sourcesSection: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            Text("Who reported it").brieflySectionHeader()
            if story.sources.isEmpty {
                Text("No sources were recorded for this story.")
                    .font(BrieflyFont.caption)
                    .foregroundStyle(BrieflyColor.inkMuted)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(story.sourcesByTime.enumerated()), id: \.element.id) { index, source in
                        SourceRow(source: source) { openURL($0) }
                            .padding(.vertical, BrieflySpace.m)
                        if index < story.sources.count - 1 { BrieflyRule(opacity: 0.7) }
                    }
                }
            }
        }
    }

    private var disagreementSection: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            Text("Where sources disagree").brieflySectionHeader()
            VStack(alignment: .leading, spacing: BrieflySpace.m) {
                ForEach(story.disputedFacts) { fact in
                    VStack(alignment: .leading, spacing: 3) {
                        if let attribution = fact.attributionText {
                            Text(attribution)
                                .font(BrieflyFont.label)
                                .foregroundStyle(BrieflyColor.disputed)
                        }
                        Text(fact.text)
                            .font(BrieflyFont.body)
                            .foregroundStyle(BrieflyColor.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .padding(BrieflySpace.l)
            .background(
                RoundedRectangle(cornerRadius: BrieflyRadius.card, style: .continuous)
                    .fill(BrieflyColor.wash(BrieflyColor.disputed))
            )
        }
    }

    private var factsSection: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.m) {
            if !story.confirmedFacts.isEmpty {
                factGroup(title: "Confirmed", facts: story.confirmedFacts,
                          tint: BrieflyColor.confirmed)
            }
            if !story.attributedFacts.isEmpty {
                factGroup(title: "Attributed claims", facts: story.attributedFacts,
                          tint: BrieflyColor.reported)
            }
            if !story.uncertainFacts.isEmpty {
                factGroup(title: "Not yet settled", facts: story.uncertainFacts,
                          tint: BrieflyColor.inkMuted)
            }
            if !story.keyFigures.isEmpty {
                VStack(alignment: .leading, spacing: BrieflySpace.s) {
                    Text("Key figures").brieflySectionHeader()
                    FlowLayout(spacing: BrieflySpace.s) {
                        ForEach(story.keyFigures) { fact in
                            BrieflyChip(text: fact.text, tint: BrieflyColor.ink, filled: true)
                        }
                    }
                }
            }
        }
    }

    private func factGroup(title: String, facts: [ExtractedFact], tint: Color) -> some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Text(title).brieflySectionHeader()
            ForEach(facts.prefix(6)) { fact in
                HStack(alignment: .top, spacing: BrieflySpace.s) {
                    Circle()
                        .fill(tint)
                        .frame(width: 5, height: 5)
                        .padding(.top, 7)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(fact.text)
                            .font(BrieflyFont.body)
                            .foregroundStyle(BrieflyColor.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        HStack(spacing: BrieflySpace.s) {
                            if let attribution = fact.attributionText {
                                Text(attribution)
                            }
                            if let support = fact.supportText {
                                Text("·")
                                Text(support)
                            }
                        }
                        .font(.caption2)
                        .foregroundStyle(BrieflyColor.inkFaint)
                    }
                }
            }
        }
    }

    private var footerNote: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            BrieflyRule()
            Text(
                "Briefly does not claim to be unbiased. It shows you who reported what, "
                + "when, and where accounts differ, and links you to the originals so you "
                + "can check any of it yourself. Headlines above are each publisher's own."
            )
            .font(.caption2)
            .foregroundStyle(BrieflyColor.inkFaint)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, BrieflySpace.s)
    }
}

/// Wraps chips onto as many lines as they need.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var rowWidth: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0
        var totalWidth: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if rowWidth + size.width > maxWidth, rowWidth > 0 {
                totalHeight += rowHeight + spacing
                totalWidth = max(totalWidth, rowWidth - spacing)
                rowWidth = 0
                rowHeight = 0
            }
            rowWidth += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        totalHeight += rowHeight
        totalWidth = max(totalWidth, rowWidth - spacing)
        return CGSize(width: min(totalWidth, maxWidth), height: totalHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
