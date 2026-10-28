import Foundation
import CryptoKit

/// Small, app-group backed snapshots for independently running native extensions.
/// Hosts supply their container and retain ownership of names and refresh policy.
struct WidgetValueRecord: Codable, Equatable {
    let title: String
    let value: String
    let updatedAt: Date
}

struct WidgetValueStore {
    let directory: URL
    static let maximumRecordBytes = 8192

    init(container: URL) {
        directory = container.appendingPathComponent("WidgetValues", isDirectory: true)
    }

    init(appGroup: String) throws {
        guard let container = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroup
        ) else { throw StoreError.containerUnavailable }
        self.init(container: container)
    }

    enum StoreError: LocalizedError {
        case containerUnavailable, invalidName, oversizedContent, invalidRecord

        var errorDescription: String? {
            switch self {
            case .containerUnavailable: return "Widget storage is unavailable. Check the app's shared-container signing."
            case .invalidName: return "Use a widget name of 1–64 characters."
            case .oversizedContent: return "Use a title up to 64 characters and a value up to 512 characters."
            case .invalidRecord: return "The saved widget value could not be read. Set its value again in Shortcuts."
            }
        }
    }

    private func location(for name: String) throws -> URL {
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              name.count <= 64 else { throw StoreError.invalidName }
        let digest = SHA256.hash(data: Data(name.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(digest + ".json")
    }

    func read(name: String) throws -> WidgetValueRecord? {
        let url = try location(for: name)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size <= Self.maximumRecordBytes else { throw StoreError.invalidRecord }
        let data = try Data(contentsOf: url)
        guard data.count <= Self.maximumRecordBytes else { throw StoreError.invalidRecord }
        let record = try JSONDecoder().decode(WidgetValueRecord.self, from: data)
        guard record.title.count <= 64, record.value.count <= 512 else {
            throw StoreError.invalidRecord
        }
        return record
    }

    /// Atomic replacement; concurrent writers are last-writer-wins, not increments.
    /// Identical content avoids both a write and a consumer's refresh request.
    @discardableResult
    func set(name: String, title: String, value: String, now: Date = Date()) throws -> Bool {
        let url = try location(for: name)
        guard title.count <= 64, value.count <= 512 else { throw StoreError.oversizedContent }
        // An explicit set may repair a malformed snapshot; ordinary reads never rewrite it.
        if let previous = try? read(name: name), previous.title == title, previous.value == value {
            return false
        }
        let record = WidgetValueRecord(title: title, value: value, updatedAt: now)
        let data = try JSONEncoder().encode(record)
        guard data.count <= Self.maximumRecordBytes else { throw StoreError.oversizedContent }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        #if os(iOS)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try data.write(to: url, options: .atomic)
        #endif
        return true
    }
}
