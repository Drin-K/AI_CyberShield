// background.js — runs independently, handles backend fetch
console.log("Background service worker loaded");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.action !== "scan_text") return;

  (async () => {
    try {
      console.log("Background: scanning text", message.payload);
      const resp = await fetch("http://127.0.0.1:5000/api/scan_text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(message.payload)
      });

      const json = await resp.json();
      console.log("Background: got response", json);
      sendResponse(json);
    } catch (err) {
      console.error("Background fetch error:", err);
      sendResponse({ error: err.message || String(err) });
    }
  })();

  return true; // keep message channel open
});

chrome.action.onClicked.addListener((tab) => {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => console.log("PhishDetect action clicked")
  });
});
