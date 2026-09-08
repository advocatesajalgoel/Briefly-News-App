import Foundation
import Security

/// A stable, app-scoped identifier used only to key optional bookmark sync.
///
/// Deliberately *not* the IDFA or the vendor identifier: this is a random value
/// created on first launch, stored in the keychain so it survives a reinstall,
/// and it is never sent anywhere unless the reader turns on bookmark sync.
enum DeviceIdentifier {
    private static let service = "com.briefly.app.device"
    private static let account = "device-id"

    static var current: String {
        if let existing = readFromKeychain() {
            return existing
        }
        let generated = "briefly-" + UUID().uuidString.lowercased()
        writeToKeychain(generated)
        return generated
    }

    // MARK: - Keychain

    private static func readFromKeychain() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let value = String(data: data, encoding: .utf8) else {
            return nil
        }
        return value
    }

    private static func writeToKeychain(_ value: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)

        var attributes = query
        attributes[kSecValueData as String] = Data(value.utf8)
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(attributes as CFDictionary, nil)
    }
}
