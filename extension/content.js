console.log("PhishDetect content script loaded");

function extractEmail() {
  const subjectEl = document.querySelector('h2[role="heading"]') || {};
  const bodyEl = document.querySelector('.ii') || {};
  const subject = subjectEl.innerText || "";
  const body = bodyEl.innerText || "";
  return {subject, body};
}
function createBanner(result) {
  const oldBanner = document.getElementById("phishdetect-banner");
  if (oldBanner) oldBanner.remove();

  const banner = document.createElement("div");
  banner.id = "phishdetect-banner";

    Object.assign(banner.style, {
    position: "relative",
    padding: "16px 20px",
    borderRadius: "12px",
    margin: "12px 0",
    fontFamily: "Roboto, Arial, sans-serif",
    fontSize: "15px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    zIndex: "9999",
    boxShadow: "0 3px 10px rgba(0,0,0,0.15)",
    animation: "fadeIn 0.4s ease",
    borderLeft: "5px solid"
  });

  const left = document.createElement("div");
  const right = document.createElement("div");
  const msg = document.createElement("div");

  const score = result.final_score || result.score || 0;
  let color = "#e7f9ee";
  let borderColor = "#1da660";
  let icon = "✅";
  let text = `<b style="color:#0d7a46">Safe email</b> — Likely legitimate.`;

  if (score >= 0.5 && score < 0.8) {
    color = "#fff8e1";
    borderColor = "#ffb300";
    icon = "⚠️";
    text = `<b style="color:#b38f00">Suspicious email</b> — Be cautious.`;
  } else if (score >= 0.8) {
    color = "#fdecea";
    borderColor = "#e53935";
    icon = "🚨";
    text = `<b style="color:#b71c1c">Phishing attempt detected!</b>`;
  }

  banner.style.background = color;
  banner.style.borderLeftColor = borderColor;

  msg.innerHTML = `${icon} ${text}<br>
    <small><b>Score:</b> ${score.toFixed(2)} — ${result.reasons?.join(", ") || ""}</small>`;


  const closeBtn = document.createElement("button");
  closeBtn.textContent = "×";
  Object.assign(closeBtn.style, {
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontSize: "20px",
    marginLeft: "12px",
    color: "#333",
    transition: "transform 0.2s ease"
  });

  closeBtn.onmouseover = () => (closeBtn.style.transform = "scale(1.3)");
  closeBtn.onmouseout = () => (closeBtn.style.transform = "scale(1)");
  closeBtn.onclick = () => banner.remove();

  left.appendChild(msg);
  right.appendChild(closeBtn);
  banner.appendChild(left);
  banner.appendChild(right);

  const container = document.querySelector(".aeH") || document.querySelector(".ii") || document.body;
  container.parentNode.insertBefore(banner, container);

  console.log(`[PhishDetect] Banner displayed (${score.toFixed(2)})(score=${score})`);
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

  Object.assign(banner.style, {
    background: "#fdecea",
    border: "1px solid #e57373",
    padding: "12px 16px",
    margin: "10px 0",
    borderRadius: "10px",
    fontFamily: "Roboto, Arial, sans-serif",
    fontSize: "14px",
    zIndex: "9999",
    boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
    animation: "fadeIn 0.4s ease"
  });

  banner.innerHTML = `
    ⚠️ <b style="color:#b71c1c">DNS tunneling detected!</b><br>
    Domain: <b>${domain}</b><br>
    Score: ${score}
  `;

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


