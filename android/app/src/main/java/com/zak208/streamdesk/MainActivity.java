package com.zak208.streamdesk;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.os.Vibrator;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private static final String PREFS_NAME = "StreamDeskPrefs";
    private static final String KEY_SERVER_URL = "server_url";

    private WebView webView;
    private LinearLayout connectLayout;
    private EditText ipInput;
    private Button btnConnect;
    private TextView statusText;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Keep screen on while using StreamDesk
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        setContentView(R.layout.activity_main);

        applyImmersiveFullscreen();

        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);

        webView = findViewById(R.id.webView);
        connectLayout = findViewById(R.id.connectLayout);
        ipInput = findViewById(R.id.ipInput);
        btnConnect = findViewById(R.id.btnConnect);
        statusText = findViewById(R.id.statusText);

        setupWebView();

        String savedUrl = prefs.getString(KEY_SERVER_URL, "");
        if (!savedUrl.isEmpty()) {
            ipInput.setText(savedUrl.replace("http://", "").replace("https://", ""));
            loadStreamDeskUrl(savedUrl);
        }

        btnConnect.setOnClickListener(v -> {
            String input = ipInput.getText().toString().trim();
            if (input.isEmpty()) {
                Toast.makeText(MainActivity.this, "Por favor introduce la IP del PC", Toast.LENGTH_SHORT).show();
                return;
            }
            if (!input.startsWith("http://") && !input.startsWith("https://")) {
                input = "http://" + input;
            }
            if (!input.matches(".+:\\d+.*")) {
                input = input + ":48291";
            }
            loadStreamDeskUrl(input);
        });
    }

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

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);

        // Hardware acceleration
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null);

        // Native Haptic Bridge
        webView.addJavascriptInterface(new WebAppInterface(this), "AndroidApp");

        // Grant camera permission for HTML5 QR scanner inside WebView
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final android.webkit.PermissionRequest request) {
                request.grant(request.getResources());
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                connectLayout.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
                prefs.edit().putString(KEY_SERVER_URL, url).apply();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    showError("No se pudo conectar con el PC. Revisa la IP y que ambos dispositivos estén en la misma Wi-Fi.");
                }
            }
        });
    }

    private void loadStreamDeskUrl(String url) {
        statusText.setText("Conectando a " + url + "...");
        btnConnect.setEnabled(false);
        webView.loadUrl(url);

        // Re-enable button after 5 seconds if connection hangs
        webView.postDelayed(() -> btnConnect.setEnabled(true), 5000);
    }

    private void showError(String message) {
        webView.setVisibility(View.GONE);
        connectLayout.setVisibility(View.VISIBLE);
        statusText.setText(message);
        btnConnect.setEnabled(true);
    }

    @Override
    public void onBackPressed() {
        if (webView.getVisibility() == View.VISIBLE) {
            // Ask or switch to connection screen
            showError("Desconectado de StreamDesk. Pulsa conectar para volver a entrar.");
        } else {
            super.onBackPressed();
        }
    }

    public static class WebAppInterface {
        Context context;

        WebAppInterface(Context c) {
            context = c;
        }

        @JavascriptInterface
        public void vibrate(long milliseconds) {
            Vibrator v = (Vibrator) context.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null && v.hasVibrator()) {
                v.vibrate(milliseconds);
            }
        }
    }
}
