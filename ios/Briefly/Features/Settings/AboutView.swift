import SwiftUI

/// What the app does, in the app's own words.
struct AboutView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: BrieflySpace.xl) {
                VStack(alignment: .leading, spacing: BrieflySpace.s) {
                    Text("Maximum transparency.\nMinimum editorial distortion.")
                        .font(BrieflyFont.headline(.compact))
                        .foregroundStyle(BrieflyColor.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Briefly does not claim to be unbiased. Choosing which stories to "
                         + "carry and which words to use is editing, and editing has a point "
                         + "of view. What Briefly can do is show its work.")
                        .font(BrieflyFont.body)
                        .foregroundStyle(BrieflyColor.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }

                pipeline

                VStack(alignment: .leading, spacing: BrieflySpace.m) {
                    Text("What every card tells you").brieflySectionHeader()
                    ForEach(Self.guarantees, id: \.title) { item in
                        HStack(alignment: .top, spacing: BrieflySpace.m) {
                            Image(systemName: item.icon)
                                .font(.footnote)
                                .foregroundStyle(BrieflyColor.accent)
                                .frame(width: 20)
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.title)
                                    .font(BrieflyFont.bodyStrong)
                                    .foregroundStyle(BrieflyColor.ink)
                                Text(item.detail)
                                    .font(BrieflyFont.caption)
                                    .foregroundStyle(BrieflyColor.inkMuted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
            .padding(BrieflySpace.pageMargin)
        }
        .background(BrieflyColor.paper)
        .navigationTitle("How Briefly works")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var pipeline: some View {
        VStack(alignment: .leading, spacing: BrieflySpace.s) {
            Text("One pipeline, two outputs").brieflySectionHeader()
            VStack(alignment: .leading, spacing: BrieflySpace.xs) {
                ForEach(Self.stages, id: \.self) { stage in
                    HStack(spacing: BrieflySpace.s) {
                        Circle()
                            .fill(BrieflyColor.accent)
                            .frame(width: 5, height: 5)
                            .accessibilityHidden(true)
                        Text(stage)
                            .font(BrieflyFont.caption)
                            .foregroundStyle(BrieflyColor.ink)
                    }
                }
            }
            Text("The 30-word card and the audio briefing are written from the same "
                 + "extracted facts. Neither is a summary of an article, and neither can "
                 + "say something the sources did not.")
                .font(BrieflyFont.caption)
                .foregroundStyle(BrieflyColor.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, BrieflySpace.xs)
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

    private static let stages = [
        "Publishers' feeds and Google News",
        "Article ingestion",
        "Story clustering — many reports become one story",
        "Fact extraction — who, what, when, where, why, figures",
        "Shared story database",
        "→ 30-word card  and  → audio briefing"
    ]

    private struct Guarantee { let icon: String; let title: String; let detail: String }

    private static let guarantees = [
        Guarantee(icon: "person.2", title: "Who reported it",
                  detail: "Every publisher on the story, with their own headline and a link "
                        + "to the original."),
        Guarantee(icon: "clock", title: "When they reported it",
                  detail: "Publication times, in the order the sources filed."),
        Guarantee(icon: "checkmark.seal", title: "What is confirmed",
                  detail: "Corroborated by several independent outlets, or by a primary source."),
        Guarantee(icon: "exclamationmark.bubble", title: "What is disputed",
                  detail: "Where accounts differ, both sides are named rather than averaged."),
        Guarantee(icon: "chart.bar", title: "How varied the sourcing is",
                  detail: "A count of where reporting came from. Not a bias score.")
    ]
}

/// The rules the pipeline enforces, stated plainly to the reader.
struct EditorialStandardsView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: BrieflySpace.xl) {
                ForEach(Self.sections, id: \.title) { section in
                    VStack(alignment: .leading, spacing: BrieflySpace.s) {
                        Text(section.title).brieflySectionHeader()
                        ForEach(section.points, id: \.self) { point in
                            HStack(alignment: .top, spacing: BrieflySpace.s) {
                                Text("—")
                                    .foregroundStyle(BrieflyColor.inkFaint)
                                    .accessibilityHidden(true)
                                Text(point)
                                    .font(BrieflyFont.body)
                                    .foregroundStyle(BrieflyColor.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
            .padding(BrieflySpace.pageMargin)
        }
        .background(BrieflyColor.paper)
        .navigationTitle("Editorial standards")
        .navigationBarTitleDisplayMode(.inline)
    }

    private struct StandardsSection { let title: String; let points: [String] }

    private static let sections = [
        StandardsSection(title: "What Briefly will not do", points: [
            "Invent a fact, a figure, a name, a quote, a source or a link.",
            "Turn an allegation into a fact. If somebody claims it, the card says who.",
            "Publish a summary over 30 words. The limit is enforced in code and by the "
            + "database, not by asking a model nicely.",
            "Republish a publisher's article. Cards carry Briefly's own wording and link out.",
            "Rank stories by how likely you are to tap them."
        ]),
        StandardsSection(title: "How sources are gathered", points: [
            "Only what publishers choose to syndicate: RSS, Atom and documented APIs.",
            "robots.txt is always honoured, and a feed we cannot get permission for is skipped.",
            "Paywalls, logins and access controls are never worked around.",
            "Outlets that require a licence appear only when another source credits them, "
            + "with a link and no stored summary."
        ]),
        StandardsSection(title: "Before anything is published", points: [
            "Every fact must be traceable to supplied source material, or it is discarded.",
            "Figures, names and dates are checked back against the sources.",
            "Copy is checked for sensational and opinionated wording.",
            "Text that leans too close to a publisher's own phrasing is rejected.",
            "Anything that fails is flagged for a person to look at rather than published."
        ])
    ]
}
