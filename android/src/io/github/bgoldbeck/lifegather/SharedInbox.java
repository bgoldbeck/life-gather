package io.github.bgoldbeck.lifegather;

import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Files shared to LifeGather from another app. Like the web app's service
 * worker, it holds them only until the signed-in page claims them once; the
 * page then saves each through the normal Photos or Documents upload.
 */
final class SharedInbox {
    /** Same limits as the web share target (frontend/src/shareTarget.ts, sw.js). */
    static final int LIMIT = 10;
    static final long MAX_BYTES = 8L * 1024 * 1024;
    static final long LIFETIME_MS = 5 * 60 * 1000;
    static final String PATH = "/__lifegather-android/share/";

    static final class Share {
        final List<File> files = new ArrayList<>();
        final List<String> names = new ArrayList<>();
        final List<String> types = new ArrayList<>();
        boolean more;
        boolean claimed;
    }

    private final File root;
    private final Map<String, Share> shares = new HashMap<>();

    SharedInbox(Context context) {
        root = new File(context.getCacheDir(), "shared");
        root.mkdirs();
        long cutoff = System.currentTimeMillis() - LIFETIME_MS;
        File[] old = root.listFiles();
        if (old != null) for (File dir : old) if (dir.lastModified() < cutoff) deleteTree(dir);
    }

    /** Copies the shared files and returns the address query to open, or null if nothing was shared. */
    synchronized String receive(Context context, Intent intent) {
        List<Uri> uris = new ArrayList<>();
        if (Intent.ACTION_SEND.equals(intent.getAction())) {
            Uri uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (uri != null) uris.add(uri);
        } else if (Intent.ACTION_SEND_MULTIPLE.equals(intent.getAction())) {
            ArrayList<Uri> list = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (list != null) for (Uri uri : list) if (uri != null) uris.add(uri);
        } else {
            return null;
        }
        if (uris.isEmpty()) return "?share=empty";
        String id = newId();
        File dir = new File(root, id);
        dir.mkdirs();
        Share share = new Share();
        ContentResolver resolver = context.getContentResolver();
        for (Uri uri : uris) {
            if (share.files.size() == LIMIT) {
                share.more = true;
                break;
            }
            File file = new File(dir, Integer.toString(share.files.size()));
            // Stop one byte past the limit: the page then reports the file as too large.
            if (!copy(resolver, uri, file, MAX_BYTES + 1)) continue;
            share.files.add(file);
            share.names.add(displayName(resolver, uri, share.files.size()));
            String type = resolver.getType(uri);
            share.types.add(type == null ? "" : type);
        }
        if (share.files.isEmpty()) {
            deleteTree(dir);
            return "?share=unavailable";
        }
        shares.put(id, share);
        return "?share=" + id + (share.more ? "&more=1" : "");
    }

    /** Hands one share's file list to the page, once. */
    synchronized String claim(String id) {
        Share share = shares.get(id);
        JSONArray list = new JSONArray();
        if (share == null || share.claimed) return list.toString();
        share.claimed = true;
        try {
            for (int i = 0; i < share.files.size(); i++) {
                list.put(new JSONObject()
                        .put("url", PATH + id + "/" + i)
                        .put("name", share.names.get(i))
                        .put("type", share.types.get(i)));
            }
        } catch (JSONException e) {
            return new JSONArray().toString();
        }
        return list.toString();
    }

    /** The claimed file at /__lifegather-android/share/<id>/<n>, removed from the inbox. */
    synchronized File take(String path) {
        if (path == null || !path.startsWith(PATH)) return null;
        String[] parts = path.substring(PATH.length()).split("/");
        if (parts.length != 2 || !parts[1].matches("[0-9]")) return null;
        Share share = shares.get(parts[0]);
        int index = Integer.parseInt(parts[1]);
        if (share == null || !share.claimed || index >= share.files.size()) return null;
        File file = share.files.get(index);
        share.files.set(index, null);
        boolean done = true;
        for (File other : share.files) if (other != null) done = false;
        if (done) shares.remove(parts[0]);
        return file;
    }

    private static String newId() {
        byte[] bytes = new byte[16];
        new SecureRandom().nextBytes(bytes);
        StringBuilder id = new StringBuilder();
        for (byte b : bytes) id.append(String.format("%02x", b));
        return id.toString();
    }

    private static boolean copy(ContentResolver resolver, Uri uri, File target, long limit) {
        try (InputStream in = resolver.openInputStream(uri); OutputStream out = new FileOutputStream(target)) {
            if (in == null) return false;
            byte[] buffer = new byte[64 * 1024];
            long total = 0;
            int read;
            while (total < limit && (read = in.read(buffer, 0, (int) Math.min(buffer.length, limit - total))) != -1) {
                out.write(buffer, 0, read);
                total += read;
            }
            return true;
        } catch (IOException | SecurityException e) {
            target.delete();
            return false;
        }
    }

    private static String displayName(ContentResolver resolver, Uri uri, int number) {
        try (Cursor cursor = resolver.query(uri, new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) return cursor.getString(0);
        } catch (RuntimeException e) {
            // Fall back to a generic name below.
        }
        String last = uri.getLastPathSegment();
        return last != null && !last.isEmpty() ? last : "shared-file-" + number;
    }

    static void deleteTree(File file) {
        File[] children = file.listFiles();
        if (children != null) for (File child : children) deleteTree(child);
        file.delete();
    }
}
