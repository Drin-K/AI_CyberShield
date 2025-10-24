// content.js - very simple: when user clicks an email open, attempt to extract subject/body and call backend
console.log("content script loaded");

function extractEmail() {
  // VERY naive: adjust selectors to actual Gmail DOM
  const subjectEl = document.querySelector('h2[role="heading"]') || {};
  const bodyEl = document.querySelector('.ii') || {};
  const subject = subjectEl.innerText || "";
  const body = bodyEl.innerText || "";
  return {subject, body};
}

async function scanNow() {
  const data = extractEmail();
  if (!data.subject && !data.body) return;
  try {
    const resp = await fetch("http://localhost:5000/api/scan_text", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(data)
    });
    const j = await resp.json();
    console.log("Scan result:", j);
    if (j.label === "phishing") {
      // very simple visual alert
      alert("⚠️ Phishing detected: " + (j.reasons || []).join(", "));
    } else {
      console.log("Likely benign");
    }
  } catch (e) {
    console.error("scan error", e);
  }
}

// Option: scan when user opens message area (very naive)
document.addEventListener("click", () => {
  setTimeout(scanNow, 800); // wait a bit for Gmail to render
});
