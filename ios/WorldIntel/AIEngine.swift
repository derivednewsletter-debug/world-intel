import Foundation

/// From-scratch intelligence engine — pure algorithms, no ML frameworks.
/// Runs in milliseconds on-device: zero battery cost.

private let STOPWORDS: Set<String> = [
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from", "as",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "will", "would", "could", "should",
    "it", "its", "his", "her", "their", "they", "them", "he", "she", "we", "you", "i", "this", "that",
    "these", "those", "not", "no", "but", "after", "before", "over", "under", "into", "during", "amid",
    "says", "said", "report", "reports", "reported", "news", "new", "first", "latest", "update", "updates",
    "us", "uk", "un", "eu", "u", "s", "vs", "de", "la", "le", "el", "who", "what", "when", "where", "why",
    "video", "photos", "breaking", "just", "one", "two", "three", "day", "week", "month", "year",
]

func tokenize(_ text: String) -> [String] {
    text.lowercased()
        .replacingOccurrences(of: "[^a-z0-9 ]+", with: " ", options: .regularExpression)
        .split(separator: " ")
        .map(String.init)
        .filter { $0.count > 3 && !STOPWORDS.contains($0) }
}

private func jaccard(_ a: Set<String>, _ b: Set<String>) -> Double {
    guard !a.isEmpty, !b.isEmpty else { return 0 }
    var inter = 0
    for t in a where b.contains(t) { inter += 1 }
    return Double(inter) / Double(a.count + b.count - inter)
}

struct StoryCluster: Identifiable {
    let id: String
    let title: String
    let category: Category
    let severity: Int
    let count: Int
    let sources: [String]
    let categories: [Category]
    let lastSeen: Double
    let momentum: Double

    var score: Double {
        let now = Date().timeIntervalSince1970 * 1000
        let recency = exp(-(now - lastSeen) / (6 * 3_600_000))
        let diversity = Double(min(sources.count, 6)) / 6
        let size = Double(min(count, 20)) / 20
        let sev = Double(severity) / 5
        return (0.35 * sev + 0.25 * diversity + 0.2 * size + 0.2 * recency) * (1 + momentum)
    }
}

func clusterEvents(_ events: [WorldEvent]) -> [StoryCluster] {
    var clusters: [(tokens: Set<String>, events: [WorldEvent])] = []
    var tokenIndex: [String: Set<Int>] = [:]  // inverted index for fast lookup
    for e in events {
        let toks = Set(tokenize(e.title))
        // Find candidate clusters via shared tokens (much faster than O(n)).
        var candidateCounts: [Int: Int] = [:]
        for t in toks {
            for ci in tokenIndex[t, default: []] {
                candidateCounts[ci, default: 0] += 1
            }
        }
        var best = -1
        var bestSim = 0.38
        for (ci, shared) in candidateCounts {
            let unionSize = clusters[ci].tokens.count + toks.count - shared
            let sim = unionSize > 0 ? Double(shared) / Double(unionSize) : 0
            if sim > bestSim { bestSim = sim; best = ci }
        }
        if best >= 0 {
            clusters[best].events.append(e)
            clusters[best].tokens.formUnion(toks)
            for t in toks {
                tokenIndex[t, default: []].insert(best)
            }
        } else {
            let idx = clusters.count
            clusters.append((toks, [e]))
            for t in toks {
                tokenIndex[t, default: []].insert(idx)
            }
        }
    }
    return clusters.compactMap { c in
        guard let rep = c.events.max(by: { ($0.severity, $0.published) < ($1.severity, $1.published) }) else { return nil }
        let now = Int(Date().timeIntervalSince1970 * 1000)
        let lastHour = c.events.filter { $0.published > now - 3_600_000 }.count
        return StoryCluster(
            id: rep.id,
            title: rep.title,
            category: rep.category,
            severity: c.events.map(\.severity).max() ?? 0,
            count: c.events.count,
            sources: Array(Set(c.events.map(\.source))),
            categories: Array(Set(c.events.map(\.category))),
            lastSeen: Double(c.events.map(\.published).max() ?? 0),
            momentum: c.events.isEmpty ? 0 : Double(lastHour) / Double(c.events.count)
        )
    }
    .sorted { $0.score > $1.score }
}

struct Spike: Identifiable {
    let term: String
    let count: Int
    let baseline: Double
    let ratio: Double
    var id: String { term }
}

func detectSpikes(_ events: [WorldEvent], windowCount: Int = 4) -> [Spike] {
    guard events.count >= 8, let newest = events.map(\.published).max(), let oldest = events.map(\.published).min() else { return [] }
    let span = max(newest - oldest, 1)
    let winMs = Double(span) / Double(windowCount)
    var buckets: [[String: Int]] = Array(repeating: [:], count: windowCount)
    for e in events {
        let idx = min(windowCount - 1, Int(Double(e.published - oldest) / winMs))
        for t in Set(tokenize(e.title)) {
            buckets[idx][t, default: 0] += 1
        }
    }
    var out: [Spike] = []
    for (term, count) in buckets[windowCount - 1] {
        var base = 0
        for i in 0..<(windowCount - 1) { base += buckets[i][term] ?? 0 }
        let baseline = Double(base) / Double(max(windowCount - 1, 1))
        if count >= 4 && Double(count) >= baseline * 2.5 {
            out.append(Spike(term: term, count: count, baseline: baseline, ratio: baseline > 0 ? Double(count) / baseline : Double(count)))
        }
    }
    return out.sorted { $0.ratio > $1.ratio }.prefix(12).map { $0 }
}

let WATCH_COUNTRIES = ["iran", "ukraine", "russia", "israel", "taiwan", "china", "north korea", "sudan", "myanmar", "venezuela"]
let WATCH_KEYWORDS = ["port congestion", "earthquake", "wildfire", "cyberattack", "ransomware", "oil price", "chip"]

struct WatchAlert: Identifiable {
    let event: WorldEvent
    let matched: [String]
    var id: String { event.id }
}

func watchAlerts(_ events: [WorldEvent], minSeverity: Int = 3) -> [WatchAlert] {
    events.compactMap { e in
        guard e.severity >= minSeverity else { return nil }
        let text = "\(e.title) \(e.summary ?? "")".lowercased()
        var matched: [String] = []
        for c in WATCH_COUNTRIES where text.contains(c) { matched.append(c) }
        for k in WATCH_KEYWORDS where text.contains(k) { matched.append(k) }
        return matched.isEmpty ? nil : WatchAlert(event: e, matched: matched)
    }
    .prefix(20)
    .map { $0 }
}

// ---------------------------------------------------------------------------
// Briefing
// ---------------------------------------------------------------------------

struct BriefingItem: Identifiable {
    let id: String
    let title: String
    let detail: String
    let severity: Int
    let url: String?
}

struct BriefingSection: Identifiable {
    let id: String
    let title: String
    let items: [BriefingItem]
}

struct Briefing {
    let headline: String
    let sections: [BriefingSection]
}

func generateBriefing(events: [WorldEvent], hours: Double = 24) -> Briefing {
    let since = Int(Date().timeIntervalSince1970 * 1000 - hours * 3_600_000)
    let recent = events.filter { $0.published >= since }
    let clusters = clusterEvents(recent).prefix(8).map { $0 }
    let breaking = recent.filter { $0.severity >= 4 }.prefix(6).map { $0 }
    let disasters = recent.filter { ["eonet", "gdacs", "usgs"].contains($0.source) }.prefix(5).map { $0 }
    let supply = recent.filter { $0.category == .supplychain || $0.category == .energy }
        .sorted { $0.severity > $1.severity }.prefix(5).map { $0 }
    let spikes = detectSpikes(recent)

    var sections: [BriefingSection] = []
    if !breaking.isEmpty {
        sections.append(BriefingSection(id: "breaking", title: "Breaking", items: breaking.map {
            BriefingItem(id: $0.id, title: $0.title, detail: "\($0.category.label) · \($0.source)", severity: $0.severity, url: $0.url)
        }))
    }
    if !clusters.isEmpty {
        sections.append(BriefingSection(id: "stories", title: "Top stories", items: clusters.map { c in
            BriefingItem(id: c.id, title: c.title, detail: "Covered by \(c.sources.count) source(s) · \(c.count) update(s)", severity: c.severity, url: nil)
        }))
    }
    if !disasters.isEmpty {
        sections.append(BriefingSection(id: "disasters", title: "Natural disasters", items: disasters.map {
            BriefingItem(id: $0.id, title: $0.title, detail: "\($0.source) · severity \($0.severity)/5", severity: $0.severity, url: $0.url)
        }))
    }
    if !supply.isEmpty {
        sections.append(BriefingSection(id: "supply", title: "Supply chain & energy watch", items: supply.map {
            BriefingItem(id: $0.id, title: $0.title, detail: "\($0.source) · severity \($0.severity)/5", severity: $0.severity, url: $0.url)
        }))
    }
    if !spikes.isEmpty {
        sections.append(BriefingSection(id: "trends", title: "Emerging trends", items: spikes.map {
            BriefingItem(id: $0.id, title: $0.term, detail: "\($0.count) mention(s) vs baseline \(String(format: "%.1f", $0.baseline))", severity: 0, url: nil)
        }))
    }

    let headline = breaking.first?.title ?? clusters.first?.title ?? "No major developments in the last 24 hours."
    return Briefing(headline: headline, sections: sections)
}

// ---------------------------------------------------------------------------
// World summary: organize ALL current events by region + category
// ---------------------------------------------------------------------------

private let REGION_MAP: [String: [String]] = [
    "Middle East": ["iran", "iraq", "israel", "palestine", "gaza", "saudi arabia", "syria", "lebanon", "jordan", "qatar", "kuwait", "oman", "yemen", "uae", "turkey"],
    "Europe": ["ukraine", "russia", "britain", "united kingdom", "france", "germany", "italy", "spain", "poland", "belarus", "finland", "sweden", "norway", "denmark", "netherlands", "belgium", "austria", "switzerland", "greece", "portugal", "ireland", "hungary", "czech", "romania", "bulgaria", "serbia", "croatia", "lithuania", "moldova", "georgia", "armenia", "azerbaijan"],
    "Asia-Pacific": ["china", "taiwan", "japan", "south korea", "north korea", "india", "pakistan", "indonesia", "philippines", "thailand", "vietnam", "malaysia", "singapore", "myanmar", "bangladesh", "sri lanka", "nepal", "afghanistan", "kazakhstan", "mongolia", "australia", "new zealand"],
    "Africa": ["egypt", "nigeria", "sudan", "south africa", "kenya", "ethiopia", "ghana", "tanzania", "uganda", "congo", "cameroon", "mali", "niger", "rwanda", "somalia", "libya", "tunisia", "algeria", "morocco", "zimbabwe", "zambia"],
    "Americas": ["united states", "america", "canada", "mexico", "brazil", "argentina", "chile", "colombia", "peru", "venezuela", "ecuador", "bolivia", "paraguay", "uruguay", "cuba", "haiti", "panama"],
]

func regionOf(_ text: String) -> String {
    let t = text.lowercased()
    for (region, terms) in REGION_MAP {
        for term in terms where t.contains(term) { return region }
    }
    return "Global"
}

struct RegionSummary: Identifiable {
    let name: String
    let count: Int
    let top: [BriefingItem]
    var id: String { name }
}

struct CategorySummary: Identifiable {
    let category: Category
    let count: Int
    let top: [BriefingItem]
    var id: String { category.rawValue }
}

struct WorldSummary {
    let opening: String
    let regions: [RegionSummary]
    let categories: [CategorySummary]
}

func generateWorldSummary(events: [WorldEvent], hours: Double = 24) -> WorldSummary {
    let since = Int(Date().timeIntervalSince1970 * 1000 - hours * 3_600_000)
    let recent = events.filter { $0.published >= since }
    let clusters = clusterEvents(recent)
    let spikes = detectSpikes(recent)

    var regionMap: [String: [StoryCluster]] = [:]
    for c in clusters {
        regionMap[regionOf(c.title), default: []].append(c)
    }
    let regions = regionMap.map { name, cl in
        RegionSummary(
            name: name,
            count: cl.count,
            top: cl.sorted { $0.score > $1.score }.prefix(3).map {
                BriefingItem(id: $0.id, title: $0.title, detail: "\($0.sources.count) source(s)", severity: $0.severity, url: nil)
            }
        )
    }.sorted { $0.count > $1.count }

    var catMap: [Category: [StoryCluster]] = [:]
    for c in clusters {
        catMap[c.category, default: []].append(c)
    }
    let categories = catMap.map { cat, cl in
        CategorySummary(
            category: cat,
            count: cl.count,
            top: cl.sorted { $0.score > $1.score }.prefix(3).map {
                BriefingItem(id: $0.id, title: $0.title, detail: "severity \($0.severity)/5", severity: $0.severity, url: nil)
            }
        )
    }.sorted { $0.count > $1.count }

    var opening = "Over the last \(Int(hours))h, \(recent.count) reports were grouped into \(clusters.count) story lines across \(regions.count) regions."
    let active = regions.filter { $0.name != "Global" }.prefix(3).map(\.name)
    if !active.isEmpty { opening += " Most active: \(active.joined(separator: ", "))." }
    if !spikes.isEmpty {
        opening += " Rising fast: " + spikes.prefix(4).map { "\($0.term) (\(String(format: "%.1f", $0.ratio))×)" }.joined(separator: ", ") + "."
    }
    if let top = clusters.first {
        opening += " The single most important story right now is: \(top.title)"
    }
    return WorldSummary(opening: opening, regions: regions, categories: categories)
}
