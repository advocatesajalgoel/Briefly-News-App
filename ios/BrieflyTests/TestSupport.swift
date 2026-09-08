import Foundation
import XCTest
@testable import Briefly

/// Finds the bundled snapshot regardless of where the test runner puts it.
///
/// With a test host the JSON lives in the app bundle (`Bundle.main`); when the
/// tests are built without one it lives in the test bundle. Checking both means
/// the same tests run in either configuration instead of silently skipping.
enum TestResources {
    static let bundle: Bundle = {
        let testBundle = Bundle(for: BundleToken.self)
        if testBundle.url(forResource: "mock_stories", withExtension: "json") != nil {
            return testBundle
        }
        if Bundle.main.url(forResource: "mock_stories", withExtension: "json") != nil {
            return Bundle.main
        }
        return testBundle
    }()

    static var isAvailable: Bool {
        bundle.url(forResource: "mock_stories", withExtension: "json") != nil
    }

    static func data(_ resource: String) throws -> Data {
        guard let url = bundle.url(forResource: resource, withExtension: "json") else {
            throw XCTSkip("\(resource).json was not copied into the test or app bundle")
        }
        return try Data(contentsOf: url)
    }

    static func repository() -> BundledNewsRepository {
        BundledNewsRepository(bundle: bundle)
    }

    private final class BundleToken {}
}
