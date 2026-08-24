import Foundation

enum Category: String, Codable, CaseIterable, Identifiable {
    case news, conflict, disaster, weather, markets, energy, tech, supplychain, health

    var id: String { rawValue }

    var label: String {
        switch self {
        case .news: return "News"
        case .conflict: return "Conflict"
        case .disaster: return "Disasters"
        case .weather: return "Weather"
        case .markets: return "Markets"
        case .energy: return "Energy"
        case .tech: return "Tech & Cyber"
        case .supplychain: return "Supply Chain"
        case .health: return "Health"
        }
    }

    var color: ColorValue {
        switch self {
        case .news: return ColorValue(hex: "#4f8cff")
        case .conflict: return ColorValue(hex: "#ff4d4f")
        case .disaster: return ColorValue(hex: "#ff7a45")
        case .weather: return ColorValue(hex: "#13c2c2")
        case .markets: return ColorValue(hex: "#b37feb")
        case .energy: return ColorValue(hex: "#faad14")
        case .tech: return ColorValue(hex: "#40c057")
        case .supplychain: return ColorValue(hex: "#f06595")
        case .health: return ColorValue(hex: "#36cfc9")
        }
    }
}

/// Simple Codable color so we can serialize without importing SwiftUI into models.
struct ColorValue: Codable {
    let hex: String
}

struct Geo: Codable {
    let lat: Double
    let lon: Double
    let place: String?
}

struct WorldEvent: Codable, Identifiable, Hashable {
    let id: String
    let source: String
    let category: Category
    let severity: Int
    let title: String
    let url: String?
    let summary: String?
    let published: Int
    let geo: Geo?
}

struct LiveStream: Codable, Identifiable, Hashable {
    let name: String
    let url: String
    let note: String
    var id: String { url }
}

struct SourceStatus: Codable, Identifiable {
    let source: String
    let lastRun: Int?
    let lastOk: Bool
    let lastError: String?
    let count: Int?
    var id: String { source }
}

struct StatsResponse: Codable {
    let total: Int
    let byCategory: [String: Int]
    let latest: Int?
    let updatedAt: Int
    let sources: [SourceStatus]
}

/// Economic indicator from the optional local backend (FRED) — /api/indicators.
struct Indicator: Codable, Identifiable {
    let series_id: String
    let name: String
    let category: String
    let unit: String?
    let latest_value: Double?
    let latest_date: String?
    let history: [IndicatorPoint]?
    var id: String { series_id }
}

struct IndicatorPoint: Codable {
    let date: String
    let value: Double?
}
