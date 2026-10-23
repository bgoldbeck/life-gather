package io.github.bgoldbeck.lifegather;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * Passes the app's connections from http://127.0.0.1:8787 on the phone to the
 * LifeGather server on the home network, unchanged.
 *
 * A self-hosted plain-HTTP installation only accepts sign-in and changes from
 * its configured address, http://127.0.0.1:8787. Opening it through this relay
 * means the server sees exactly that address, so its sign-in and request
 * checks stay as they are. The relay listens on the phone's loopback address
 * only, so nothing outside the phone can use it.
 */
final class LoopbackRelay {
    static final int PORT = 8787;
    static final String ORIGIN = "http://127.0.0.1:" + PORT;

    private static LoopbackRelay instance;

    private final ServerSocket listener;
    private volatile InetSocketAddress target;

    private LoopbackRelay() throws IOException {
        listener = new ServerSocket();
        listener.setReuseAddress(true);
        listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), PORT));
    }

    /** Starts the relay once per app process, or points it at a new server. */
    static synchronized void start(String host, int port) throws IOException {
        if (instance == null) {
            instance = new LoopbackRelay();
            final LoopbackRelay relay = instance;
            Thread accept = new Thread(new Runnable() {
                @Override
                public void run() {
                    relay.acceptLoop();
                }
            }, "lifegather-relay");
            accept.setDaemon(true);
            accept.start();
        }
        instance.target = new InetSocketAddress(host, port);
    }

    private void acceptLoop() {
        while (!listener.isClosed()) {
            final Socket client;
            try {
                client = listener.accept();
            } catch (IOException e) {
                continue;
            }
            Thread connection = new Thread(new Runnable() {
                @Override
                public void run() {
                    relay(client, target);
                }
            }, "lifegather-relay-connection");
            connection.setDaemon(true);
            connection.start();
        }
    }

    private static void relay(final Socket client, InetSocketAddress address) {
        final Socket server = new Socket();
        try {
            // A fresh address each time, so a changed DHCP lease is picked up.
            server.connect(new InetSocketAddress(address.getHostString(), address.getPort()), 8000);
            Thread upload = new Thread(new Runnable() {
                @Override
                public void run() {
                    pump(client, server);
                }
            }, "lifegather-relay-upload");
            upload.setDaemon(true);
            upload.start();
            pump(server, client);
        } catch (IOException e) {
            // The page shows its own "can't reach LifeGather" screen.
        } finally {
            close(server);
            close(client);
        }
    }

    private static void pump(Socket from, Socket to) {
        byte[] buffer = new byte[32 * 1024];
        try {
            InputStream in = from.getInputStream();
            OutputStream out = to.getOutputStream();
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
                out.flush();
            }
            to.shutdownOutput();
        } catch (IOException e) {
            close(from);
            close(to);
        }
    }

    private static void close(Socket socket) {
        try {
            socket.close();
        } catch (IOException e) {
            // Already closed.
        }
    }
}
