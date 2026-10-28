import Foundation

@main
struct WidgetValueStoreChecks {
    static func check(_ condition: Bool) { precondition(condition) }

    static func main() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let writer = WidgetValueStore(container: root)
        let reader = WidgetValueStore(container: root)
        let initialDate = Date(timeIntervalSince1970: 123)
        check(try reader.read(name: "folds") == nil)
        check(try writer.set(name: "folds", title: "Folds", value: "25", now: initialDate))
        check(try reader.read(name: "folds") == WidgetValueRecord(title: "Folds", value: "25", updatedAt: initialDate))
        check(try !writer.set(name: "folds", title: "Folds", value: "25"))
        check(try reader.read(name: "folds")?.updatedAt == initialDate)
        check(try writer.set(name: "folds", title: "Folds", value: "26"))
        check(try reader.read(name: "folds")?.value == "26")
        check(try writer.set(name: "../other", title: "Other", value: "☕️ 3"))
        check(try reader.read(name: "../other")?.value == "☕️ 3")
        check(!FileManager.default.fileExists(atPath: root.appendingPathComponent("other.json").path))
        check(try reader.read(name: "folds")?.value == "26")
        for name in ["", "  ", String(repeating: "a", count: 65)] {
            do {
                try writer.set(name: name, title: "Folds", value: "1")
                fatalError("Accepted invalid name")
            } catch WidgetValueStore.StoreError.invalidName {}
        }
        do {
            try writer.set(name: "folds", title: "Folds", value: String(repeating: "a", count: 513))
            fatalError("Accepted oversized content")
        } catch WidgetValueStore.StoreError.oversizedContent {}
        let files = try FileManager.default.contentsOfDirectory(at: writer.directory, includingPropertiesForKeys: nil)
        check(files.count == 2)
        let folds = try files.first {
            try JSONDecoder().decode(WidgetValueRecord.self, from: Data(contentsOf: $0)).value == "26"
        }!
        try Data("broken".utf8).write(to: folds)
        do {
            _ = try reader.read(name: "folds")
            fatalError("Accepted corrupt content")
        } catch {}
        check(try writer.set(name: "folds", title: "Folds", value: "27"))
        check(try reader.read(name: "folds")?.value == "27")
        try Data(repeating: 0, count: WidgetValueStore.maximumRecordBytes + 1).write(to: folds)
        do {
            _ = try reader.read(name: "folds")
            fatalError("Accepted oversized record")
        } catch WidgetValueStore.StoreError.invalidRecord {}
        check(try writer.set(name: "folds", title: "Folds", value: "28"))
        check(try reader.read(name: "folds")?.value == "28")
        print("WidgetValueStore checks passed: persistence, unchanged writes, isolation, bounds, recovery")
    }
}
