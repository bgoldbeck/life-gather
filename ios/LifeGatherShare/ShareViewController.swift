import ImageIO
import UIKit
import UniformTypeIdentifiers

/// "Share to LifeGather" from Photos, Files, Mail and other apps. Copies the
/// shared photos and files into the App Group folder (see ShareInbox) and tells
/// the user to open LifeGather, where the signed-in page asks whether to save
/// them to Photos or Documents. The extension never talks to the server.
final class ShareViewController: UIViewController {
    /// Photo types LifeGather takes as they are; other images become JPEG.
    private static let photoTypes: [UTType] = [.jpeg, .png, .webP]

    private let stack = UIStackView()
    private var started = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        stack.axis = .vertical
        stack.spacing = 16
        stack.alignment = .fill
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerYAnchor.constraint(equalTo: view.safeAreaLayoutGuide.centerYAnchor),
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
        ])
        let spinner = UIActivityIndicatorView(style: .large)
        spinner.startAnimating()
        show("Saving for LifeGather…", nil, extra: spinner, done: false)
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !started else { return }
        started = true
        let providers = (extensionContext?.inputItems as? [NSExtensionItem] ?? []).flatMap { $0.attachments ?? [] }
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Self.collect(providers)
            DispatchQueue.main.async { self.finished(result) }
        }
    }

    private enum Result { case saved(Int, more: Bool), nothing, failed }

    private static func collect(_ providers: [NSItemProvider]) -> Result {
        guard let inbox = ShareInbox.shared(), let draft = try? inbox.begin() else { return .failed }
        var more = false
        for provider in providers {
            if draft.count >= ShareInbox.limit {
                draft.markMore()
                more = true
                break
            }
            save(provider, into: draft)
        }
        do {
            return try inbox.commit(draft) ? .saved(draft.count, more: more) : .nothing
        } catch {
            inbox.discard(draft)
            return .failed
        }
    }

    /// Copies one shared item, waiting for it. Web links are skipped.
    private static func save(_ provider: NSItemProvider, into draft: ShareInbox.Draft) {
        let types = provider.registeredTypeIdentifiers.compactMap { UTType($0) }
        let photo = types.first { type in photoTypes.contains { type.conforms(to: $0) } }
        let image = types.first { $0.conforms(to: .image) }
        let file = types.first { $0.conforms(to: .data) && !$0.conforms(to: .url) }
        guard let type = photo ?? image ?? file else { return }
        let convert = photo == nil && image != nil
        let wait = DispatchSemaphore(value: 0)
        provider.loadFileRepresentation(forTypeIdentifier: type.identifier) { url, _ in
            defer { wait.signal() }
            guard let url = url else { return }
            var name = provider.suggestedName ?? url.deletingPathExtension().lastPathComponent
            if convert {
                let jpeg = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".jpg")
                defer { try? FileManager.default.removeItem(at: jpeg) }
                guard toJPEG(url, jpeg) else { return }
                name = (name as NSString).deletingPathExtension + ".jpg"
                try? draft.add(copying: jpeg, name: name, type: "image/jpeg")
                return
            }
            if (name as NSString).pathExtension.isEmpty {
                let ext = type.preferredFilenameExtension ?? url.pathExtension
                if !ext.isEmpty { name += "." + ext }
            }
            try? draft.add(copying: url, name: name, type: type.preferredMIMEType ?? "")
        }
        wait.wait()
    }

    /// HEIC and other photo formats become JPEG, keeping the photo's date and
    /// other details, because LifeGather saves JPEG, PNG and WebP photos.
    private static func toJPEG(_ source: URL, _ target: URL) -> Bool {
        guard let input = CGImageSourceCreateWithURL(source as CFURL, nil),
              let output = CGImageDestinationCreateWithURL(target as CFURL, UTType.jpeg.identifier as CFString, 1, nil)
        else { return false }
        let options = [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary
        CGImageDestinationAddImageFromSource(output, input, 0, options)
        return CGImageDestinationFinalize(output)
    }

    private func finished(_ result: Result) {
        switch result {
        case .saved(let count, let more):
            let what = count == 1 ? "1 file is" : "\(count) files are"
            var detail = "Open the LifeGather app to choose whether to keep it in Photos or Documents. "
                + "\(what) waiting there for an hour."
            if more { detail += " Only the first \(ShareInbox.limit) were kept." }
            show("Saved for LifeGather", detail, extra: nil, done: true)
        case .nothing:
            show("Nothing to save", "LifeGather takes photos and files such as PDFs, Word or Excel documents.",
                 extra: nil, done: true)
        case .failed:
            show("Couldn't save", "LifeGather couldn't keep these files. Try again, or open LifeGather and add "
                + "them there.", extra: nil, done: true)
        }
    }

    private func show(_ title: String, _ detail: String?, extra: UIView?, done: Bool) {
        stack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        let heading = UILabel()
        heading.text = title
        heading.font = .preferredFont(forTextStyle: .title2)
        heading.adjustsFontForContentSizeCategory = true
        heading.numberOfLines = 0
        heading.textAlignment = .center
        heading.accessibilityTraits.insert(.header)
        stack.addArrangedSubview(heading)
        if let extra = extra { stack.addArrangedSubview(extra) }
        if let detail = detail {
            let body = UILabel()
            body.text = detail
            body.font = .preferredFont(forTextStyle: .body)
            body.adjustsFontForContentSizeCategory = true
            body.textColor = .secondaryLabel
            body.numberOfLines = 0
            body.textAlignment = .center
            stack.addArrangedSubview(body)
        }
        if done {
            let button = UIButton(type: .system, primaryAction: UIAction(title: "Done") { [weak self] _ in
                self?.extensionContext?.completeRequest(returningItems: nil)
            })
            button.titleLabel?.font = .preferredFont(forTextStyle: .headline)
            button.heightAnchor.constraint(greaterThanOrEqualToConstant: 44).isActive = true
            stack.addArrangedSubview(button)
        }
    }
}
