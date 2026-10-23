import Foundation
import Network

/// Passes the app's connections from http://127.0.0.1:8787 on the iPhone to the
/// LifeGather server on the home network, unchanged. Same idea as the Android
/// app's LoopbackRelay.java.
///
/// A self-hosted plain-HTTP installation only accepts sign-in and changes from
/// its configured address, http://127.0.0.1:8787. Opening it through this relay
/// means the server sees exactly that address, so its sign-in and request
/// checks stay as they are. The relay listens on the iPhone's loopback address
/// only, so nothing outside the phone can use it. iOS stops it while the app is
/// in the background; `start` brings it back when the app returns.
final class LoopbackRelay {
    static let port: UInt16 = 8787
    static let origin = "http://127.0.0.1:\(port)"
    static let shared = LoopbackRelay()

    private let queue = DispatchQueue(label: "lifegather.relay")
    private var listener: NWListener?
    private var ready = false
    private var waiting: [(Error?) -> Void] = []
    private var target: (host: String, port: UInt16)?

    private init() {}

    /// Points the relay at host:port and makes sure it is listening. `done` runs
    /// on the main queue with nil once it is, or the error that stopped it.
    func start(host: String, port: UInt16, done: @escaping (Error?) -> Void) {
        queue.async {
            self.target = (host, port)
            if self.listener != nil && self.ready {
                DispatchQueue.main.async { done(nil) }
                return
            }
            self.waiting.append(done)
            if self.listener == nil { self.listen() }
        }
    }

    /// Called when the app goes to the background, where iOS would close the
    /// listening socket anyway; the next `start` opens a fresh one.
    func stop() {
        queue.async {
            self.listener?.cancel()
            self.listener = nil
            self.ready = false
            if !self.waiting.isEmpty { self.finish(CancellationError()) }
        }
    }

    private func listen() {
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: LoopbackRelay.port)!)
        parameters.allowLocalEndpointReuse = true
        parameters.acceptLocalOnly = true
        let listener: NWListener
        do {
            listener = try NWListener(using: parameters)
        } catch {
            finish(error)
            return
        }
        self.listener = listener
        listener.newConnectionHandler = { [weak self] client in self?.relay(client) }
        listener.stateUpdateHandler = { [weak self, weak listener] state in
            guard let self = self, let listener = listener, self.listener === listener else { return }
            switch state {
            case .ready:
                self.ready = true
                self.finish(nil)
            case .failed(let error):
                listener.cancel()
                self.listener = nil
                self.ready = false
                self.finish(error)
            case .cancelled:
                self.listener = nil
                self.ready = false
            default:
                break
            }
        }
        listener.start(queue: queue)
    }

    private func finish(_ error: Error?) {
        let callbacks = waiting
        waiting = []
        DispatchQueue.main.async { callbacks.forEach { $0(error) } }
    }

    private func relay(_ client: NWConnection) {
        guard let target = target, let port = NWEndpoint.Port(rawValue: target.port) else {
            client.cancel()
            return
        }
        let tcp = NWProtocolTCP.Options()
        tcp.connectionTimeout = 8
        // A fresh lookup each time, so a changed DHCP lease is picked up.
        let server = NWConnection(host: NWEndpoint.Host(target.host), port: port, using: NWParameters(tls: nil, tcp: tcp))
        let pair = Pair(client: client, server: server)
        server.stateUpdateHandler = { state in
            switch state {
            case .ready:
                pair.pump(from: client, to: server)
                pair.pump(from: server, to: client)
            case .failed, .waiting:
                // The page shows its own "can't reach LifeGather" screen.
                pair.close()
            default:
                break
            }
        }
        client.stateUpdateHandler = { state in
            if case .failed = state { pair.close() }
        }
        client.start(queue: queue)
        server.start(queue: queue)
    }

    /// One relayed connection: bytes copied both ways until both sides finish.
    private final class Pair {
        let client: NWConnection
        let server: NWConnection
        private var finished = 0
        private var closed = false

        init(client: NWConnection, server: NWConnection) {
            self.client = client
            self.server = server
        }

        func pump(from: NWConnection, to: NWConnection) {
            from.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { data, _, isComplete, error in
                if let data = data, !data.isEmpty {
                    to.send(content: data, completion: .contentProcessed { sendError in
                        if sendError != nil {
                            self.close()
                        } else if isComplete {
                            self.endOfStream(to)
                        } else {
                            self.pump(from: from, to: to)
                        }
                    })
                } else if isComplete {
                    self.endOfStream(to)
                } else if error != nil {
                    self.close()
                } else {
                    self.pump(from: from, to: to)
                }
            }
        }

        private func endOfStream(_ to: NWConnection) {
            to.send(content: nil, contentContext: .finalMessage, isComplete: true, completion: .contentProcessed { _ in
                self.finished += 1
                if self.finished == 2 { self.close() }
            })
        }

        func close() {
            guard !closed else { return }
            closed = true
            client.cancel()
            server.cancel()
        }
    }
}
