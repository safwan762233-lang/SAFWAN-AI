package com.safwan.ai;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
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
    private String serverUrl = "http://192.168.1.100:8000";

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        showHome();
    }

    private void showHome() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 48, 32, 32);
        root.setBackgroundColor(Color.rgb(12, 17, 28));
        root.setGravity(Gravity.CENTER);

        TextView title = new TextView(this);
        title.setText("SAFWAN AI");
        title.setTextSize(32);
        title.setTextColor(Color.WHITE);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        TextView note = new TextView(this);
        note.setText("Android Test App\nConnect to your PC server to try SAFWAN AI.");
        note.setTextColor(Color.LTGRAY);
        note.setTextSize(16);
        note.setGravity(Gravity.CENTER);
        note.setPadding(0, 24, 0, 24);
        root.addView(note);

        Button connect = new Button(this);
        connect.setText("Connect to PC");
        root.addView(connect);
        connect.setOnClickListener(v -> askServerUrl());

        Button settings = new Button(this);
        settings.setText("Set server address");
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
            .setMessage("Enter your PC's local IP address and port 8000.")
            .setView(input)
            .setPositiveButton("Connect", (d, w) -> openServer(input.getText().toString().trim()))
            .setNegativeButton("Cancel", null)
            .show();
    }

    private void openServer(String url) {
        if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://" + url;
        serverUrl = url;
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient());
        web.loadUrl(serverUrl);
        setContentView(web);
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else showHome();
    }
}
