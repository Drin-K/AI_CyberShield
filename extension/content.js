// content.js — PhishDetect (fully integrated: one-alert-per-email, DOM observation, DNS dedupe)
/* global chrome */

console.log("PhishDetect content script loaded (updated observer + DNS behavior)");

const qs = (s, r = document) => r.querySelector(s);
const qsa = (s, r = document) => Array.from((r || document).querySelectorAll(s));
const create = (t, a = {}, children = []) => {
  const e = document.createElement(t);
  Object.entries(a).forEach(([k, v]) => {
    if (k === "style") Object.assign(e.style, v);
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  });
  children.forEach(c => typeof c === "string" ? e.appendChild(document.createTextNode(c)) : e.appendChild(c));
  return e;
};

const injectStyles = (() => {
  let done = false;
  return () => {
    if (done) return;
    done = true;
    const s = document.createElement("style");
    s.id = "phishdetect-styles";
    s.textContent = `
#phishdetect-root,#phishdetect-modal{font-family:Inter,Roboto,"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial;color:#111}
.phd-card{display:flex;gap:12px;align-items:center;justify-content:space-between;width:100%;max-width:980px;box-sizing:border-box;padding:14px 16px;border-radius:14px;margin:12px 8px;box-shadow:0 8px 24px rgba(12,20,30,0.12);transition:transform 320ms cubic-bezier(.22,.9,.32,1),opacity 300ms ease;transform-origin:top center;will-change:transform,opacity;position:relative;overflow:hidden;backdrop-filter:blur(2px)}
@keyframes phd-fade-slide{0%{opacity:0;transform:translateY(-8px) scale(.995)}60%{opacity:1;transform:translateY(4px) scale(1.004)}100%{transform:translateY(0) scale(1)}}
@keyframes phd-emoji-bounce{0%{transform:translateY(0)}30%{transform:translateY(-6px) rotate(-6deg)}60%{transform:translateY(0) rotate(6deg)}100%{transform:translateY(0) rotate(0)}}
.phd-close{border:none;background:transparent;cursor:pointer;font-size:18px;width:36px;height:36px;border-radius:10px;display:inline-grid;place-items:center;transition:transform 220ms cubic-bezier(.2,.9,.3,1),box-shadow 180ms}
.phd-close:hover{transform:scale(1.18) rotate(8deg);box-shadow:0 6px 18px rgba(0,0,0,0.12)}
.phd-close:active{transform:scale(.92) rotate(-6deg)}
.phd-left{display:flex;gap:12px;align-items:center;flex:1 1 auto;min-width:0}
.phd-icon{width:56px;height:56px;min-width:56px;border-radius:12px;display:grid;place-items:center;font-size:26px;box-shadow:0 6px 18px rgba(0,0,0,0.06);flex-shrink:0}
.phd-msg{min-width:0}
.phd-title{font-weight:700;font-size:15px;letter-spacing:-0.2px;margin-bottom:4px}
.phd-sub{font-size:13px;opacity:0.85;color:#222;line-height:1.18}
.phd-meter{width:160px;min-width:120px;max-width:220px;margin-left:12px;display:flex;flex-direction:column;gap:8px;align-items:stretch;flex-shrink:0}
.phd-meter .label{font-size:12px;opacity:0.8}
.phd-bar{height:10px;width:100%;background:rgba(0,0,0,0.06);border-radius:999px;overflow:hidden;box-shadow:inset 0 -1px 0 rgba(255,255,255,0.15)}
.phd-bar-inner{height:100%;width:0%;border-radius:999px;transition:width 900ms cubic-bezier(.2,.9,.3,1);box-shadow:0 6px 18px rgba(0,0,0,0.06) inset}
.phd-actions{display:flex;gap:8px;align-items:center;margin-left:12px}
.phd-btn{font-size:13px;padding:8px 10px;border-radius:10px;cursor:pointer;border:none;background:transparent;transition:transform 160ms}
.phd-learn{text-decoration:underline}
.phd-safe{background:linear-gradient(135deg,#f0fff6,#e7fbf0);border-left:6px solid #1da660}
.phd-susp{background:linear-gradient(135deg,#fffaf0,#fff6e8);border-left:6px solid #ffb300}
.phd-phish{background:linear-gradient(135deg,#fff1f2,#fdecea);border-left:6px solid #e53935}
.phd-icon.safe{background:linear-gradient(135deg,#e6fbf0,#c7f5de);color:#0d7a46}
.phd-icon.susp{background:linear-gradient(135deg,#fff6e1,#ffefcf);color:#b36f00}
.phd-icon.phish{background:linear-gradient(135deg,#ffe8e8,#ffdede);color:#9b1c1c}
#phishdetect-modal-overlay{position:fixed;inset:0;background:rgba(8,10,12,0.42);display:none;align-items:center;justify-content:center;z-index:2147483646;padding:20px}
#phishdetect-modal{width:100%;max-width:780px;background:white;border-radius:12px;padding:18px;box-shadow:0 20px 60px rgba(8,10,20,0.35);transform-origin:center;animation:phd-modal-in 360ms cubic-bezier(.2,.9,.3,1)}
@keyframes phd-modal-in{from{transform:translateY(8px) scale(.995);opacity:0}to{transform:translateY(0) scale(1);opacity:1}}
.phd-modal-header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}
.phd-modal-body{font-size:14px;color:#222;line-height:1.45;margin-top:8px;max-height:58vh;overflow:auto}
@media (max-width:640px){.phd-card{flex-direction:column;align-items:stretch;gap:10px;padding:12px}.phd-meter{width:100%;max-width:none;order:3}.phd-actions{margin-left:0;justify-content:flex-end}}
`;
    document.head.appendChild(s);
  };
})();

let lastScannedEmailId = null;
let lastBannerRoot = null;
let shownDnsDomains = new Set();

const escapeHtml = (s = "") => String(s).replace(/[&<>"'`]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;","`":"&#96;" }[c]));

const getGradientForScore = score => {
  const pct = Math.max(0, Math.min(1, Number(score)));
  if (pct >= 0.8) return "linear-gradient(90deg,#ff4d4f,#ff7a7a)";
  if (pct >= 0.5) return "linear-gradient(90deg,#ffb74d,#ffd27a)";
  return "linear-gradient(90deg,#7ad39a,#4bd37a)";
};

const findInsertionTarget = () => {
  const c = ['.aeH','.nH','.nH.Hd','.ii.gt','.a3s','.adn'];
  for (const sel of c) {
    const el = qs(sel);
    if (el) return el;
  }
  return document.body;
};

const removeExistingBannerAndModal = () => {
  const b = document.getElementById("phishdetect-banner");
  if (b) b.remove();
  lastBannerRoot = null;
  const mod = document.getElementById("phishdetect-modal-overlay");
  if (mod) {
    mod.style.display = "none";
    mod.innerHTML = "";
  }
};

const createBanner = (result = {}) => {
  try {
    removeExistingBannerAndModal();
    injectStyles();
    const score = Number(result.final_score ?? result.score ?? 0);
    let severity = "safe";
    if (score >= 0.8) severity = "phish";
    else if (score >= 0.5) severity = "susp";
    const map = {
      safe: { icon: "✅", title: "Safe email", sub: "Likely legitimate.", ic: "safe", cc: "phd-safe" },
      susp: { icon: "⚠️", title: "Suspicious email", sub: "Be cautious — some signals look risky.", ic: "susp", cc: "phd-susp" },
      phish: { icon: "🚨", title: "Phishing attempt detected!", sub: "High risk — do not click links or reply.", ic: "phish", cc: "phd-phish" }
    };
    const meta = map[severity];
    const root = create("div", { id: "phishdetect-banner", style: { display: "flex", justifyContent: "center", pointerEvents: "auto" } });
    const card = create("div", { class: `phd-card ${meta.cc}`, role: "status", "aria-live": "polite" });
    card.style.animation = "phd-fade-slide 420ms ease both";
    const left = create("div", { class: "phd-left" });
    const iconWrap = create("div", { class: `phd-icon ${meta.ic}`, title: meta.title });
    const emoji = create("div", { style: { transformOrigin: "center", display: "inline-block", animation: "phd-emoji-bounce 2200ms infinite" } }, [meta.icon]);
    iconWrap.appendChild(emoji);
    const msg = create("div", { class: "phd-msg" });
    const title = create("div", { class: "phd-title", innerHTML: meta.title });
    const sub = create("div", { class: "phd-sub", innerHTML: `${meta.sub} <span style="opacity:.9">Score: <b>${score.toFixed(2)}</b></span>` });
    const reasonsText = (Array.isArray(result.reasons) && result.reasons.length) ? result.reasons.join(", ") : (result.reasons || "");
    const reasonEl = create("div", { class: "phd-sub", style: { fontSize: "12px", opacity: 0.85, marginTop: "6px" } });
    reasonEl.innerHTML = reasonsText ? `<small>Signals: ${escapeHtml(reasonsText)}</small>` : `<small>No notable signals.</small>`;
    msg.appendChild(title);
    msg.appendChild(sub);
    msg.appendChild(reasonEl);
    left.appendChild(iconWrap);
    left.appendChild(msg);
    const right = create("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 } });
    const meter = create("div", { class: "phd-meter" });
    const label = create("div", { class: "label" });
    label.textContent = severity === "phish" ? "Threat level" : severity === "susp" ? "Suspicion level" : "Confidence";
    const bar = create("div", { class: "phd-bar", "aria-hidden": "true" });
    const barInner = create("div", { class: "phd-bar-inner", style: { width: "0%" } });
    barInner.style.background = getGradientForScore(score);
    bar.appendChild(barInner);
    meter.appendChild(label);
    meter.appendChild(bar);
    const actions = create("div", { class: "phd-actions" });
    const learnBtn = create("button", { class: "phd-btn phd-learn", type: "button", "aria-label": "Learn more about this detection", onClick: () => openModal(result) }, [create("span", {}, ["Learn more 🔎"])]);
    const dismissBtn = create("button", { class: "phd-close", "aria-label": "Dismiss PhishDetect banner", onClick: () => { dismissBtn.animate([{ transform: "scale(1)" }, { transform: "scale(1.18) rotate(14deg)" }, { transform: "scale(0)" }], { duration: 320, easing: "cubic-bezier(.2,.9,.3,1)" }); setTimeout(() => root.remove(), 320); } }, ["✕"]);
    actions.appendChild(learnBtn);
    actions.appendChild(dismissBtn);
    right.appendChild(meter);
    right.appendChild(actions);
    card.appendChild(left);
    card.appendChild(right);
    root.appendChild(card);
    const target = findInsertionTarget();
    if (target && target.parentNode) target.parentNode.insertBefore(root, target);
    else document.body.prepend(root);
    requestAnimationFrame(() => {
      const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
      barInner.style.width = pct + "%";
    });
    observeAndKeep(root, target);
    lastBannerRoot = root;
  } catch (e) {
    console.error("createBanner error", e);
  }
};

const showDnsBanner = (domain = "unknown", score = 0) => {
  if (typeof domain !== "string") domain = String(domain || "unknown");
  if (shownDnsDomains.has(domain)) return;
  shownDnsDomains.add(domain);
  // removeExistingBannerAndModal(); // ❌ remove this line to preserve phishing banner
  injectStyles();
  const root = create("div", { id: "dns-banner", style: { display: "flex", justifyContent: "center", pointerEvents: "auto" } });
  const card = create("div", { class: "phd-card phd-phish", role: "alert", "aria-live": "assertive" });
  card.style.animation = "phd-fade-slide 420ms ease both";
  const left = create("div", { class: "phd-left" });
  const iconWrap = create("div", { class: "phd-icon phish" }, ["⚠️"]);
  const msg = create("div", { class: "phd-msg" });
  const title = create("div", { class: "phd-title", innerHTML: "DNS tunneling detected!" });
  const sub = create("div", { class: "phd-sub", innerHTML: `Domain: <b>${escapeHtml(domain)}</b> — Score: <b>${Number(score).toFixed(2)}</b>` });
  msg.appendChild(title);
  msg.appendChild(sub);
  left.appendChild(iconWrap);
  left.appendChild(msg);
  const right = create("div", { style: { display: "flex", alignItems: "center", gap: "8px" } });
  const closeBtn = create("button", { class: "phd-close", onClick: () => root.remove() }, ["✕"]);
  right.appendChild(closeBtn);
  card.appendChild(left);
  card.appendChild(right);
  root.appendChild(card);
  const target = findInsertionTarget();
  if (target && target.parentNode) target.parentNode.insertBefore(root, target);
  else document.body.prepend(root);
  root.id = "dns-banner";
};


const openModal = (result = {}) => {
  injectStyles();
  let overlay = document.getElementById("phishdetect-modal-overlay");
  if (!overlay) {
    overlay = create("div", { id: "phishdetect-modal-overlay", role: "dialog", "aria-modal": "true" });
    document.body.appendChild(overlay);
  }
  overlay.style.display = "flex";
  overlay.innerHTML = "";
  const modal = create("div", { id: "phishdetect-modal" });
  const header = create("div", { class: "phd-modal-header" });
  const title = create("div", { style: { fontWeight: 800, fontSize: "16px" } }, ["Why this email is flagged"]);
  const close = create("button", { class: "phd-close", onClick: () => { overlay.style.display = "none"; overlay.innerHTML = ""; } }, ["✕"]);
  header.appendChild(title);
  header.appendChild(close);
  const body = create("div", { class: "phd-modal-body" });
  const score = Number(result.final_score ?? result.score ?? 0);
  const reasons = Array.isArray(result.reasons) ? result.reasons : (result.reasons ? [result.reasons] : []);
  body.appendChild(create("div", { style: { marginBottom: "6px", fontSize: "13px", opacity: 0.9 } }, [`Score: ${score.toFixed(2)} — ${score >= 0.8 ? "High risk" : score >= 0.5 ? "Potential risk" : "Likely safe"}`]));
  if (reasons.length) {
    body.appendChild(create("div", { style: { fontWeight: 700, marginTop: "6px", marginBottom: "6px" } }, ["Signals we found:"]));
    const ul = create("ul");
    reasons.forEach(r => ul.appendChild(create("li", { style: { marginBottom: "6px", fontSize: "13px" } }, [escapeHtml(r)])));
    body.appendChild(ul);
  } else {
    body.appendChild(create("div", { style: { fontSize: "13px", opacity: 0.9 } }, ["No detailed signals were returned by the scanner."]));
  }
  if (result.raw_input || result.debug) {
    const dbg = create("details", { style: { marginTop: "10px", fontSize: "13px" } });
    dbg.appendChild(create("summary", {}, ["Show raw scanner data"]));
    dbg.appendChild(create("pre", { style: { fontSize: "12px", whiteSpace: "pre-wrap", maxHeight: "220px", overflow: "auto" } }, [JSON.stringify(result, null, 2)]));
    body.appendChild(dbg);
  }
  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  overlay.addEventListener("click", ev => { if (ev.target === overlay) { overlay.style.display = "none"; overlay.innerHTML = ""; } }, { once: true });
};

const extractEmail = () => {
  const subjectEl = qs('h2[role="heading"]') || qs('.hP') || {};
  const bodyEl = qs('.ii.gt') || qs('.a3s') || qs('.ii') || {};
  const subject = (subjectEl && subjectEl.innerText) ? subjectEl.innerText.trim() : "";
  let body = "";
  if (bodyEl && bodyEl.innerText) body = bodyEl.innerText.trim();
  else body = qsa('.a3s,.ii').map(n => n.innerText || "").join("\n").trim();
  return { subject, body };
};

const simpleId = (s) => {
  try {
    return btoa(s).replace(/=+$/,'').slice(0,36);
  } catch (e) {
    return String(s).slice(0,36);
  }
};

const removeBannerOnNewEmail = () => {
  removeExistingBannerAndModal();
  shownDnsDomains.clear();
  lastScannedEmailId = null;
};

const scanNow = (force = false) => {
  const data = extractEmail();
  if (!data.subject && !data.body) return;
  const id = simpleId(data.subject + "||" + data.body);
  if (!force && lastScannedEmailId === id) return;
  lastScannedEmailId = id;
  removeExistingBannerAndModal();
  chrome.runtime.sendMessage({ action: "scan_text", payload: data }, response => {
    if (chrome.runtime.lastError) return;
    if (!response || response.error) return;
    response.raw_input = data;
    createBanner(response);
  });
};

chrome.runtime.onMessage.addListener(msg => {
  if (!msg || !msg.action) return;
  if (msg.action === "dns_alert") {
    const a = msg.alerts && msg.alerts[0] ? msg.alerts[0] : {};
    showDnsBanner(a.domain || "unknown", Number(a.score ?? 0));
  }
});

let clickTimer = null;
document.addEventListener("click", () => {
  if (clickTimer) clearTimeout(clickTimer);
  clickTimer = setTimeout(() => { scanNow(); clickTimer = null; }, 800);
});
document.addEventListener("keydown", ev => {
  if (["j","k","ArrowDown","ArrowUp","PageDown","PageUp"].includes(ev.key)) setTimeout(() => scanNow(), 420);
});

const observeEmailChanges = (() => {
  let observer = null;
  return () => {
    const target = findInsertionTarget();
    if (!target) return;
    if (observer) observer.disconnect();
    observer = new MutationObserver(muts => {
      for (const m of muts) {
        if (m.addedNodes.length || m.removedNodes.length) {
          setTimeout(() => scanNow(), 260);
          break;
        }
      }
    });
    observer.observe(target, { childList: true, subtree: true });
    setTimeout(() => observer && observer.disconnect(), 30000);
  };
})();

function observeAndKeep(bannerRoot, anchorNode) {
  const parent = (anchorNode && anchorNode.parentNode) || document.body;
  const mo = new MutationObserver(() => {
    if (!document.body.contains(bannerRoot)) {
      try {
        const insertionTarget = findInsertionTarget();
        if (insertionTarget && insertionTarget.parentNode) insertionTarget.parentNode.insertBefore(bannerRoot, insertionTarget);
        else document.body.prepend(bannerRoot);
      } catch {}
      finally { mo.disconnect(); }
    }
  });
  mo.observe(parent, { childList: true, subtree: true });
  setTimeout(() => mo.disconnect(), 10000);
}

setTimeout(() => { scanNow(); observeEmailChanges(); }, 700);
