console.log("Background service worker loaded");

// Fetch DNS tunneling alerts every 15 seconds
async function fetchDnsAlerts() {
  try {
    const resp = await fetch("http://127.0.0.1:5000/api/phishing_alerts", {
      method: "GET",
      credentials: "omit"
    });

    // if non-2xx -> log status and body text for debugging
    if (!resp.ok) {
      const txt = await resp.text();
      console.error("DNS alerts endpoint returned non-OK:", resp.status, resp.statusText, txt);
      return;
    }

    // check content-type before parsing
    const contentType = resp.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const txt = await resp.text();
      console.error("DNS alerts: expected JSON but got:", contentType, txt);
      return;
    }

    const json = await resp.json();
    const alerts = json.alerts || [];

    if (alerts.length > 0) {
      const highAlerts = alerts.filter(a => a.score >= 0.6);
      if (highAlerts.length > 0) {
        console.log("⚠️ DNS tunneling detected:", highAlerts);

        // notification
        chrome.notifications.create({
          type: "basic",
          iconUrl: "icon128.png",
          title: "DNS Tunneling Detected",
          message: `Detected ${highAlerts.length} suspicious DNS event(s).`
        });

        // send to open Gmail tabs
        chrome.tabs.query({ url: "*://mail.google.com/*" }, (tabs) => {
          for (const tab of tabs) {
            chrome.tabs.sendMessage(tab.id, {
              action: "dns_alert",
              alerts: highAlerts
            });
          }
        });
      }
    }
  } catch (err) {
    console.error("Error fetching DNS alerts:", err);
  }
}


// Run check every 15 seconds
setInterval(fetchDnsAlerts, 15000);

// Handle phishing scan requests (existing logic)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "scan_text") {
    (async () => {
      try {
        const resp = await fetch("http://127.0.0.1:5000/api/scan_text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(message.payload)
        });
        const json = await resp.json();
        sendResponse(json);
      } catch (err) {
        console.error("Background fetch error:", err);
        sendResponse({ error: err.message });
      }
    })();
    return true;
  }
});
