package com.safwan.ai;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.view.ViewGroup;
import android.graphics.Color;
import android.view.Gravity;

public class MainActivity extends Activity {
    private WebView web;
    private String serverUrl;
    private TextView addressLabel;
    private SharedPreferences prefs;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("safwan_ai_settings", MODE_PRIVATE);
        serverUrl = prefs.getString("server_url", "");
        showHome();
    }

    private void showHome() {
        web = null;
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(36, 48, 36, 36);
        root.setBackgroundColor(Color.rgb(12, 17, 28));
        root.setGravity(Gravity.CENTER);

        TextView title = new TextView(this);
        title.setText("SAFWAN AI");
        title.setTextSize(32);
        title.setTextColor(Color.WHITE);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        TextView note = new TextView(this);
        note.setText("Mobile AI Assistant\nConnect to your PC to use your local AI.");
        note.setTextColor(Color.LTGRAY);
        note.setTextSize(16);
        note.setGravity(Gravity.CENTER);
        note.setPadding(0, 24, 0, 24);
        root.addView(note);

        addressLabel = new TextView(this);
        addressLabel.setText(serverUrl.isEmpty() ? "Server address not set" : "Saved server: " + serverUrl);
        addressLabel.setTextColor(Color.rgb(90, 205, 220));
        addressLabel.setTextSize(13);
        addressLabel.setGravity(Gravity.CENTER);
        addressLabel.setPadding(0, 0, 0, 24);
        root.addView(addressLabel);

        Button connect = new Button(this);
        connect.setText("Connect to PC");
        root.addView(connect);
        connect.setOnClickListener(v -> {
            if (serverUrl.isEmpty()) askServerUrl();
            else openServer(serverUrl);
        });

        Button settings = new Button(this);
        settings.setText("Server Settings");
        root.addView(settings);
        settings.setOnClickListener(v -> askServerUrl());

        setContentView(root);
    }

    private void askServerUrl() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint("http://192.168.1.x:8000");
        input.setText(serverUrl);
        new AlertDialog.Builder(this)
            .setTitle("PC Server Address")
            .setMessage("Enter your PC's local IP address and port 8000. Keep your PC and phone on the same Wi-Fi.")
            .setView(input)
            .setPositiveButton("Save & Connect", (d, w) -> {
                String url = input.getText().toString().trim();
                if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://" + url;
                if (url.length() < 9 || !url.contains(".")) {
                    new AlertDialog.Builder(this).setMessage("Please enter a valid server address.").setPositiveButton("OK", null).show();
                    return;
                }
                serverUrl = url.replaceAll("/+$", "");
                prefs.edit().putString("server_url", serverUrl).apply();
                openServer(serverUrl);
            })
            .setNegativeButton("Cancel", null)
            .show();
    }

    private void openServer(String url) {
        serverUrl = url;
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.setWebViewClient(new WebViewClient());
        web.loadUrl(serverUrl);
        setContentView(web);
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else showHome();
    }
}
