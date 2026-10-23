import UIKit
import WebKit

/// Shows LifeGather's web UI from the user's own server. On first launch it asks
/// for the server's home-network address; the page itself does everything else.
/// Mirrors the Android app's MainActivity.
final class MainViewController: UIViewController {
    private enum Screen { case none, setup, web, offline }

    private static let serverKey = "server"
    private let defaults = UserDefaults.standard
    private let inbox = ShareInbox.shared()
    private var screen = Screen.none
    private var web: WKWebView?
    /// What the user typed, e.g. http://192.168.1.20:8787.
    private var server = UserDefaults.standard.string(forKey: MainViewController.serverKey)
    /// What the web view opens: the loopback relay for plain HTTP, otherwise the server.
    private var webOrigin: String?
    /// The share last opened in the page, so it is not opened twice.
    private var openedShare: String?

    private static let green = UIColor(red: 0x23 / 255, green: 0x4e / 255, blue: 0x3c / 255, alpha: 1)
    private static let problemRed = UIColor(red: 0xb3 / 255, green: 0x26 / 255, blue: 0x1e / 255, alpha: 1)

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
    }

    // MARK: App life cycle

    func becameActive() {
        switch screen {
        case .setup:
            return
        case .offline:
            // The user taps Try again, unless a new share is waiting.
            if let query = newShare() { openServer(query: query, reload: true) }
        case .none where server == nil:
            showSetup(problem: nil)
        case .none, .web:
            openServer(query: newShare())
        }
    }

    func enteredBackground() {
        LoopbackRelay.shared.stop()
    }

    /// A share saved by the Share extension since the page last opened one.
    private func newShare() -> String? {
        guard let query = inbox?.pending(), query != openedShare else { return nil }
        return query
    }

    // MARK: First launch: ask for the server address

    func showSetup(problem: String?) {
        screen = .setup
        let title = label("Connect to LifeGather", size: 26, bold: true)
        let help = label("Type the address you use to open LifeGather on your home network, for example "
            + "http://192.168.1.20:8787. Your iPhone must be on the same Wi-Fi.", size: 17, bold: false)
        let field = UITextField()
        field.borderStyle = .roundedRect
        field.font = .preferredFont(forTextStyle: .body)
        field.placeholder = "http://192.168.1.20:8787"
        field.text = server ?? "http://"
        field.keyboardType = .URL
        field.autocapitalizationType = .none
        field.autocorrectionType = .no
        field.spellCheckingType = .no
        field.returnKeyType = .go
        field.clearButtonMode = .whileEditing
        field.accessibilityLabel = "Server address"
        let status = label(problem ?? "", size: 16, bold: false)
        status.textColor = MainViewController.problemRed
        let connect = UIButton(type: .system)
        connect.setTitle("Connect", for: .normal)
        connect.titleLabel?.font = .preferredFont(forTextStyle: .headline)
        connect.backgroundColor = MainViewController.green
        connect.setTitleColor(.white, for: .normal)
        connect.setTitleColor(.lightGray, for: .disabled)
        connect.layer.cornerRadius = 10
        connect.heightAnchor.constraint(greaterThanOrEqualToConstant: 48).isActive = true
        field.heightAnchor.constraint(greaterThanOrEqualToConstant: 44).isActive = true

        let go = UIAction { [weak self, weak field, weak status, weak connect] _ in
            guard let self = self, let field = field, let status = status, let connect = connect else { return }
            field.resignFirstResponder()
            guard let origin = ServerAddress.normalize(field.text) else {
                status.textColor = MainViewController.problemRed
                status.text = "That doesn't look like an address. Try something like http://192.168.1.20:8787"
                return
            }
            connect.isEnabled = false
            status.textColor = .secondaryLabel
            status.text = "Checking \(origin) …"
            self.check(origin) { problem in
                connect.isEnabled = true
                if let problem = problem {
                    status.textColor = MainViewController.problemRed
                    status.text = problem
                    return
                }
                if origin != self.server { self.forgetPreviousServer() }
                self.defaults.set(origin, forKey: MainViewController.serverKey)
                self.server = origin
                self.openServer(query: self.newShare())
            }
        }
        connect.addAction(go, for: .touchUpInside)
        field.addAction(go, for: .editingDidEndOnExit)

        var views: [UIView] = [title, help, field, connect, status]
        if server != nil {
            views.append(button("Back to LifeGather") { [weak self] in
                self?.screen = .none
                self?.openServer(query: nil)
            })
        }
        show(column(views))
        field.becomeFirstResponder()
    }

    /// A different server must not see the old one's sign-in cookie or cached pages.
    private func forgetPreviousServer() {
        web?.removeFromSuperview()
        web = nil
        openedShare = nil
        WKWebsiteDataStore.default().removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(),
                                                modifiedSince: .distantPast) {}
    }

    /// Calls back with nil when LifeGather answers at origin, otherwise a message for the user.
    private func check(_ origin: String, done: @escaping (String?) -> Void) {
        let unreachable = "Couldn't reach LifeGather at \(origin). Check the address, that your iPhone is on your "
            + "home Wi-Fi, and that the computer or NAS running LifeGather is on. If the iPhone asked to find "
            + "devices on your local network, tap Allow and try again."
        startRelay(for: origin) { base in
            guard let base = base, let url = URL(string: base + "/health") else {
                done(unreachable)
                return
            }
            var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 6)
            request.httpShouldHandleCookies = false
            HealthCheck.session.dataTask(with: request) { data, response, error in
                let problem: String?
                if error != nil {
                    problem = unreachable
                } else if let code = (response as? HTTPURLResponse)?.statusCode, code != 200 {
                    problem = "Something answered at that address, but it isn't LifeGather (code \(code))."
                } else if let data = data, String(decoding: data.prefix(1024), as: UTF8.self).contains("\"ok\"") {
                    problem = nil
                } else {
                    problem = "Something answered at that address, but it isn't LifeGather."
                }
                DispatchQueue.main.async { done(problem) }
            }.resume()
        }
    }

    // MARK: The web app

    private func openServer(query: String?, reload: Bool = false) {
        guard let server = server else {
            showSetup(problem: nil)
            return
        }
        startRelay(for: server) { [weak self] base in
            guard let self = self else { return }
            guard let base = base else {
                self.showSetup(problem: "The app couldn't start its connection to LifeGather. Close the app "
                    + "completely and open it again.")
                return
            }
            self.webOrigin = base
            let web = self.web ?? self.createWebView()
            self.web = web
            if self.screen != .web {
                self.screen = .web
                self.show(web)
            }
            if let query = query {
                self.openedShare = query
                web.load(URLRequest(url: URL(string: base + "/" + query)!))
            } else if reload || !ServerAddress.sameOrigin(base, web.url) {
                web.load(URLRequest(url: URL(string: base + "/")!))
            }
        }
    }

    /// Plain-HTTP home servers are opened through LoopbackRelay; HTTPS ones
    /// directly. Calls back with the origin to open, or nil.
    private func startRelay(for origin: String, done: @escaping (String?) -> Void) {
        guard let target = ServerAddress.relayTarget(origin) else {
            done(origin)
            return
        }
        LoopbackRelay.shared.start(host: target.host, port: target.port) { error in
            done(error == nil ? LoopbackRelay.origin : nil)
        }
    }

    private func createWebView() -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.allowsInlineMediaPlayback = true
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
        configuration.applicationNameForUserAgent = "Mobile/15E148 LifeGatherIOS/\(version)"
        configuration.userContentController.addScriptMessageHandler(
            ShareBridge(owner: self), contentWorld: .page, name: ShareBridge.name)
        let web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.scrollView.contentInsetAdjustmentBehavior = .never
        #if DEBUG
        if #available(iOS 16.4, *) { web.isInspectable = true }
        #endif
        return web
    }

    /// Pages on the server stay in the app; any other link opens in Safari.
    private func leaveApp(_ url: URL) {
        guard let scheme = url.scheme?.lowercased(), ["http", "https", "mailto", "tel"].contains(scheme) else { return }
        UIApplication.shared.open(url)
    }

    private func showOffline() {
        screen = .offline
        let title = label("Can't reach LifeGather", size: 26, bold: true)
        let help = label("The app couldn't open \(server ?? "your server"). Make sure your iPhone is on your home "
            + "Wi-Fi and the computer or NAS running LifeGather is switched on.", size: 17, bold: false)
        let retry = button("Try again") { [weak self] in
            self?.openServer(query: nil, reload: true)
        }
        let change = button("Change server address") { [weak self] in self?.showSetup(problem: nil) }
        show(column([title, help, retry, change]))
    }

    // MARK: Files shared from other apps

    /// Lets the signed-in page collect files from the Share extension, once:
    /// {action: "list", id} returns [{name, type, size}], then
    /// {action: "file", id, index} returns each file as base64 and deletes it.
    private final class ShareBridge: NSObject, WKScriptMessageHandlerWithReply {
        static let name = "lifegatherShare"
        weak var owner: MainViewController?

        init(owner: MainViewController) {
            self.owner = owner
        }

        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                                   replyHandler: @escaping (Any?, String?) -> Void) {
            guard let owner = owner, message.frameInfo.isMainFrame,
                  owner.isWebOrigin(message.frameInfo.securityOrigin) else {
                replyHandler(nil, "Not available here")
                return
            }
            guard let body = message.body as? [String: Any], let id = body["id"] as? String,
                  let inbox = owner.inbox else {
                replyHandler(nil, "Nothing shared")
                return
            }
            switch body["action"] as? String {
            case "list":
                let entries = inbox.claim(id) ?? []
                replyHandler(entries.map { entry -> [String: Any] in
                    ["name": entry.name, "type": entry.type, "size": entry.size]
                }, nil)
            case "file":
                let index = (body["index"] as? NSNumber)?.intValue ?? -1
                replyHandler(inbox.take(id, index: index)?.base64EncodedString(), nil)
            default:
                replyHandler(nil, "Unknown request")
            }
        }
    }

    fileprivate func isWebOrigin(_ origin: WKSecurityOrigin) -> Bool {
        let authority = origin.port == 0 ? origin.host : "\(origin.host):\(origin.port)"
        return webOrigin != nil && ServerAddress.normalize("\(origin.protocol)://\(authority)") == webOrigin
    }

    // MARK: Small layout helpers for the two native screens

    private func show(_ content: UIView) {
        view.subviews.forEach { $0.removeFromSuperview() }
        content.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(content)
        let guide = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            content.topAnchor.constraint(equalTo: guide.topAnchor),
            content.bottomAnchor.constraint(equalTo: guide.bottomAnchor),
            content.leadingAnchor.constraint(equalTo: guide.leadingAnchor),
            content.trailingAnchor.constraint(equalTo: guide.trailingAnchor),
        ])
    }

    private func column(_ views: [UIView]) -> UIView {
        let stack = UIStackView(arrangedSubviews: views)
        stack.axis = .vertical
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        let scroll = UIScrollView()
        scroll.keyboardDismissMode = .interactive
        scroll.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 48),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -24),
            stack.leadingAnchor.constraint(equalTo: scroll.frameLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: scroll.frameLayoutGuide.trailingAnchor, constant: -24),
        ])
        return scroll
    }

    private func label(_ text: String, size: CGFloat, bold: Bool) -> UILabel {
        let label = UILabel()
        label.text = text
        label.numberOfLines = 0
        label.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        label.adjustsFontForContentSizeCategory = true
        label.textColor = bold ? UIColor { $0.userInterfaceStyle == .dark ? .white : MainViewController.green }
            : .secondaryLabel
        if bold { label.accessibilityTraits.insert(.header) }
        return label
    }

    private func button(_ title: String, action: @escaping () -> Void) -> UIButton {
        let button = UIButton(type: .system, primaryAction: UIAction(title: title) { _ in action() })
        button.titleLabel?.font = .preferredFont(forTextStyle: .headline)
        button.heightAnchor.constraint(greaterThanOrEqualToConstant: 44).isActive = true
        return button
    }

    private func alert(_ message: String) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }
}

// MARK: - Navigation

extension MainViewController: WKNavigationDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        let scheme = url.scheme?.lowercased() ?? ""
        if ["about", "blob", "data"].contains(scheme) || ServerAddress.sameOrigin(webOrigin, url)
            || action.targetFrame?.isMainFrame == false {
            return decisionHandler(.allow)
        }
        leaveApp(url)
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition")
        if response.isForMainFrame && (!response.canShowMIMEType
            || disposition?.lowercased().hasPrefix("attachment") == true) {
            alert("Downloads aren't available in the iPhone app yet. Use LifeGather on your computer.")
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let error = error as NSError
        // Cancelled loads and links handed to Safari are not failures.
        if error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled { return }
        if error.domain == "WebKitErrorDomain" && error.code == 102 { return }
        showOffline()
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }
}

// MARK: - New windows and JavaScript dialogs

extension MainViewController: WKUIDelegate {
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if ServerAddress.sameOrigin(webOrigin, url) { webView.load(action.request) } else { leaveApp(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        alert.addTextField { $0.text = defaultText }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(nil) })
        alert.addAction(UIAlertAction(title: "OK", style: .default) { [weak alert] _ in
            completionHandler(alert?.textFields?.first?.text)
        })
        present(alert, animated: true)
    }
}

/// Health checks never follow redirects, so a login page elsewhere can't pass for LifeGather.
private final class HealthCheck: NSObject, URLSessionTaskDelegate {
    static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 6
        return URLSession(configuration: configuration, delegate: HealthCheck(), delegateQueue: nil)
    }()

    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
