import XCTest
@testable import Briefly

final class FormattingTests: XCTestCase {
    func testDurationFormatting() {
        XCTAssertEqual(Duration.formatted(seconds: 0), "0:00")
        XCTAssertEqual(Duration.formatted(seconds: 9), "0:09")
        XCTAssertEqual(Duration.formatted(seconds: 65), "1:05")
        XCTAssertEqual(Duration.formatted(seconds: 600), "10:00")
        XCTAssertEqual(Duration.formatted(seconds: 3661), "1:01:01")
        XCTAssertEqual(Duration.formatted(seconds: -5), "0:00", "negatives clamp rather than crash")
    }

    func testApproximateDuration() {
        XCTAssertEqual(Duration.approximate(seconds: 20), "Under a minute")
        XCTAssertEqual(Duration.approximate(seconds: 480), "About 8 min")
    }

    func testRelativeTime() {
        let now = Date()
        XCTAssertEqual(RelativeTime.string(for: now.addingTimeInterval(-30), now: now), "Just now")
        XCTAssertFalse(RelativeTime.string(for: now.addingTimeInterval(-3600), now: now).isEmpty)
        XCTAssertEqual(RelativeTime.string(for: nil), "")
    }

    func testCompactRelativeTime() {
        let now = Date()
        XCTAssertEqual(RelativeTime.compact(for: now.addingTimeInterval(-120), now: now), "2m")
        XCTAssertEqual(RelativeTime.compact(for: now.addingTimeInterval(-7200), now: now), "2h")
        XCTAssertEqual(RelativeTime.compact(for: now.addingTimeInterval(-172_800), now: now), "2d")
    }

    func testWordCountMatchesTheBackendsRule() {
        XCTAssertEqual(WordCount.count(""), 0)
        XCTAssertEqual(WordCount.count("One"), 1)
        XCTAssertEqual(WordCount.count("Two words"), 2)
        XCTAssertEqual(WordCount.count("don't count that twice"), 4)
        XCTAssertEqual(WordCount.count("!!! ???"), 0)
        XCTAssertTrue(WordCount.isWithinCardLimit(String(repeating: "word ", count: 30)))
        XCTAssertFalse(WordCount.isWithinCardLimit(String(repeating: "word ", count: 31)))
    }
}
