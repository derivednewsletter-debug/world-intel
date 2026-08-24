import SwiftUI

extension Color {
    init(hex: String) {
        var h = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if h.hasPrefix("#") { h.removeFirst() }
        var rgb: UInt64 = 0
        Scanner(string: h).scanHexInt64(&rgb)
        self.init(
            .sRGB,
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255,
            opacity: 1
        )
    }

    init(cv: ColorValue) { self.init(hex: cv.hex) }

    static let appBg = Color(hex: "#0b0e14")
    static let appPanel = Color(hex: "#131824")
    static let appPanel2 = Color(hex: "#1a2130")
    static let appBorder = Color(hex: "#242e40")
    static let appText = Color(hex: "#e6e9f0")
    static let appMuted = Color(hex: "#8b93a7")
    static let appAccent = Color(hex: "#4f8cff")
    static let appOk = Color(hex: "#40c057")
    static let appWarn = Color(hex: "#faad14")
    static let appErr = Color(hex: "#ff4d4f")
}

let severityColors: [Color] = [
    Color(hex: "#5cdbd3"),
    Color(hex: "#8b93a7"),
    Color(hex: "#95de64"),
    Color(hex: "#ffc53d"),
    Color(hex: "#ff7a45"),
    Color(hex: "#ff4d4f"),
]

func severityColor(_ s: Int) -> Color {
    severityColors[max(0, min(5, s))]
}

func relativeTime(_ ts: Double) -> String {
    let diff = Date().timeIntervalSince1970 * 1000 - ts
    let m = Int(diff / 60000)
    if m < 1 { return "just now" }
    if m < 60 { return "\(m)m ago" }
    let h = m / 60
    if h < 24 { return "\(h)h ago" }
    return "\(h / 24)d ago"
}

/// Themed card background.
struct Panel: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(Color.appPanel)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.appBorder, lineWidth: 1))
    }
}

extension View {
    func panel() -> some View { modifier(Panel()) }
}

struct EventRow: View {
    let event: WorldEvent

    var body: some View {
        HStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 2)
                .fill(severityColor(event.severity))
                .frame(width: 4)
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(event.category.label.uppercased())
                        .font(.caption2).bold()
                        .foregroundColor(Color(cv: event.category.color))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color(cv: event.category.color).opacity(0.15))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                    if event.severity >= 4 {
                        Text("BREAKING")
                            .font(.caption2).bold()
                            .foregroundColor(.appErr)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.appErr.opacity(0.15))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                    Text(event.source)
                        .font(.caption)
                        .foregroundColor(.appMuted)
                        .lineLimit(1)
                    Spacer()
                    Text(relativeTime(Double(event.published)))
                        .font(.caption)
                        .foregroundColor(.appMuted)
                }
                if let url = event.url, let u = URL(string: url) {
                    Link(destination: u) {
                        Text(event.title)
                            .font(.subheadline).fontWeight(.semibold)
                            .multilineTextAlignment(.leading)
                            .foregroundColor(.appText)
                    }
                } else {
                    Text(event.title)
                        .font(.subheadline).fontWeight(.semibold)
                        .multilineTextAlignment(.leading)
                        .foregroundColor(.appText)
                }
                if let place = event.geo?.place {
                    Label(place, systemImage: "mappin.and.ellipse")
                        .font(.caption)
                        .foregroundColor(.appAccent)
                }
                if let summary = event.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.caption)
                        .foregroundColor(.appMuted)
                        .lineLimit(2)
                }
            }
        }
        .padding(11)
        .panel()
    }
}

struct StatCard: View {
    let value: String
    let label: String
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.title2).bold()
            Text(label.uppercased())
                .font(.caption2)
                .foregroundColor(.appMuted)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .panel()
    }
}

/// "Updated Xm ago" based on cache age for a section key.
struct FreshnessLabel: View {
    let key: String

    var body: some View {
        Text(text).font(.caption).foregroundColor(.appMuted)
    }

    private var text: String {
        guard let age = CacheStore.shared.age(of: key) else { return "not updated yet" }
        let m = Int(age / 60)
        if m < 1 { return "updated just now" }
        if m < 60 { return "updated \(m)m ago" }
        return "updated \(m / 60)h ago"
    }
}

struct EmptyState: View {
    let text: String
    var body: some View {
        VStack(spacing: 8) {
            Text(text)
                .foregroundColor(.appMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }
}
