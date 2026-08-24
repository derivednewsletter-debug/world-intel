import Foundation

/// On-disk JSON cache. Views show cached data instantly and only hit the network
/// when their TTL has expired — the app is idle (zero battery cost) otherwise.
final class CacheStore {
    static let shared = CacheStore()

    private let fm = FileManager.default
    private var dir: URL {
        let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let d = base.appendingPathComponent("WorldIntelCache", isDirectory: true)
        try? fm.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }

    private func fileURL(_ key: String) -> URL {
        dir.appendingPathComponent("\(key).json")
    }

    private func metaURL(_ key: String) -> URL {
        dir.appendingPathComponent("\(key).meta")
    }

    func save<T: Encodable>(_ value: T, key: String) {
        let encoder = JSONEncoder()
        if let data = try? encoder.encode(value) {
            try? data.write(to: fileURL(key))
        }
        try? String(Date().timeIntervalSince1970).write(to: metaURL(key), atomically: true, encoding: .utf8)
    }

    func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        guard let data = try? Data(contentsOf: fileURL(key)) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }

    /// Age of the cache in seconds, or nil if never cached.
    func age(of key: String) -> TimeInterval? {
        guard let s = try? String(contentsOf: metaURL(key), encoding: .utf8),
              let t = Double(s) else { return nil }
        return Date().timeIntervalSince1970 - t
    }

    func clearAll() {
        try? fm.removeItem(at: dir)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
    }
}

/// TTLs — the app refreshes a source only after its TTL expires.
enum TTL {
    static let news: TimeInterval = 180        // 3 min
    static let disasters: TimeInterval = 300   // 5 min
    static let map: TimeInterval = 600         // 10 min
    static let indicators: TimeInterval = 3600 // 1 hour
}
