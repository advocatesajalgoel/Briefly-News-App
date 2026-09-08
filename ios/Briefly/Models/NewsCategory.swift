import Foundation

/// A section of the app. Sections come from the backend, so adding one is a data
/// change rather than a release.
struct NewsCategory: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    let slug: String
    let name: String
    let description: String?
    let sortOrder: Int
    let isSynthetic: Bool

    /// The ranked mix across every section.
    var isForYou: Bool { slug == "for-you" }

    var systemImage: String {
        switch slug {
        case "for-you":       return "sparkles"
        case "india":         return "building.columns"
        case "world":         return "globe"
        case "business":      return "chart.line.uptrend.xyaxis"
        case "technology":    return "cpu"
        case "science":       return "atom"
        case "sports":        return "figure.run"
        case "entertainment": return "theatermasks"
        default:              return "newspaper"
        }
    }
}
