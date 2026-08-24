import Foundation
import CryptoKit

/// Fetches every source directly from the device — the app runs fully standalone,
/// with no dependency on the laptop backend.
actor APIClient {
    static let shared = APIClient()

    private let session: URLSession = {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 20
        cfg.timeoutIntervalForResource = 30
        cfg.httpAdditionalHeaders = ["User-Agent": "WorldIntel-iOS/1.0 (personal)"]
        return URLSession(configuration: cfg)
    }()

    private func text(_ url: URL) async throws -> String {
        let (data, resp) = try await session.data(from: url)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return String(data: data, encoding: .utf8) ?? ""
    }

    func json(_ url: URL) async throws -> Data {
        let (data, resp) = try await session.data(from: url)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    // MARK: - RSS feeds

    func rssEvents(feeds: [(name: String, url: String, category: Category)]) async -> [WorldEvent] {
        var out: [WorldEvent] = []
        for feed in feeds {
            guard let url = URL(string: feed.url) else { continue }
            if let items = try? RSSParser().parse(data: await text(url)) {
                for item in items {
                    guard let title = item.title?.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty else { continue }
                    out.append(WorldEvent(
                        id: Self.eventId(title: title, url: item.link ?? ""),
                        source: feed.name,
                        category: feed.category,
                        severity: Self.severity(title: title, base: 1),
                        title: title,
                        url: item.link,
                        summary: item.summary,
                        image: item.image,
                        published: item.date ?? Date.now.timeIntervalSince1970 * 1000,
                        geo: item.geo
                    ))
                }
            }
        }
        return out.sorted { $0.published > $1.published }
    }

    // MARK: - NASA EONET

    func eonetEvents() async -> [WorldEvent] {
        guard let url = URL(string: "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=50"),
              let data = try? await json(url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let events = json["events"] as? [[String: Any]] else { return [] }

        var out: [WorldEvent] = []
        for e in events {
            guard let title = e["title"] as? String else { continue }
            let catId = (e["categories"] as? [[String: Any]])?.first?["id"] as? String ?? ""
            let category: Category
            switch catId {
            case "severeStorms", "seaLakeIce", "drought", "dustHaze", "snow", "tempExtremes": category = .weather
            default: category = .disaster
            }
            var lat: Double = .nan, lon: Double = .nan
            if let coords = (e["geometry"] as? [[String: Any]])?.first?["coordinates"] as? [Double], coords.count >= 2 {
                lon = coords[0]; lat = coords[1]
            }
            let sourceUrl = (e["sources"] as? [[String: Any]])?.first?["url"] as? String
            let dateStr = (e["geometry"] as? [[String: Any]])?.first?["date"] as? String
            out.append(WorldEvent(
                id: Self.eventId(title: title, url: sourceUrl ?? ""),
                source: "eonet",
                category: category,
                severity: Self.severity(title: title, base: 3),
                title: title,
                url: sourceUrl,
                summary: e["description"] as? String ?? "Active event (NASA EONET)",
                image: nil,
                published: Self.isoDate(dateStr) ?? Date.now.timeIntervalSince1970 * 1000,
                geo: lat.isFinite && lon.isFinite ? Geo(lat: lat, lon: lon, place: title) : nil
            ))
        }
        return out
    }

    // MARK: - USGS earthquakes

    func usgsEvents() async -> [WorldEvent] {
        let start = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-86400))
        let q = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=\(start.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")&minmagnitude=4.5&orderby=time&limit=100"
        guard let url = URL(string: q),
              let data = try? await json(url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let features = json["features"] as? [[String: Any]] else { return [] }

        var out: [WorldEvent] = []
        for f in features {
            guard let props = f["properties"] as? [String: Any] else { continue }
            let mag = props["mag"] as? Double ?? 0
            let place = props["place"] as? String ?? "Unknown location"
            let title = String(format: "Earthquake M%.1f — %@", mag, place)
            let base = mag >= 6 ? 5 : mag >= 5.5 ? 4 : mag >= 5 ? 3 : 2
            var lat: Double = .nan, lon: Double = .nan
            if let coords = (f["geometry"] as? [String: Any])?["coordinates"] as? [Double], coords.count >= 2 {
                lon = coords[0]; lat = coords[1]
            }
            out.append(WorldEvent(
                id: Self.eventId(title: title, url: props["url"] as? String ?? ""),
                source: "usgs",
                category: .disaster,
                severity: Self.severity(title: title, base: base),
                title: title,
                url: props["url"] as? String,
                summary: nil,
                image: nil,
                published: (props["time"] as? Double) ?? Date.now.timeIntervalSince1970 * 1000,
                geo: lat.isFinite && lon.isFinite ? Geo(lat: lat, lon: lon, place: place) : nil
            ))
        }
        return out
    }

    // MARK: - GDACS alerts (RSS)

    func gdacsEvents() async -> [WorldEvent] {
        guard let url = URL(string: "https://www.gdacs.org/xml/rss.xml"),
              let items = try? RSSParser().parse(data: await text(url)) else { return [] }
        var out: [WorldEvent] = []
        for item in items {
            guard let title = item.title?.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty else { continue }
            let lower = title.lowercased()
            let base = lower.contains("red alert") ? 4 : lower.contains("orange alert") ? 3 : lower.contains("green alert") ? 2 : 1
            out.append(WorldEvent(
                id: Self.eventId(title: title, url: item.link ?? ""),
                source: "gdacs",
                category: .disaster,
                severity: Self.severity(title: title, base: base),
                title: title,
                url: item.link,
                summary: item.summary,
                image: nil,
                published: item.date ?? Date.now.timeIntervalSince1970 * 1000,
                geo: item.geo
            ))
        }
        return out
    }

    // MARK: - GDELT pointdata (world map points) — 1 call per refresh

    func gdeltPoints() async -> [WorldEvent] {
        let q = "conflict%20OR%20protest%20OR%20riot%20OR%20strike%20OR%20disaster%20OR%20earthquake%20OR%20flood"
        guard let url = URL(string: "https://api.gdeltproject.org/api/v2/doc/doc?query=\(q)&mode=pointdata&format=json&timespan=1d&maxrecords=150"),
              let data = try? await json(url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let points = json["points"] as? [[String: Any]] else { return [] }

        var out: [WorldEvent] = []
        for p in points {
            let lat = (p["lat"] as? Double) ?? (p["lat_"] as? Double) ?? .nan
            let lon = (p["lon"] as? Double) ?? (p["lon_"] as? Double) ?? .nan
            guard lat.isFinite, lon.isFinite else { continue }
            let title = (p["title"] as? String) ?? (p["name"] as? String) ?? "Event"
            out.append(WorldEvent(
                id: Self.eventId(title: title, url: "\(lat),\(lon)"),
                source: "gdelt-points",
                category: .conflict,
                severity: Self.severity(title: title, base: 2),
                title: title,
                url: p["url"] as? String,
                summary: (p["desc"] as? String) ?? "Conflict/event cluster (GDELT)",
                image: nil,
                published: Date.now.timeIntervalSince1970 * 1000,
                geo: Geo(lat: lat, lon: lon, place: title)
            ))
        }
        return out
    }

    // MARK: - Optional local backend (your Mac's dashboard, same Wi-Fi)
    // When a server URL is set in Settings, the app uses the backend's richer
    // data (full aggregated feed, FRED indicators, satellite fires, AI summary);
    // otherwise it runs fully standalone.

    func serverEvents(base: String, query: [URLQueryItem]) async -> [WorldEvent] {
        guard let url = URL(string: base)?.appendingPathComponent("api/events"),
              var comps = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return [] }
        comps.queryItems = query
        guard let u = comps.url,
              let data = try? await json(u),
              let d = try? JSONDecoder().decode(EventsResponse.self, from: data) else { return [] }
        return d.events
    }

    func serverIndicators(base: String) async -> [Indicator] {
        guard let url = URL(string: base)?.appendingPathComponent("api/indicators"),
              let data = try? await json(url),
              let d = try? JSONDecoder().decode(IndicatorsResponse.self, from: data) else { return [] }
        return d.indicators
    }

    func serverMarketData(base: String) async -> (indicators: [Indicator], events: [WorldEvent]) {
        async let inds = serverIndicators(base: base)
        async let evs = serverEvents(base: base, query: [
            URLQueryItem(name: "category", value: "markets"),
            URLQueryItem(name: "limit", value: "80"),
        ])
        return await (inds, evs)
    }

    func serverDisasters(base: String) async -> [WorldEvent] {
        async let a = serverEvents(base: base, query: [
            URLQueryItem(name: "category", value: "disaster"),
            URLQueryItem(name: "limit", value: "120"),
        ])
        async let b = serverEvents(base: base, query: [
            URLQueryItem(name: "category", value: "weather"),
            URLQueryItem(name: "limit", value: "60"),
        ])
        let (x, y) = await (a, b)
        return SourceFeeds.dedupe(x + y)
    }

    func serverBriefing(base: String) async -> Briefing? {
        guard let url = URL(string: base)?.appendingPathComponent("api/ai/briefing"),
              let data = try? await json(url),
              let d = try? JSONDecoder().decode(ServerBriefing.self, from: data) else { return nil }
        return d.toLocal()
    }

    func serverSummary(base: String) async -> WorldSummary? {
        guard let url = URL(string: base)?.appendingPathComponent("api/ai/summary"),
              let data = try? await json(url),
              let d = try? JSONDecoder().decode(ServerSummary.self, from: data) else { return nil }
        return d.toLocal()
    }

    // MARK: - Keyless money (FX + crypto, standalone)

    /// Live FX rates (open.er-api.com) + crypto prices (CoinGecko) — keyless,
    /// so the Markets tab shows real money data even without the local backend.
    func moneyIndicators() async -> [Indicator] {
        var out: [Indicator] = []
        let now = dateString()
        let fxCodes = ["EUR", "GBP", "JPY", "CNY", "CHF", "AUD", "CAD", "INR"]
        if let url = URL(string: "https://open.er-api.com/v6/latest/USD"),
           let data = try? await json(url),
           let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let rates = d["rates"] as? [String: Any] {
            for code in fxCodes {
                if let v = rates[code] as? Double {
                    out.append(Indicator(series_id: "FX:\(code)", name: "USD/\(code)",
                                         category: "money", unit: "rate",
                                         latest_value: v, latest_date: now, history: nil))
                }
            }
        }
        let coins = ["bitcoin", "ethereum", "solana"]
        let ids = coins.joined(separator: ",")
        if let url = URL(string: "https://api.coingecko.com/api/v3/simple/price?ids=\(ids)&vs_currencies=usd&include_24hr_change=true"),
           let data = try? await json(url),
           let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            for coin in coins {
                if let info = d[coin] as? [String: Any], let v = info["usd"] as? Double {
                    out.append(Indicator(series_id: "CRYPTO:\(coin)", name: "\(coin.capitalized) (USD)",
                                         category: "money", unit: "USD",
                                         latest_value: v, latest_date: now, history: nil))
                }
            }
        }
        return out
    }

    private func dateString() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
        f.timeZone = TimeZone(identifier: "UTC")
        return f.string(from: Date())
    }

    // MARK: - Helpers

    static func eventId(title: String, url: String) -> String {
        let norm = title.lowercased().replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
        let base = "\(norm)|\(url.lowercased().replacingOccurrences(of: "^https?://", with: "", options: .regularExpression))"
        let digest = Insecure.SHA1.hash(data: Data(base.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    static func severity(title: String, base: Int) -> Int {
        var s = base
        let t = title.lowercased()
        let boosts: [(String, Int)] = [
            ("magnitude 6", 4), ("magnitude 5", 3), ("earthquake", 1),
            ("red alert", 4), ("orange alert", 3),
            ("hurricane", 2), ("cyclone", 2), ("typhoon", 2), ("tsunami", 3),
            ("wildfire", 2), ("volcano", 2), ("eruption", 2), ("flood", 1),
            ("killed", 2), ("deaths", 2), ("massacre", 2),
            ("war", 2), ("invasion", 2), ("missile", 2), ("airstrike", 2),
            ("cyberattack", 2), ("ransomware", 2), ("data breach", 2),
            ("outage", 1), ("port congestion", 1), ("supply chain", 1), ("freight", 1),
        ]
        for (kw, b) in boosts where t.contains(kw) { s += b }
        return max(0, min(5, s))
    }

    static func isoDate(_ s: String?) -> Double? {
        guard let s, s.count >= 10 else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = formatter.date(from: s) { return d.timeIntervalSince1970 * 1000 }
        formatter.formatOptions = [.withInternetDateTime]
        if let d = formatter.date(from: s) { return d.timeIntervalSince1970 * 1000 }
        return nil
    }
}

// ---------------------------------------------------------------------------
// Optional local backend
// ---------------------------------------------------------------------------

/// Where the local dashboard lives. Set in Settings → Local server URL.
/// When set, the app pulls the backend's full aggregated feed, FRED indicators,
/// satellite fires and the AI world summary; empty = fully standalone.
enum AppServer {
    static var baseURL: String? {
        let v = UserDefaults.standard.string(forKey: "pushServerURL")?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return v.isEmpty ? nil : v
    }
}

struct EventsResponse: Codable {
    let events: [WorldEvent]
}

struct IndicatorsResponse: Codable {
    let indicators: [Indicator]
}

/// JSON mirrors of the backend's /api/ai/briefing and /api/ai/summary responses.
struct ServerBriefing: Codable {
    let headline: String
    let sections: [ServerSection]
}

struct ServerSection: Codable {
    let title: String
    let items: [ServerItem]
}

struct ServerItem: Codable {
    let title: String
    let detail: String?
    let severity: Int
    let url: String?
}

struct ServerSummary: Codable {
    let opening: String
    let regions: [ServerRegion]
    let categories: [ServerCategory]
}

struct ServerRegion: Codable {
    let name: String
    let count: Int
    let top: [ServerTop]
}

struct ServerCategory: Codable {
    let category: String
    let count: Int
    let top: [ServerTop]
}

struct ServerTop: Codable {
    let title: String
    let severity: Int
    let url: String?
}

extension ServerBriefing {
    func toLocal() -> Briefing {
        Briefing(
            headline: headline,
            sections: sections.map { s in
                BriefingSection(id: s.title, title: s.title, items: s.items.map {
                    BriefingItem(id: UUID().uuidString, title: $0.title, detail: $0.detail ?? "", severity: $0.severity, url: $0.url)
                })
            }
        )
    }
}

extension ServerSummary {
    func toLocal() -> WorldSummary {
        WorldSummary(
            opening: opening,
            regions: regions.map { r in
                RegionSummary(name: r.name, count: r.count, top: r.top.map {
                    BriefingItem(id: UUID().uuidString, title: $0.title, detail: "severity \($0.severity)/5", severity: $0.severity, url: $0.url)
                })
            },
            categories: categories.map { c in
                CategorySummary(category: Category(rawValue: c.category) ?? .news, count: c.count, top: c.top.map {
                    BriefingItem(id: UUID().uuidString, title: $0.title, detail: "severity \($0.severity)/5", severity: $0.severity, url: $0.url)
                })
            }
        )
    }
}
