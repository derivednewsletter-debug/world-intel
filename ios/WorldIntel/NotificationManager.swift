import Foundation
import UserNotifications
import UIKit

/// Delivers local notifications for major events when the app refreshes.
/// Runs only while the app is open — zero background battery cost.
final class NotificationManager {
    static let shared = NotificationManager()
    private let notifiedKey = "notifiedEventIds"

    func requestPermissionIfNeeded() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            if settings.authorizationStatus == .notDetermined {
                UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
            }
        }
    }

    /// Called after a successful refresh — fires alerts for new severity ≥ 4 events.
    func checkAndNotify(events: [WorldEvent]) {
        guard UserDefaults.standard.bool(forKey: "notificationsEnabled") else { return }
        var notified = Set(UserDefaults.standard.stringArray(forKey: notifiedKey) ?? [])
        let majors = events.filter { $0.severity >= 4 }
        for e in majors where !notified.contains(e.id) {
            let content = UNMutableNotificationContent()
            content.title = "🌍 \(e.category.label.uppercased())"
            content.body = e.title
            content.sound = .default
            let req = UNNotificationRequest(identifier: "major-\(e.id)", content: content, trigger: nil)
            UNUserNotificationCenter.current().add(req)
            notified.insert(e.id)
        }
        if notified.count > 300 {
            notified = Set(notified.suffix(300))
        }
        UserDefaults.standard.set(Array(notified), forKey: notifiedKey)
    }

    /// Registers for remote push and sends the device token to the user's Mac backend.
    func enableRemotePush() {
        UIApplication.shared.registerForRemoteNotifications()
    }
}
