# app.py
import os
import re
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, request, jsonify
from flask_cors import CORS
import tldextract
import sys

# DB / SQLAlchemy imports
from db import engine, Base, get_db
from models import DNSAlert
from db_helpers import upsert_dns_alert, get_active_alerts
from phish_model import heuristic_score_and_reasons


# -----------------------
# DEBUG STARTUP PRINTS
# -----------------------
print(">>> APP DEBUG START")
print("python exe:", sys.executable)
print("python version:", sys.version)
print("cwd:", os.getcwd())
print("DATABASE_URL env:", os.getenv("DATABASE_URL"))
print("PHISHING_ALERT_API_KEY:", bool(os.getenv("PHISHING_ALERT_API_KEY")))
print("ENABLE_CLEANUP_WORKER:", os.getenv("ENABLE_CLEANUP_WORKER"))
sys.stdout.flush()


# -----------------------
# Flask app setup
# -----------------------
app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://127.0.0.1:5000", "http://localhost:5000"])


# Create tables on startup (development only)
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully.")
except Exception as e:
    print("❌ Error creating database tables:", e)
    sys.exit(1)

# Configs
ALERT_TTL_HOURS = int(os.getenv("ALERT_TTL_HOURS", "24"))
PHISHING_ALERT_API_KEY = os.getenv("PHISHING_ALERT_API_KEY")
SCORE_BUMP_FACTOR = float(os.getenv("SCORE_BUMP_FACTOR", "0.15"))

# Regex for URLs
URL_RE = re.compile(r"https?://[^\s)'\"]+|www\.[^\s)'\"]+", re.IGNORECASE)


# -----------------------
# Helper functions
# -----------------------
def extract_urls(text: str):
    return URL_RE.findall(text or "")


def domain_from_url(url: str):
    try:
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        ext = tldextract.extract(url)
        if ext.domain:
            return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
    except Exception:
        pass
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def normalize_domain_raw(domain: str):
    try:
        ext = tldextract.extract(domain)
        return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
    except Exception:
        return domain.lower() if domain else None


def load_active_alerts_map(db):
    alerts = get_active_alerts(db)
    return {a.domain.lower(): a for a in alerts}


# -----------------------
# Endpoint: receive DNS alerts
# -----------------------
@app.route("/api/phishing_alert", methods=["POST"])
def receive_dns_alert():
    if PHISHING_ALERT_API_KEY:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.split()[1] != PHISHING_ALERT_API_KEY:
            return jsonify({"error": "unauthorized"}), 401

    db = next(get_db())
    try:
        data = request.get_json(silent=True) or {}
        domain_in = data.get("domain")
        if not domain_in:
            return jsonify({"error": "missing domain"}), 400

        norm_domain = normalize_domain_raw(domain_in)
        score = float(data.get("score") or 0.0)
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

        db.commit()
        return jsonify({"status": "ok", "domain": norm_domain, "score": alert.score}), 200

    except Exception as e:
        db.rollback()
        print("❌ Error in receive_dns_alert:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# -----------------------
# Endpoint: list active alerts
# -----------------------
@app.route("/api/phishing_alerts", methods=["GET"])
def list_alerts():
    db = next(get_db())
    try:
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
    except Exception as e:
        print("❌ Error in list_alerts:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# -----------------------
# Endpoint: scan text
# -----------------------
@app.route("/api/scan_text", methods=["POST"])
def scan_text():
    db = next(get_db())
    try:
        data = request.get_json(silent=True) or {}
        subject = data.get("subject", "")
        body = data.get("body", "")
        combined_text = (subject + "\n" + body)[:10000]

        urls = extract_urls(combined_text)
        url_results = []
        max_url_score = 0.0
        aggregated_reasons = []

        for u in urls:
            try:
                s, label, reasons = heuristic_score_and_reasons(u)
            except Exception:
                s, label, reasons = 0.0, "benign", []
            url_results.append({"url": u, "score": s, "label": label, "reasons": reasons})
            max_url_score = max(max_url_score, s)
            aggregated_reasons.extend(reasons or [])

        try:
            text_score, text_label, text_reasons = heuristic_score_and_reasons(combined_text)
        except Exception:
            text_score, text_label, text_reasons = 0.0, "benign", []
        aggregated_reasons.extend(text_reasons or [])

        final_score = max(max_url_score, text_score)

        alert_map = load_active_alerts_map(db)
        matched_alerts = []
        seen_domains = set()
        for ur in url_results:
            u = ur["url"]
            d = domain_from_url(u)
            if not d:
                continue
            ld = d.lower()
            if ld in seen_domains:
                continue
            seen_domains.add(ld)

            for adomain, alert_row in alert_map.items():
                if ld == adomain or ld.endswith("." + adomain):
                    matched_alerts.append({
                        "url": u,
                        "domain": adomain,
                        "alert_score": alert_row.score,
                        "reasons": (alert_row.reasons or "").split(",") if alert_row.reasons else []
                    })
                    bump = SCORE_BUMP_FACTOR * float(alert_row.score or 1.0)
                    final_score = min(1.0, final_score + bump)
                    aggregated_reasons.append(f"dns alert for {adomain} (+{bump:.2f})")

        final_label = "phishing" if final_score >= 0.5 else "benign"
        dedup_reasons = []
        for r in aggregated_reasons:
            if r not in dedup_reasons:
                dedup_reasons.append(r)

        return jsonify({
            "final_score": round(final_score, 4),
            "final_label": final_label,
            "reasons": dedup_reasons,
            "urls": url_results,
            "dns_alerts": matched_alerts
        })
    except Exception as e:
        print("❌ Error in scan_text:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# -----------------------
# Health endpoint
# -----------------------
@app.route("/health", methods=["GET"])
def health():
    db = next(get_db())
    try:
        alerts = get_active_alerts(db)
        return jsonify({"ok": True, "active_dns_alerts": len(alerts)}), 200
    finally:
        db.close()


# -----------------------
# Cleanup worker (optional)
# -----------------------
def cleanup_expired_worker(interval_seconds=3600):
    import time
    from sqlalchemy.orm import Session
    while True:
        try:
            db: Session = next(get_db())
            now = datetime.utcnow()
            deleted = db.query(DNSAlert).filter(DNSAlert.expires_at < now).delete()
            if deleted:
                db.commit()
                print(f"[cleanup] deleted {deleted} expired alerts")
            db.close()
        except Exception as e:
            print("[cleanup] error:", e)
        time.sleep(interval_seconds)


# -----------------------
# Entry point
# -----------------------
if __name__ == "__main__":
    print(">>> REACHED __main__ - about to call app.run", flush=True)

    if os.getenv("ENABLE_CLEANUP_WORKER", "1") == "1":
        import threading
        t = threading.Thread(target=cleanup_expired_worker, args=(3600,), daemon=True)
        t.start()
        print("🧹 Cleanup worker started.")

    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
