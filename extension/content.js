console.log("PhishDetect content script loaded");

function extractEmail() {
  const subjectEl = document.querySelector('h2[role="heading"]') || {};
  const bodyEl = document.querySelector('.ii') || {};
  const subject = subjectEl.innerText || "";
  const body = bodyEl.innerText || "";
  return { subject, body };
}
function createBanner(result) {
  const oldBanner = document.getElementById("phishdetect-banner");
  if (oldBanner) oldBanner.remove();

  const banner = document.createElement("div");
  banner.id = "phishdetect-banner";
  banner.style.position = "relative";
  banner.style.padding = "12px 16px";
  banner.style.borderRadius = "8px";
  banner.style.margin = "8px 0";
  banner.style.fontFamily = "Arial, sans-serif";
  banner.style.fontSize = "14px";
  banner.style.display = "flex";
  banner.style.alignItems = "center";
  banner.style.justifyContent = "space-between";
  banner.style.zIndex = "9999";
  banner.style.boxShadow = "0 2px 8px rgba(0,0,0,0.15)";
  banner.style.transition = "all 0.3s ease";

  const left = document.createElement("div");
  const right = document.createElement("div");
  const msg = document.createElement("div");

  const score = result.final_score || result.score || 0;
  let level = "safe";
  let color = "#e6ffe6";
  let border = "#7fd67f";
  let text = `✅ <b style="color:#007500">Safe email.</b> — Likely legitimate.`

  if (score >= 0.5 && score < 0.8) {
    level = "warning";
    color = "#fff3cd";
    border = "#ffcc00";
    text = `⚠️ <b style="color:#b38f00">Warning:</b> This email seems suspicious.`;
  } else if (score >= 0.8) {
    level = "phishing";
    color = "#ffe6e6";
    border = "#ff8080";
    text = `🚨 <b style="color:#b30000">Phishing detected!</b>`;
  }

  banner.style.background = color;
  banner.style.border = `1px solid ${border}`;

  msg.innerHTML = `${text}<br><b>Score:</b> ${score.toFixed(2)} — ${result.reasons?.join(", ") || ""}`;

  const closeBtn = document.createElement("button");
  closeBtn.textContent = "×";
  closeBtn.style.border = "none";
  closeBtn.style.background = "transparent";
  closeBtn.style.cursor = "pointer";
  closeBtn.style.fontSize = "18px";
  closeBtn.style.marginLeft = "10px";
  closeBtn.onclick = () => banner.remove();
  left.appendChild(msg);
  right.appendChild(closeBtn);
  banner.appendChild(left);
  banner.appendChild(right);

  const container = document.querySelector(".aeH") || document.querySelector(".ii") || document.body;
  container.parentNode.insertBefore(banner, container);

  console.log(`[PhishDetect] Banner shown: ${level.toUpperCase()} (score=${score})`);
}

function scanNow() {
  const data = extractEmail();
  if (!data.subject && !data.body) return;

  console.log("Sending to background for scan:", data);
  chrome.runtime.sendMessage({ action: "scan_text", payload: data }, (response) => {
    if (chrome.runtime.lastError) {
      console.error("runtime error:", chrome.runtime.lastError.message);
      return;
    }
    if (!response) return;
    if (response.error) {
      console.error("backend error:", response.error);
      return;
    }
    createBanner(response);
  });
}

// DNS tunneling alert banner
function showDnsBanner(domain, score) {
  const old = document.getElementById("dns-banner");
  if (old) old.remove();

  const banner = document.createElement("div");
  banner.id = "dns-banner";
  banner.style.background = "#ffe6e6";
  banner.style.border = "1px solid #ff8080";
  banner.style.padding = "10px";
  banner.style.margin = "8px 0";
  banner.style.borderRadius = "6px";
  banner.style.fontFamily = "Arial";
  banner.style.zIndex = "9999";
  banner.innerHTML = `⚠️ <b style="color:#b30000">DNS tunneling detected!</b><br>
  Domain: <b>${domain}</b> — Score: ${score}`;

  const container = document.querySelector(".aeH") || document.body;
  container.parentNode.insertBefore(banner, container);
}

// Listen for DNS alerts from background.js
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "dns_alert") {
    const a = msg.alerts[0];
    showDnsBanner(a.domain || "unknown", a.score.toFixed(2));
  }
});

// Trigger scan every time user clicks inside Gmail
document.addEventListener("click", () => {
  setTimeout(scanNow, 800);
});
