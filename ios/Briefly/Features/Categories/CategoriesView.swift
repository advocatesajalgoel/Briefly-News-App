import SwiftUI

/// Tab 2. Pick a section; the feed inside it is the same card stack.
struct CategoriesView: View {
    @Environment(AppEnvironment.self) private var appEnvironment
    @State private var categories: [NewsCategory] = []
    @State private var phase: Phase = .loading
    @State private var errorMessage: String?

    private enum Phase { case loading, loaded, failed }

    var body: some View {
        NavigationStack {
            Group {
                switch phase {
                case .loading:
                    LoadingStateView(message: "Loading sections")
                case .failed:
                    ErrorStateView(
                        title: "Couldn't load sections",
                        message: errorMessage ?? "Something went wrong.",
                        onRetry: { Task { await load() } }
                    )
                case .loaded:
                    list
                }
            }
            .background(BrieflyColor.paper)
            .navigationTitle("Sections")
        }
        .task { await load() }
    }

    private var list: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(categories) { category in
                    NavigationLink {
                        CategoryFeedScreen(category: category)
                    } label: {
                        row(for: category)
                    }
                    .buttonStyle(.plain)
                    BrieflyRule(opacity: 0.7)
                        .padding(.leading, BrieflySpace.pageMargin)
                }
            }
        }
        .background(BrieflyColor.paper)
    }

    private func row(for category: NewsCategory) -> some View {
        HStack(spacing: BrieflySpace.l) {
            Image(systemName: category.systemImage)
                .font(.title3)
                .foregroundStyle(BrieflyColor.accent)
                .frame(width: 28)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(category.name)
                    .font(BrieflyFont.bodyStrong)
                    .foregroundStyle(BrieflyColor.ink)
                if let description = category.description {
                    Text(description)
                        .font(BrieflyFont.caption)
                        .foregroundStyle(BrieflyColor.inkMuted)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(BrieflyColor.inkFaint)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, BrieflySpace.pageMargin)
        .padding(.vertical, BrieflySpace.l)
        .contentShape(Rectangle())
    }

    private func load() async {
        do {
            categories = try await appEnvironment.repository.categories()
                .sorted { $0.sortOrder < $1.sortOrder }
            phase = .loaded
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
            phase = .failed
        }
    }
}

/// A category's own card stack, pushed from the section list.
struct CategoryFeedScreen: View {
    let category: NewsCategory
    @Environment(AppEnvironment.self) private var appEnvironment
    @State private var model: FeedViewModel?

    var body: some View {
        Group {
            if let model {
                FeedView(model: model)
            } else {
                StorySkeletonView()
            }
        }
        .navigationTitle(category.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(BrieflyColor.paper, for: .navigationBar)
        .onAppear {
            if model == nil {
                model = FeedViewModel(category: category, repository: appEnvironment.repository)
            }
        }
    }
}
