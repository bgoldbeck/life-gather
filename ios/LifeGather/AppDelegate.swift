import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    static let changeServerShortcut = "change-server"

    var window: UIWindow?
    private let main = MainViewController()

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = main
        window.makeKeyAndVisible()
        self.window = window
        if let shortcut = options?[.shortcutItem] as? UIApplicationShortcutItem {
            handle(shortcut)
            return false
        }
        return true
    }

    // Home-screen quick action: touch and hold the app icon.
    func application(_ application: UIApplication, performActionFor shortcut: UIApplicationShortcutItem,
                     completionHandler: @escaping (Bool) -> Void) {
        completionHandler(handle(shortcut))
    }

    @discardableResult
    private func handle(_ shortcut: UIApplicationShortcutItem) -> Bool {
        guard shortcut.type == AppDelegate.changeServerShortcut else { return false }
        main.showSetup(problem: nil)
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        main.enteredBackground()
    }

    // Also runs right after launch.
    func applicationDidBecomeActive(_ application: UIApplication) {
        main.becameActive()
    }
}
