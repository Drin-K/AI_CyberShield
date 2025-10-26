console.log("Background service worker loaded");

let dismissedUntil = 0;
let permanentlyHandledDomains = new Set(); // ruaj domenet që janë raportuar te SOC

// --- funksioni kryesor për marrjen e alarmeve DNS ---
async function fetchDnsAlerts() {
  try {
    const resp = await fetch("http://127.0.0.1:5000/api/phishing_alerts", {
      method: "GET",
      credentials: "omit"
    });

    if (!resp.ok) {
      console.error("DNS alerts endpoint returned non-OK:", resp.status);
      return;
    }

    const json = await resp.json();
    const alerts = json.alerts || [];
    const now = Date.now();

    // nëse është brenda periudhës së dismiss → mos shfaq
    if (now < dismissedUntil) return;

    // filtro alertat që NUK janë raportuar më parë
    const unhandled = alerts.filter(a => !permanentlyHandledDomains.has(a.domain));

    if (unhandled.length > 0) {
      const highAlerts = unhandled.filter(a => a.score >= 0.6);
      if (highAlerts.length > 0) {
        console.log("⚠️ DNS tunneling detected:", highAlerts);

        chrome.notifications.create({
          type: "basic",
          iconUrl: "icon128.png",
          title: "DNS Tunneling Detected",
          message: `Detected ${highAlerts.length} suspicious DNS event(s).`,
          buttons: [
            { title: "📨 Send to SOC Team" },
            { title: "Dismiss" }
          ],
          requireInteraction: true
        }, (notificationId) => {
          chrome.storage.local.set({
            lastDnsAlerts: highAlerts,
            lastNotificationId: notificationId
          });
        });
      }
    }
  } catch (err) {
    console.error("Error fetching DNS alerts:", err);
  }
}

// --- event për klikim të butonave të njoftimit ---
chrome.notifications.onButtonClicked.addListener(async (notifId, btnIdx) => {
  const stored = await chrome.storage.local.get(["lastDnsAlerts"]);
  const alerts = stored.lastDnsAlerts || [];
  const firstDomain = alerts[0]?.domain || "unknown-domain";

  if (btnIdx === 0) {
    // 👉 Send to SOC Team → dërgo raport, mbyll njoftimin, MOS e shfaq më
    try {
      const resp = await fetch("http://127.0.0.1:5000/api/report_to_soc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: firstDomain,
          reason: "Automatic report from DNS tunneling alert"
        })
      });

      const json = await resp.json();
      chrome.notifications.clear(notifId);

      if (json.status === "ok") {
        // Ruaj që ky domain është trajtuar → mos e shfaq më
        permanentlyHandledDomains.add(firstDomain);
        console.log(`✅ Domain ${firstDomain} reported to SOC, nuk shfaqet më.`);

        chrome.notifications.create({
          type: "basic",
          iconUrl: "icon128.png",
          title: "✅ Report Sent",
          message: `Domain ${firstDomain} reported to SOC Team.`
        });
      } else {
        chrome.notifications.create({
          type: "basic",
          iconUrl: "icon128.png",
          title: "⚠️ Report Failed",
          message: json.error || "Unknown error."
        });
      }
    } catch (err) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icon128.png",
        title: "❌ Error",
        message: err.message
      });
    }

  } else if (btnIdx === 1) {
    // 👉 Dismiss → mbyll përkohësisht dhe lejo pas 25 sekondash
    chrome.notifications.clear(notifId);
    dismissedUntil = Date.now() + 25000; // 25 sekonda
    console.log("🔕 Alerts dismissed për 25 sekonda — do të rikthehen më pas.");
  }
});

// --- funksioni që ekzekutohet periodikisht çdo 15 sekonda ---
setInterval(fetchDnsAlerts, 15000);

// --- logjika ekzistuese për skanimin e phishing ---
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
        json.label = json.final_label;
        json.score = json.final_score;
        sendResponse(json);
      } catch (err) {
        console.error("Background fetch error:", err);
        sendResponse({ error: err.message });
      }
    })();
    return true;
  }
});
