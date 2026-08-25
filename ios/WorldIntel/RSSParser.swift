import Foundation

struct RSSItem {
    var title: String?
    var link: String?
    var pubDate: String?
    var summary: String?
    var image: String?
    var geoLat: Double?
    var geoLon: Double?

    var date: Double? {
        guard let pubDate else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        // Common RSS date formats
        f.dateFormat = "EEE, dd MMM yyyy HH:mm:ss Z"
        if let d = f.date(from: pubDate) { return d.timeIntervalSince1970 * 1000 }
        f.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        if let d = f.date(from: pubDate) { return d.timeIntervalSince1970 * 1000 }
        if let d = ISO8601DateFormatter().date(from: pubDate) { return d.timeIntervalSince1970 * 1000 }
        return nil
    }

    var geo: Geo? {
        if let geoLat, let geoLon { return Geo(lat: geoLat, lon: geoLon, place: nil) }
        return nil
    }
}

/// Minimal streaming XML parser for RSS/Atom — no third-party dependencies.
final class RSSParser: NSObject, XMLParserDelegate {
    private var items: [RSSItem] = []
    private var currentItem: RSSItem?
    private var currentElement = ""
    private var currentText = ""
    private var elementAttributes: [String: String] = [:]

    func parse(data: Data) throws -> [RSSItem] {
        items = []
        let parser = XMLParser(data: data)
        parser.delegate = self
        _ = parser.parse()
        return items
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
        currentElement = elementName
        currentText = ""
        elementAttributes = attributeDict ?? [:]
        if elementName == "item" || elementName == "entry" {
            currentItem = RSSItem()
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        currentText += string
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        let text = currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if elementName == "item" || elementName == "entry" {
            if let item = currentItem { items.append(item) }
            currentItem = nil
            return
        }
        guard var item = currentItem else { return }
        switch elementName {
        case "title": item.title = text
        case "link":
            if item.link == nil { item.link = text }
        case "pubDate", "published", "updated", "dc:date": item.pubDate = text
        case "description", "summary", "content:encoded", "content": item.summary = text
        case "media:content", "media:thumbnail", "enclosure":
            if let url = elementAttributes["url"] { item.image = url }
        case "geo:lat", "georss:point":
            if elementName == "geo:lat" {
                item.geoLat = Double(text)
            } else {
                // georss:point is "lat lon"
                let parts = text.split(separator: " ")
                if parts.count == 2 {
                    item.geoLat = Double(parts[0])
                    item.geoLon = Double(parts[1])
                }
            }
        case "geo:long": item.geoLon = Double(text)
        default: break
        }
        currentItem = item
    }
}
