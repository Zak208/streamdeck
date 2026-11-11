package com.zak208.streamdesk;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Vibrator;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.content.res.Configuration;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.AppCompatButton;

import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanOptions;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.HttpURLConnection;
import java.net.NetworkInterface;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * StreamDesk for Android: a window onto the page the PC serves, plus what a browser shortcut cannot do.
 *
 * The app remembers every PC it was paired with (its id, last address and pairing token). When the PC does not
 * answer where it was, because the phone moved to another Wi-Fi or the PC got another address, the app looks for it
 * on the current network and reconnects by itself. If it is not there, this screen offers the QR scanner and a
 * field for the address, so the user never has to dig through a browser.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS_NAME = "StreamDeskPrefs";
    private static final String KEY_SERVERS = "servers";
    private static final String KEY_LAST_ID = "last_server_id";
    private static final int PORT = 48291;
    private static final int RETRY_MS = 6000;

    /** A PC this phone knows. */
    private static final class Server {
        String id;
        String name;
        String url; // origin only, e.g. http://192.168.1.50:48291
        String token; // pairing token ("" when the phone is not paired yet)
    }

    /** What a PC answered at /api/identity. */
    private static final class Identity {
        String id;
        String name;
        String url;
        boolean verified; // it proved it knows the pairing token we hold for this id
    }

    private WebView webView;
    private View connectLayout;
    private EditText ipInput;
    private Button btnConnect;
    private Button btnScan;
    private Button btnSearch;
    private TextView statusText;
    private TextView foundTitle;
    private LinearLayout foundList;
    private ProgressBar progress;
    private View connectCard;
    private SharedPreferences prefs;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newCachedThreadPool();
    private final List<Server> servers = new ArrayList<>();
    private ActivityResultLauncher<ScanOptions> scanLauncher;

    /** Bumped to cancel whatever search or probe is running. Only touched on the UI thread. */
    private int generation = 0;
    private boolean pageFailed = false;

    /** The PC shown in the WebView, read from the bridge thread. */
    private volatile String currentId = "";
    /** True when the PC shown proved it holds our token: only then does the page get the token. */
    private volatile boolean currentVerified = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_main);
        applyImmersiveFullscreen();

        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        loadServers();

        webView = findViewById(R.id.webView);
        connectLayout = findViewById(R.id.connectLayout);
        ipInput = findViewById(R.id.ipInput);
        btnConnect = findViewById(R.id.btnConnect);
        btnScan = findViewById(R.id.btnScan);
        btnSearch = findViewById(R.id.btnSearch);
        statusText = findViewById(R.id.statusText);
        foundTitle = findViewById(R.id.foundTitle);
        foundList = findViewById(R.id.foundList);
        progress = findViewById(R.id.progress);
        connectCard = findViewById(R.id.connectCard);
        centerConnectCard();

        // Must be registered before the activity starts.
        scanLauncher = registerForActivityResult(new ScanContract(), result -> {
            if (result != null && result.getContents() != null) {
                openUrl(result.getContents());
            }
        });

        setupWebView();

        ipInput.setOnEditorActionListener((v, actionId, event) -> {
            btnConnect.performClick(); // "Ir" on the keyboard does what the Ir button does
            return true;
        });
        btnScan.setOnClickListener(v -> startScan());
        btnSearch.setOnClickListener(v -> startSearch(lastServer()));
        btnConnect.setOnClickListener(v -> {
            String input = ipInput.getText().toString().trim();
            if (input.isEmpty()) {
                setStatus("Escribe la dirección IP del PC, por ejemplo 192.168.1.50");
                return;
            }
            openUrl(input);
        });

        Server last = lastServer();
        if (last != null) {
            showConnect("Buscando " + last.name + "...");
            startSearch(last);
        } else {
            showConnect(getString(R.string.connect_hint));
            startSearch(null);
        }
    }

    // ------------------------------------------------------------------ screens

    private void applyImmersiveFullscreen() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            final WindowInsetsController insetsController = getWindow().getInsetsController();
            if (insetsController != null) {
                insetsController.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                insetsController.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_FULLSCREEN
            );
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            applyImmersiveFullscreen();
        }
    }

    /** On wide screens (tablets, landscape) the card keeps a readable width instead of stretching edge to edge. */
    private void centerConnectCard() {
        final float density = getResources().getDisplayMetrics().density;
        int screen = getResources().getDisplayMetrics().widthPixels;
        int maxCard = (int) (440 * density);
        int margin = Math.max((int) (16 * density), (screen - maxCard) / 2);
        android.view.ViewGroup.MarginLayoutParams params = (android.view.ViewGroup.MarginLayoutParams) connectCard.getLayoutParams();
        params.setMargins(margin, params.topMargin, margin, params.bottomMargin);
        connectCard.setLayoutParams(params);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        centerConnectCard();
    }

    private boolean connectVisible() {
        return connectLayout.getVisibility() == View.VISIBLE;
    }

    private void setStatus(String text) {
        statusText.setText(text);
    }

    /** Shows the connection screen. The page behind it is emptied so it stops reconnecting to an old address. */
    private void showConnect(String message) {
        // The screen only has to stay on while the deck is in use, not while searching for the PC.
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setStatus(message);
        if (webView.getVisibility() == View.VISIBLE) {
            webView.setVisibility(View.GONE);
            webView.loadUrl("about:blank");
        }
        connectLayout.setVisibility(View.VISIBLE);
    }

    /** Shows the deck and cancels every search. */
    /** The executor is shut down in onDestroy: a late call from the page's bridge must not crash the app. */
    private void runIo(Runnable work) {
        try {
            io.execute(work);
        } catch (java.util.concurrent.RejectedExecutionException ignored) {
            // the activity is gone
        }
    }

    private void showDeck() {
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        generation++;
        ui.removeCallbacksAndMessages(null);
        progress.setVisibility(View.INVISIBLE);
        connectLayout.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
    }

    private long lastBackAt = 0;

    @Override
    public void onBackPressed() {
        if (webView.getVisibility() == View.VISIBLE) {
            // A stray Back gesture in the middle of a stream must not drop the panel: the second one within 2 s does.
            long now = System.currentTimeMillis();
            if (now - lastBackAt > 2000) {
                lastBackAt = now;
                Toast.makeText(this, R.string.press_back_again, Toast.LENGTH_SHORT).show();
                return;
            }
            generation++;
            showConnect("Has salido del panel. Toca Buscar mi PC para volver, o escanea otro QR.");
            progress.setVisibility(View.INVISIBLE);
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        generation++;
        ui.removeCallbacksAndMessages(null);
        io.shutdownNow();
        super.onDestroy();
    }

    // ------------------------------------------------------------------ WebView

    @SuppressLint({"SetJavaScriptEnabled", "JavascriptInterface"})
    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(false);
        settings.setLoadsImagesAutomatically(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);

        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        webView.addJavascriptInterface(new AppBridge(), "AndroidApp");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // WebView also calls this after an error, and for the blank page used to stop the old one.
                if (pageFailed || url == null || url.startsWith("about:")) {
                    return;
                }
                showDeck();
            }

            @Override
            public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
                // The page's process died (usually low memory). Returning false would take the whole app down.
                ui.post(() -> {
                    Toast.makeText(MainActivity.this, R.string.panel_closed, Toast.LENGTH_LONG).show();
                    recreate();
                });
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    pageFailed = true;
                    Server s = serverById(currentId);
                    showConnect("No se pudo abrir " + (s != null ? s.name : "el PC") + ". Comprueba que StreamDesk está abierto en el PC y que estáis en la misma Wi-Fi.");
                    progress.setVisibility(View.INVISIBLE);
                    scheduleRetry();
                }
            }

            // The page is the PC's and talks to the bridge: nothing else may load in this WebView.
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                Server s = serverById(currentId);
                String current = s != null ? s.url : "";
                String origin = origin(target);
                if (origin != null && origin.equals(current)) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, target));
                } catch (Exception ignored) {
                    // no app can open it
                }
                return true;
            }
        });
    }

    /** Loads the PC's page. pin is only set when the address came from Studio's QR. */
    private void loadServer(Server s, boolean verified, String pin) {
        generation++;
        ui.removeCallbacksAndMessages(null);
        currentId = s.id;
        currentVerified = verified;
        pageFailed = false;
        prefs.edit().putString(KEY_LAST_ID, s.id).apply();
        setStatus("Conectando con " + s.name + "...");
        progress.setVisibility(View.VISIBLE);
        String target = s.url + "/" + (pin != null && !pin.isEmpty() ? "?pin=" + Uri.encode(pin) : "");
        webView.loadUrl(target);
    }

    // ------------------------------------------------------------------ opening an address (QR or typed)

    /** Opens what the user scanned or typed, but only after the address proves it is a StreamDesk PC. */
    private void openUrl(String raw) {
        final String base = normalizeBase(raw);
        if (base == null) {
            setStatus("Esa dirección no es válida.");
            return;
        }
        String pin = null;
        try {
            Uri parsed = Uri.parse(raw.trim().contains("://") ? raw.trim() : "http://" + raw.trim());
            pin = parsed.getQueryParameter("pin");
        } catch (Exception ignored) {
            // no PIN in it
        }
        if (pin != null && !pin.matches("\\d{4,8}")) {
            pin = null;
        }
        final String pinToUse = pin;
        final int my = ++generation;
        ui.removeCallbacksAndMessages(null); // a pending automatic search would bump `generation` and drop this answer
        connectLayout.setVisibility(View.VISIBLE);
        progress.setVisibility(View.VISIBLE);
        setStatus("Comprobando " + base + "...");
        runIo(() -> {
            Identity found = probeKnown(base, 2500, 3000);
            ui.post(() -> {
                if (my != generation) {
                    return;
                }
                if (found == null) {
                    progress.setVisibility(View.INVISIBLE);
                    setStatus("No encuentro StreamDesk en " + base + ". Si es un QR, comprueba que es el de Studio; si es una IP, que StreamDesk está abierto y que estáis en la misma Wi-Fi. Si todo parece bien, en el PC abre Studio > Ajustes > Conexión del móvil > Comprobar la conexión: la causa más habitual es el cortafuegos de Windows.");
                    return;
                }
                Server s = remember(found);
                loadServer(s, found.verified, pinToUse);
            });
        });
    }

    private static String normalizeBase(String raw) {
        if (raw == null) {
            return null;
        }
        String text = raw.trim();
        if (text.isEmpty()) {
            return null;
        }
        if (!text.toLowerCase(Locale.ROOT).startsWith("http://") && !text.toLowerCase(Locale.ROOT).startsWith("https://")) {
            text = "http://" + text;
        }
        try {
            Uri uri = Uri.parse(text);
            String host = uri.getHost();
            if (host == null || host.isEmpty()) {
                return null;
            }
            int port = uri.getPort() > 0 ? uri.getPort() : PORT;
            String scheme = uri.getScheme() == null ? "http" : uri.getScheme().toLowerCase(Locale.ROOT);
            return scheme + "://" + host + ":" + port;
        } catch (Exception e) {
            return null;
        }
    }

    private static String origin(Uri uri) {
        if (uri == null || uri.getHost() == null || uri.getScheme() == null) {
            return null;
        }
        int port = uri.getPort() > 0 ? uri.getPort() : (uri.getScheme().equalsIgnoreCase("https") ? 443 : 80);
        return uri.getScheme().toLowerCase(Locale.ROOT) + "://" + uri.getHost() + ":" + port;
    }

    // ------------------------------------------------------------------ searching for the PC

    private void scheduleRetry() {
        ui.postDelayed(() -> {
            Server last = lastServer();
            if (connectVisible() && last != null) {
                startSearch(last);
            }
        }, RETRY_MS);
    }

    /**
     * Looks for the PC: first where it was, then across the local network. A known PC found is opened at once;
     * PCs not known yet are listed so the user can choose.
     */
    private void startSearch(final Server wanted) {
        final int my = ++generation;
        ui.removeCallbacksAndMessages(null);
        foundList.removeAllViews();
        foundTitle.setVisibility(View.GONE);
        progress.setVisibility(View.VISIBLE);
        setStatus(wanted != null ? "Buscando " + wanted.name + " en esta red..." : "Buscando PCs con StreamDesk en esta Wi-Fi...");

        runIo(() -> {
            // 1. Where it was.
            if (wanted != null) {
                Identity same = probeKnown(wanted.url, 1500, 1500);
                if (same != null && same.id.equals(wanted.id)) {
                    ui.post(() -> {
                        if (my == generation) {
                            loadServer(remember(same), same.verified, null);
                        }
                    });
                    return;
                }
            }
            // 2. Everything on the local network(s).
            final List<String> prefixes = localPrefixes();
            if (prefixes.isEmpty()) {
                ui.post(() -> {
                    if (my == generation) {
                        searchDone(wanted, false, "Este móvil no está conectado a una Wi-Fi. Conéctate a la misma red que tu PC.");
                    }
                });
                return;
            }
            final boolean[] opened = {false};
            final int[] hits = {0};
            ExecutorService pool = Executors.newFixedThreadPool(48);
            List<java.util.concurrent.Future<?>> tasks = new ArrayList<>();
            for (final String prefix : prefixes) {
                for (int host = 1; host <= 254; host++) {
                    final String base = "http://" + prefix + host + ":" + PORT;
                    tasks.add(pool.submit(() -> {
                        if (my != generation) {
                            return;
                        }
                        Identity found = probeKnown(base, 350, 900);
                        if (found == null) {
                            return;
                        }
                        ui.post(() -> {
                            if (my != generation) {
                                return;
                            }
                            hits[0]++;
                            Server known = serverById(found.id);
                            if (known != null) {
                                if (!opened[0]) {
                                    opened[0] = true;
                                    loadServer(remember(found), found.verified, null);
                                }
                            } else {
                                addFound(found);
                            }
                        });
                    }));
                }
            }
            for (java.util.concurrent.Future<?> task : tasks) {
                try {
                    task.get();
                } catch (Exception ignored) {
                    // cancelled or failed probe: nothing to report
                }
            }
            pool.shutdownNow();
            ui.post(() -> {
                if (my == generation) {
                    searchDone(wanted, hits[0] > 0, null);
                }
            });
        });
    }

    private void searchDone(Server wanted, boolean foundAny, String message) {
        progress.setVisibility(View.INVISIBLE);
        if (message != null) {
            setStatus(message);
        } else if (wanted != null) {
            setStatus(foundAny
                    ? "No encuentro " + wanted.name + " en esta red, pero hay otros StreamDesk abajo."
                    : "No encuentro " + wanted.name + " en esta red. ¿Está el PC encendido y StreamDesk en marcha (icono junto al reloj)? Vuelvo a mirar cada pocos segundos; también puedes escanear el QR o escribir su IP. Si todo parece bien, en el PC abre Studio > Ajustes > Conexión del móvil > Comprobar la conexión: la causa más habitual es el cortafuegos de Windows.");
        } else {
            setStatus(foundAny
                    ? "Elige tu PC de la lista, o escanea el QR de Studio."
                    : "No he encontrado ningún StreamDesk en esta Wi-Fi. Escanea el QR de Studio o escribe la IP del PC. Si todo parece bien, en el PC abre Studio > Ajustes > Conexión del móvil > Comprobar la conexión: la causa más habitual es el cortafuegos de Windows.");
        }
        if (wanted != null) {
            scheduleRetry();
        }
    }

    private void addFound(final Identity found) {
        foundTitle.setVisibility(View.VISIBLE);
        AppCompatButton button = new AppCompatButton(this);
        button.setAllCaps(false);
        button.setBackgroundResource(R.drawable.bg_button_secondary);
        button.setTextColor(getResources().getColor(R.color.text_primary, getTheme()));
        button.setText(found.name + "   " + found.url.replace("http://", ""));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, (int) (48 * getResources().getDisplayMetrics().density));
        lp.topMargin = (int) (6 * getResources().getDisplayMetrics().density);
        button.setLayoutParams(lp);
        button.setOnClickListener(v -> openUrl(found.url));
        foundList.addView(button);
    }

    /** IPv4 prefixes ("192.168.1.") of the Wi-Fi, Ethernet, hotspot and USB-tether networks this phone is on. */
    private static List<String> localPrefixes() {
        List<String> result = new ArrayList<>();
        try {
            for (NetworkInterface nif : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                String name = nif.getName() == null ? "" : nif.getName().toLowerCase(Locale.ROOT);
                boolean lan = name.startsWith("wlan") || name.startsWith("eth") || name.startsWith("ap")
                        || name.startsWith("swlan") || name.startsWith("rndis") || name.startsWith("usb");
                if (!lan || !nif.isUp() || nif.isLoopback()) {
                    continue;
                }
                for (InetAddress address : Collections.list(nif.getInetAddresses())) {
                    if (address instanceof Inet4Address && address.isSiteLocalAddress()) {
                        byte[] b = address.getAddress();
                        String prefix = (b[0] & 255) + "." + (b[1] & 255) + "." + (b[2] & 255) + ".";
                        if (!result.contains(prefix)) {
                            result.add(prefix);
                        }
                    }
                }
            }
        } catch (Exception ignored) {
            // no interfaces readable: the caller reports "no Wi-Fi"
        }
        return result;
    }

    // ------------------------------------------------------------------ talking to the PC

    /** Asks a PC who it is. If we already hold a token for the id it answers with, asks again for proof of it. */
    private Identity probeKnown(String base, int connectMs, int readMs) {
        Identity first = fetchIdentity(base, connectMs, readMs, null);
        if (first == null) {
            return null;
        }
        Server known = serverById(first.id);
        if (known == null || known.token == null || known.token.isEmpty()) {
            return first;
        }
        Identity proven = fetchIdentity(base, connectMs, Math.max(readMs, 1500), known.token);
        return proven != null ? proven : first;
    }

    private Identity fetchIdentity(String base, int connectMs, int readMs, String token) {
        HttpURLConnection connection = null;
        try {
            String nonce = null;
            String query = "";
            if (token != null) {
                byte[] random = new byte[16];
                new SecureRandom().nextBytes(random);
                nonce = hex(random);
                query = "?device=" + hex(sha256(token)).substring(0, 12) + "&nonce=" + nonce;
            }
            connection = (HttpURLConnection) new URL(base + "/api/identity" + query).openConnection();
            connection.setConnectTimeout(connectMs);
            connection.setReadTimeout(readMs);
            connection.setUseCaches(false);
            connection.setInstanceFollowRedirects(false);
            if (connection.getResponseCode() != 200) {
                return null;
            }
            InputStream in = connection.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[512];
            int n;
            int total = 0;
            while ((n = in.read(buffer)) > 0 && total < 4096) {
                out.write(buffer, 0, n);
                total += n;
            }
            JSONObject json = new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
            if (!"streamdesk".equals(json.optString("app")) || json.optString("id").isEmpty()) {
                return null;
            }
            Identity identity = new Identity();
            identity.id = json.getString("id");
            identity.name = json.optString("name", "PC");
            identity.url = base;
            if (token != null && nonce != null) {
                String proof = json.optString("proof", "");
                identity.verified = !proof.isEmpty() && MessageDigest.isEqual(
                        proof.getBytes(StandardCharsets.UTF_8), hmac(token, nonce).getBytes(StandardCharsets.UTF_8));
            }
            return identity;
        } catch (Exception e) {
            return null;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static byte[] sha256(String text) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
    }

    private static String hmac(String key, String message) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return hex(mac.doFinal(message.getBytes(StandardCharsets.UTF_8)));
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte b : bytes) {
            out.append(String.format(Locale.ROOT, "%02x", b & 255));
        }
        return out.toString();
    }

    // ------------------------------------------------------------------ known PCs

    private void loadServers() {
        synchronized (servers) {
            servers.clear();
            try {
                JSONArray array = new JSONArray(prefs.getString(KEY_SERVERS, "[]"));
                for (int i = 0; i < array.length(); i++) {
                    JSONObject o = array.getJSONObject(i);
                    Server s = new Server();
                    s.id = o.getString("id");
                    s.name = o.optString("name", "PC");
                    s.url = o.getString("url");
                    s.token = o.optString("token", "");
                    servers.add(s);
                }
            } catch (Exception ignored) {
                servers.clear();
            }
        }
    }

    private void saveServers() {
        synchronized (servers) {
            JSONArray array = new JSONArray();
            try {
                for (Server s : servers) {
                    JSONObject o = new JSONObject();
                    o.put("id", s.id);
                    o.put("name", s.name);
                    o.put("url", s.url);
                    o.put("token", s.token == null ? "" : s.token);
                    array.put(o);
                }
            } catch (Exception ignored) {
                return;
            }
            prefs.edit().putString(KEY_SERVERS, array.toString()).apply();
        }
    }

    private Server serverById(String id) {
        synchronized (servers) {
            for (Server s : servers) {
                if (s.id.equals(id)) {
                    return s;
                }
            }
        }
        return null;
    }

    private Server lastServer() {
        return serverById(prefs.getString(KEY_LAST_ID, ""));
    }

    /** Stores (or updates) the PC with the address it answered from, keeping its token. */
    private Server remember(Identity found) {
        synchronized (servers) {
            Server s = serverById(found.id);
            if (s == null) {
                s = new Server();
                s.id = found.id;
                s.token = "";
                servers.add(s);
            }
            s.name = found.name;
            s.url = found.url;
            saveServers();
            return s;
        }
    }

    // ------------------------------------------------------------------ QR

    private void startScan() {
        ui.removeCallbacksAndMessages(null); // no automatic search behind the camera
        ScanOptions options = new ScanOptions();
        options.setDesiredBarcodeFormats(ScanOptions.QR_CODE);
        options.setPrompt("Apunta al QR que muestra StreamDesk Studio en tu PC");
        options.setBeepEnabled(false);
        options.setOrientationLocked(false);
        scanLauncher.launch(options);
    }

    // ------------------------------------------------------------------ bridge for the page (window.AndroidApp)

    /** Called from the page's JavaScript, on a WebView thread: anything touching views goes through the UI thread. */
    public class AppBridge {
        @JavascriptInterface
        public void vibrate(long milliseconds) {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null && v.hasVibrator()) {
                v.vibrate(milliseconds);
            }
        }

        /** The pairing token of the PC on screen, only if that PC proved it knows it (so a lookalike gets nothing). */
        @JavascriptInterface
        public String getToken() {
            if (!currentVerified) {
                return "";
            }
            Server s = serverById(currentId);
            return s == null || s.token == null ? "" : s.token;
        }

        @JavascriptInterface
        public void saveToken(String token) {
            Server s = serverById(currentId);
            if (s == null || token == null || token.length() > 128) {
                return;
            }
            synchronized (servers) {
                s.token = token;
                saveServers();
            }
            currentVerified = true;
        }

        @JavascriptInterface
        public void clearToken() {
            Server s = serverById(currentId);
            if (s == null) {
                return;
            }
            synchronized (servers) {
                s.token = "";
                saveServers();
            }
            currentVerified = false;
        }

        /** This app's version (for example "2.19.0"): the page compares it with the PC's to offer a newer app. */
        @JavascriptInterface
        public String getVersion() {
            try {
                String version = getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
                return version == null ? "" : version;
            } catch (Exception e) {
                return "";
            }
        }

        @JavascriptInterface
        public void scanQr() {
            runOnUiThread(MainActivity.this::startScan);
        }

        @JavascriptInterface
        public void openUrl(String url) {
            runOnUiThread(() -> MainActivity.this.openUrl(url));
        }

        @JavascriptInterface
        public void showConnect() {
            runOnUiThread(() -> {
                generation++;
                MainActivity.this.showConnect("Escanea el QR de Studio, busca tu PC o escribe su dirección.");
                progress.setVisibility(View.INVISIBLE);
            });
        }

        /** The page could not reach its PC for a while: look for it on this network. */
        @JavascriptInterface
        public void connectionLost() {
            runOnUiThread(() -> {
                final Server s = serverById(currentId);
                final int my = ++generation;
                runIo(() -> {
                    // A short outage is the page's own business: if the PC answers where it was, leave it be.
                    Identity same = s == null ? null : fetchIdentity(s.url, 1500, 1500, null);
                    if (same != null && same.id.equals(s.id)) {
                        return;
                    }
                    ui.post(() -> {
                        if (my != generation) {
                            return;
                        }
                        MainActivity.this.showConnect(s != null ? "Perdí la conexión con " + s.name + "." : "Perdí la conexión con el PC.");
                        startSearch(s);
                    });
                });
            });
        }
    }
}
