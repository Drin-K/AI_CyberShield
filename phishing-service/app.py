# app.py
import os
import re
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, request, jsonify
import tldextract

# DB / SQLAlchemy imports (db.py, models.py, db_helpers.py duhet të ekzistojnë në folder)
from db import engine, Base, get_db, SessionLocal
from models import DNSAlert
from db_helpers import upsert_dns_alert, get_active_alerts

# Import heuristic URL/text scanner you already have
# This file should export heuristic_score_and_reasons(url_or_text) -> (score, label, reasons)
from phish_model import heuristic_score_and_reasons

# Flask app
app = Flask(__name__)

# create tables on startup (dev). In prod, use migrations (alembic)
Base.metadata.create_all(bind=engine)

# Config
ALERT_TTL_HOURS = int(os.getenv("ALERT_TTL_HOURS", "24"))
PHISHING_ALERT_API_KEY = os.getenv("PHISHING_ALERT_API_KEY")  # optional auth for dns->phish posts
SCORE_BUMP_FACTOR = float(os.getenv("SCORE_BUMP_FACTOR", "0.15"))  # how much to bump final_score per alert (scaled by alert.score)

# URL regex for extracting urls from email text
URL_RE = re.compile(r"https?://[^\s)'\"]+|www\.[^\s)'\"]+", re.IGNORECASE)


# -----------------------
# Helper functions
# -----------------------
def now_iso():
    return datetime.utcnow().isoformat() + "Z"


def extract_urls(text: str):
    if not text:
        return []
    return URL_RE.findall(text)


def domain_from_url(url: str):
    try:
        # ensure scheme for tldextract/urlparse
        if not url.startswith(("http://", "https://")):
            u = "http://" + url
        else:
            u = url
        ext = tldextract.extract(u)
        if ext.domain:
            return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
    except Exception:
        pass
    try:
        return urlparse(u).hostname
    except Exception:
        return None


def normalize_domain_raw(domain: str):
    """Normalize arbitrary input to base domain (example.com)."""
    try:
        ext = tldextract.extract(domain)
        return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
    except Exception:
        return domain.lower() if domain else None


def load_active_alerts_map(db):
    """Return dict domain -> alert row for active alerts (expires_at >= now)."""
    alerts = get_active_alerts(db)
    return {a.domain.lower(): a for a in alerts}


# -----------------------
# Endpoint: receive DNS alerts
# -----------------------
@app.route("/api/phishing_alert", methods=["POST"])
def receive_dns_alert():
    # Optional API key check (prevents anyone from inserting alerts)
    if PHISHING_ALERT_API_KEY:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.split()[1] != PHISHING_ALERT_API_KEY:
            return jsonify({"error": "unauthorized"}), 401

    db = next(get_db())
    data = request.get_json(silent=True) or {}

    # domain required (dns-tunnel-service should include it)
    domain_in = data.get("domain")
    if not domain_in:
        return jsonify({"error": "missing domain"}), 400

    # normalize domain
    norm_domain = normalize_domain_raw(domain_in)

    # parse fields
    try:
        score = float(data.get("score") or 0.0)
    except Exception:
        score = 0.0
    reasons = data.get("reasons") or []
    features = data.get("features") or {}
    client_id = data.get("client_id")
    observed_at_raw = data.get("observed_at")
    if observed_at_raw:
        try:
            observed_at = datetime.fromisoformat(observed_at_raw.replace("Z", "+00:00"))
        except Exception:
            observed_at = datetime.utcnow()
    else:
        observed_at = datetime.utcnow()

    # upsert into DB via helper
    alert = upsert_dns_alert(
        db=db,
        domain=norm_domain,
        score=score,
        reasons=reasons,
        features=features,
        client_id=client_id,
        observed_at=observed_at,
        raw=json.dumps(data),
    )

    return jsonify({"status": "ok", "domain": norm_domain, "score": alert.score}), 200


# -----------------------
# Endpoint: list active alerts (for debugging / UI)
# -----------------------
@app.route("/api/phishing_alerts", methods=["GET"])
def list_alerts():
    db = next(get_db())
    alerts = get_active_alerts(db)
    out = []
    for a in alerts:
        out.append({
            "domain": a.domain,
            "score": a.score,
            "reasons": (a.reasons or "").split(",") if a.reasons else [],
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "report_count": a.report_count
        })
    return jsonify({"alerts": out})


# -----------------------
# Endpoint: scan text (called by extension / IMAP scanner)
# -----------------------
@app.route("/api/scan_text", methods=["POST"])
def scan_text():
    """
    Expected JSON input:
    {
      "subject": "...",
      "body": "...",
      "from": "...",
      "source": "extension" | "imap" | ...
    }
    Response includes:
    {
      "final_score": 0.72,
      "final_label": "phishing",
      "reasons": [...],
      "urls": [...],           # url_results with per-url scores
      "dns_alerts": [...]      # matched dns alerts
    }
    """
    db = next(get_db())
    data = request.get_json(silent=True) or {}
    subject = data.get("subject", "") or ""
    body = data.get("body", "") or ""
    from_field = data.get("from")
    source = data.get("source", "extension")

    combined_text = (subject + "\n" + body)[:10000]  # limit length

    # 1) extract urls
    urls = extract_urls(combined_text)

    # 2) per-URL scoring using existing heuristic model
    url_results = []
    max_url_score = 0.0
    aggregated_reasons = []
    for u in urls:
        try:
            s, label, reasons = heuristic_score_and_reasons(u)
        except Exception:
            # fallback: treat as benign if model errors
            s, label, reasons = 0.0, "benign", []
        url_results.append({"url": u, "score": s, "label": label, "reasons": reasons})
        if s > max_url_score:
            max_url_score = s
        aggregated_reasons.extend(reasons or [])

    # 3) text-level scoring (scan full content) with heuristic model as well
    try:
        text_score, text_label, text_reasons = heuristic_score_and_reasons(combined_text)
    except Exception:
        text_score, text_label, text_reasons = 0.0, "benign", []
    aggregated_reasons.extend(text_reasons or [])

    # initial final score is the max of URL-based and text-based
    final_score = max(max_url_score, text_score)

    # 4) correlate with DNS alerts from DB
    alert_map = load_active_alerts_map(db)  # domain -> alert row
    matched_alerts = []
    # Build set of unique domains from extracted URLs
    seen_domains = set()
    for ur in url_results:
        u = ur.get("url")
        d = domain_from_url(u)
        if not d:
            continue
        # normalize lower
        ld = d.lower()
        if ld in seen_domains:
            continue
        seen_domains.add(ld)

        # match with alerts: exact or suffix (subdomain)
        for adomain, alert_row in alert_map.items():
            # adomain stored in DB should be normalized already
            if ld == adomain or ld.endswith("." + adomain):
                matched_alerts.append({
                    "url": u,
                    "domain": adomain,
                    "alert_score": alert_row.score,
                    "reasons": (alert_row.reasons or "").split(",") if alert_row.reasons else []
                })
                # bump final_score proportional to alert score
                try:
                    bump = SCORE_BUMP_FACTOR * float(alert_row.score or 1.0)
                except Exception:
                    bump = SCORE_BUMP_FACTOR
                final_score = min(1.0, final_score + bump)
                aggregated_reasons.append(f"dns alert for {adomain} (bumped +{bump:.2f})")

    # 5) final label & reasons dedup
    final_label = "phishing" if final_score >= 0.5 else "benign"
    # dedupe reasons preserving order
    dedup_reasons = []
    for r in aggregated_reasons:
        if r not in dedup_reasons:
            dedup_reasons.append(r)

    response = {
        "final_score": round(final_score, 4),
        "final_label": final_label,
        "reasons": dedup_reasons,
        "urls": url_results,
        "dns_alerts": matched_alerts
    }
    return jsonify(response), 200


# -----------------------
# Health endpoint & simple housekeeping
# -----------------------
@app.route("/health", methods=["GET"])
def health():
    db = next(get_db())
    # quick check: count active alerts
    alerts = get_active_alerts(db)
    return jsonify({"ok": True, "active_dns_alerts": len(alerts)}), 200


# -----------------------
# Optional cleanup worker
# -----------------------
def cleanup_expired_worker(interval_seconds=3600):
    """Background thread to cleanup expired alerts from DB periodically.
       If you use DB-level TTL or cron, you can skip this.
    """
    import time
    from sqlalchemy.orm import Session

    while True:
        try:
            db: Session = next(get_db())
            now = datetime.utcnow()
            # delete expired
            deleted = db.query(DNSAlert).filter(DNSAlert.expires_at < now).delete()
            if deleted:
                db.commit()
                print(f"[cleanup] deleted {deleted} expired alerts")
            db.close()
        except Exception as e:
            print("[cleanup] error:", e)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    # start cleanup thread in background for dev/testing
    if os.getenv("ENABLE_CLEANUP_WORKER", "1") == "1":
        import threading
        t = threading.Thread(target=cleanup_expired_worker, args=(3600,), daemon=True)
        t.start()

    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
