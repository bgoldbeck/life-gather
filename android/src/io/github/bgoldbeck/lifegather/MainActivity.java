package io.github.bgoldbeck.lifegather;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;

/**
 * Shows LifeGather's web UI from the user's own server. On first launch it asks
 * for the server's home-network address; the page itself does everything else.
 */
public final class MainActivity extends Activity {
    private static final String PREFS = "lifegather";
    private static final String SERVER = "server";
    private static final int PICK_FILES = 1;
    private static final int TAKE_PHOTO = 2;
    private static final String GREEN = "#234e3c";

    private SharedPreferences prefs;
    private SharedInbox inbox;
    private WebView web;
    /** What the user typed, e.g. http://192.168.1.20:8787. */
    private volatile String server;
    /** What the web view opens: the loopback relay for plain HTTP, otherwise the server. */
    private volatile String webOrigin;
    private String pendingQuery;
    private ValueCallback<Uri[]> fileCallback;
    private File photoFile;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        inbox = new SharedInbox(this);
        server = prefs.getString(SERVER, null);
        pendingQuery = inbox.receive(this, getIntent());
        if (server == null) showSetup(null);
        else openServer();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        String query = inbox.receive(this, intent);
        if (query == null) return;
        pendingQuery = query;
        if (server != null) openServer();
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.getParent() != null && web.canGoBack()) {
            web.goBack();
            return;
        }
        if (web != null && web.getParent() != null) {
            new AlertDialog.Builder(this)
                    .setTitle("Leave LifeGather?")
                    .setMessage("Connected to " + server)
                    .setPositiveButton("Close app", new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface dialog, int which) {
                            finish();
                        }
                    })
                    .setNeutralButton("Change server address", new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface dialog, int which) {
                            showSetup(null);
                        }
                    })
                    .setNegativeButton("Stay", null)
                    .show();
            return;
        }
        super.onBackPressed();
    }

    // ----- First launch: ask for the server address -----

    private void showSetup(String problem) {
        LinearLayout column = column();
        column.addView(text("Connect to LifeGather", 24, true));
        column.addView(text("Type the address you use to open LifeGather on your home network, "
                + "for example http://192.168.1.20:8787. Your phone must be on the same Wi-Fi.", 16, false));
        final EditText field = new EditText(this);
        field.setHint("http://192.168.1.20:8787");
        field.setSingleLine(true);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        field.setImeOptions(EditorInfo.IME_ACTION_GO);
        field.setContentDescription("Server address");
        String saved = prefs.getString(SERVER, null);
        field.setText(saved != null ? saved : "http://");
        field.setSelection(field.getText().length());
        column.addView(field, wide());
        final TextView status = text(problem == null ? "" : problem, 15, false);
        status.setTextColor(Color.parseColor("#b3261e"));
        final Button connect = button("Connect");
        column.addView(connect, wide());
        column.addView(status);
        View.OnClickListener go = new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                final String origin = ServerAddress.normalize(field.getText().toString());
                if (origin == null) {
                    status.setText("That doesn't look like an address. Try something like http://192.168.1.20:8787");
                    return;
                }
                connect.setEnabled(false);
                status.setTextColor(Color.DKGRAY);
                status.setText("Checking " + origin + " …");
                new Thread(new Runnable() {
                    @Override
                    public void run() {
                        final String problem = check(origin);
                        runOnUiThread(new Runnable() {
                            @Override
                            public void run() {
                                connect.setEnabled(true);
                                if (problem != null) {
                                    status.setTextColor(Color.parseColor("#b3261e"));
                                    status.setText(problem);
                                    return;
                                }
                                if (!origin.equals(server)) forgetPreviousServer();
                                prefs.edit().putString(SERVER, origin).apply();
                                server = origin;
                                openServer();
                            }
                        });
                    }
                }).start();
            }
        };
        connect.setOnClickListener(go);
        field.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView v, int actionId, KeyEvent event) {
                connect.performClick();
                return true;
            }
        });
        setContentView(scroll(column));
        field.requestFocus();
    }

    /** A different server must not see the old one's session cookie or cached pages. */
    private void forgetPreviousServer() {
        CookieManager.getInstance().removeAllCookies(null);
        CookieManager.getInstance().flush();
        if (web != null) {
            web.clearCache(true);
            web.clearHistory();
            web.loadUrl("about:blank");
        }
    }

    /** Returns null when LifeGather answers at origin, otherwise a message for the user. */
    private static String check(String origin) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(origin + "/health").openConnection();
            connection.setConnectTimeout(6000);
            connection.setReadTimeout(6000);
            connection.setInstanceFollowRedirects(false);
            int code = connection.getResponseCode();
            if (code != 200) return "Something answered at that address, but it isn't LifeGather (code " + code + ").";
            byte[] buffer = new byte[256];
            int read;
            StringBuilder body = new StringBuilder();
            try (InputStream in = connection.getInputStream()) {
                while (body.length() < 1024 && (read = in.read(buffer)) != -1) body.append(new String(buffer, 0, read, "UTF-8"));
            }
            if (!body.toString().contains("\"ok\"")) return "Something answered at that address, but it isn't LifeGather.";
            return null;
        } catch (IOException e) {
            return "Couldn't reach LifeGather at " + origin + ". Check the address, that your phone is on your home Wi-Fi, "
                    + "and that the computer or NAS running LifeGather is on.";
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    // ----- The web app -----

    private void openServer() {
        if (!startRelay()) return;
        if (web == null) web = createWebView();
        String query = pendingQuery;
        pendingQuery = null;
        if (web.getParent() == null) setContentView(web);
        if (query != null) web.loadUrl(webOrigin + "/" + query);
        else if (web.getUrl() == null || !ServerAddress.sameOrigin(webOrigin, web.getUrl())) web.loadUrl(webOrigin + "/");
    }

    /** Plain-HTTP home servers are opened through LoopbackRelay; HTTPS ones directly. */
    private boolean startRelay() {
        Uri address = Uri.parse(server);
        if (!"http".equals(address.getScheme())) {
            webOrigin = server;
            return true;
        }
        try {
            LoopbackRelay.start(address.getHost(), address.getPort() == -1 ? 80 : address.getPort());
            webOrigin = LoopbackRelay.ORIGIN;
            return true;
        } catch (IOException e) {
            showSetup("The app couldn't start its connection to LifeGather. Close other apps using port "
                    + LoopbackRelay.PORT + " and try again.");
            return false;
        }
    }

    private WebView createWebView() {
        WebView view = new WebView(this);
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setUserAgentString(settings.getUserAgentString() + " LifeGatherAndroid/" + BuildInfo.VERSION);
        CookieManager.getInstance().setAcceptCookie(true);
        view.addJavascriptInterface(new Bridge(), "LifeGatherAndroid");
        view.setWebViewClient(new Client());
        view.setWebChromeClient(new Chrome());
        view.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String agent, String disposition, String type, long length) {
                Toast.makeText(MainActivity.this, "Downloads aren't available in the phone app yet. Use LifeGather on your computer.",
                        Toast.LENGTH_LONG).show();
            }
        });
        return view;
    }

    /** Lets the page collect files shared from another app; see SharedInbox. */
    private final class Bridge {
        @JavascriptInterface
        public String sharedFiles(String id) {
            return inbox.claim(id);
        }
    }

    private final class Client extends WebViewClient {
        // Android 7+ calls this one; it is newer than the API 23 jar we compile
        // against, so it can't carry @Override but still overrides at run time.
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return leaveApp(request.getUrl());
        }

        @Override
        @SuppressWarnings("deprecation")
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return leaveApp(Uri.parse(url));
        }

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();
            if (!ServerAddress.sameOrigin(webOrigin, url.toString()) || !"GET".equals(request.getMethod())) return null;
            if (url.getPath() == null || !url.getPath().startsWith(SharedInbox.PATH)) return null;
            final File file = inbox.take(url.getPath());
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-store");
            if (file == null) return notFound(headers);
            try {
                InputStream stream = new FileInputStream(file) {
                    @Override
                    public void close() throws IOException {
                        super.close();
                        file.delete();
                    }
                };
                return new WebResourceResponse("application/octet-stream", null, 200, "OK", headers, stream);
            } catch (FileNotFoundException e) {
                return notFound(headers);
            }
        }

        private WebResourceResponse notFound(Map<String, String> headers) {
            return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", headers,
                    new ByteArrayInputStream(new byte[0]));
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) showOffline();
        }
    }

    /** Pages on the server stay in the app; any other link opens in the phone's browser. */
    private boolean leaveApp(Uri url) {
        if (ServerAddress.sameOrigin(webOrigin, url.toString())) return false;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, url).addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "No app can open that link.", Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    private void showOffline() {
        LinearLayout column = column();
        column.addView(text("Can't reach LifeGather", 24, true));
        column.addView(text("The app couldn't open " + server + ". Make sure your phone is on your home Wi-Fi "
                + "and the computer or NAS running LifeGather is switched on.", 16, false));
        Button retry = button("Try again");
        retry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (!startRelay()) return;
                setContentView(web);
                web.loadUrl(webOrigin + "/");
            }
        });
        column.addView(retry, wide());
        Button change = button("Change server address");
        change.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showSetup(null);
            }
        });
        column.addView(change, wide());
        if (web.getParent() != null) ((ViewGroup) web.getParent()).removeView(web);
        setContentView(scroll(column));
    }

    // ----- Choosing files and taking photos -----

    private final class Chrome extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            if (params.isCaptureEnabled() && acceptsImages(params) && takePhoto()) return true;
            Intent pick = params.createIntent();
            if (params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE) pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            try {
                startActivityForResult(pick, PICK_FILES);
            } catch (ActivityNotFoundException e) {
                fileCallback = null;
                return false;
            }
            return true;
        }
    }

    private static boolean acceptsImages(WebChromeClient.FileChooserParams params) {
        String[] types = params.getAcceptTypes();
        if (types == null || types.length == 0) return true;
        for (String type : types) if (type.isEmpty() || type.startsWith("image/")) return true;
        return false;
    }

    private boolean takePhoto() {
        File dir = PhotoFileProvider.directory(getCacheDir());
        File[] old = dir.listFiles();
        if (old != null) for (File file : old) file.delete();
        photoFile = new File(dir, "photo-" + System.currentTimeMillis() + ".jpg");
        Uri output = PhotoFileProvider.uriFor(photoFile);
        Intent camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        camera.putExtra(MediaStore.EXTRA_OUTPUT, output);
        camera.setClipData(ClipData.newRawUri("photo", output));
        camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivityForResult(camera, TAKE_PHOTO);
            return true;
        } catch (ActivityNotFoundException e) {
            photoFile = null;
            return false;
        }
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (fileCallback == null) return;
        Uri[] chosen = null;
        if (request == TAKE_PHOTO && result == RESULT_OK && photoFile != null && photoFile.length() > 0) {
            chosen = new Uri[] {PhotoFileProvider.uriFor(photoFile)};
        } else if (request == PICK_FILES && result == RESULT_OK) {
            chosen = WebChromeClient.FileChooserParams.parseResult(result, data);
            if (data != null && data.getClipData() != null) {
                ClipData clip = data.getClipData();
                chosen = new Uri[clip.getItemCount()];
                for (int i = 0; i < clip.getItemCount(); i++) chosen[i] = clip.getItemAt(i).getUri();
            }
        }
        fileCallback.onReceiveValue(chosen);
        fileCallback = null;
    }

    // ----- Small layout helpers for the two native screens -----

    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics());
    }

    private LinearLayout column() {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(24), dp(48), dp(24), dp(24));
        column.setGravity(Gravity.CENTER_HORIZONTAL);
        return column;
    }

    private ScrollView scroll(View content) {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(content);
        return scroll;
    }

    private TextView text(String value, int size, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        text.setTextColor(bold ? Color.parseColor(GREEN) : Color.DKGRAY);
        if (bold) text.setTypeface(Typeface.DEFAULT_BOLD);
        text.setPadding(0, 0, 0, dp(16));
        return text;
    }

    private Button button(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        return button;
    }

    private LinearLayout.LayoutParams wide() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        params.bottomMargin = dp(12);
        return params;
    }
}
