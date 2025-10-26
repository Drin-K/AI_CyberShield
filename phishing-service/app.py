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
from phish_model import predict_text_ml

import smtplib
from email.mime.text import MIMEText

SOC_EMAIL = "bardh.tahiri@student.uni-pr.edu"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "bardhtahiri15@gmail.com"
SMTP_PASS = "pobm iejj ogab zkud"  # app password
SMTP_USE_TLS = True


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

        # -------------------- ML PREDICTION --------------------
        ml_result = predict_text_ml(subject, body)
        ml_score = None
        if ml_result:
            ml_score = ml_result[0]  # probability
            ml_label = ml_result[1]  # label
        else:
            ml_score = 0.0
            ml_label = "benign"

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

        heuristic_score = max(max_url_score, text_score)

        # -------------------- COMBINE ML + HEURISTICS --------------------
        if ml_score is not None:
            final_score = (ml_score * 0.65) + (heuristic_score * 0.35)
        else:
            final_score = heuristic_score

        print(f"[DEBUG] ML_RESULT -> score={ml_score:.4f}, label={ml_label}")
        sys.stdout.flush()

        # -------------------- DNS ALERT CHECK --------------------
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

        # -------------------- FINAL LABEL --------------------
        if final_score >= 0.8:
            final_label = "phishing"
        elif final_score >= 0.6:
            final_label = "warning"
        else:
            final_label = "safe"

        dedup_reasons = []
        for r in aggregated_reasons:
            if r not in dedup_reasons:
                dedup_reasons.append(r)

        # -------------------- RESPONSE --------------------
        print(f"ML={ml_score:.3f}, Heuristic={heuristic_score:.3f}, Final={final_score:.3f}, Label={final_label}")
        return jsonify({
            "final_score": round(final_score, 4),
            "final_label": final_label,
            "ml_score": round(ml_score, 4) if ml_score is not None else None,
            "ml_label": ml_label,
            "heuristic_score": round(heuristic_score, 4),
            "reasons": dedup_reasons,
            "urls": url_results,
            "dns_alerts": matched_alerts
        })
    except Exception as e:
        print("❌ Error in scan_text:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
        print(final_score)

@app.route("/api/report_to_soc", methods=["POST"])
def report_to_soc():
    """
    Accepts JSON: { "domain": "...", "subject": "...", "body": "...", "reason": "..." }
    Sends an email to SOC_EMAIL but DOES NOT quarantine.
    """
    data = request.get_json(silent=True) or {}
    domain = data.get("domain")
    subject = data.get("subject", "PhishDetect SOC report")
    body = data.get("body", "")
    reason = data.get("reason", "Reported by user via PhishDetect")

    if not domain:
        return jsonify({"error": "missing domain"}), 400

    text = f"""PhishDetect Report

Domain: {domain}
Reason: {reason}

Original subject: {subject}

Original body:
{body}

(Reported at: {datetime.utcnow().isoformat()} UTC)
"""
    msg = MIMEText(text)
    msg["Subject"] = f"[PhishDetect] SOC report: {domain}"
    msg["From"] = os.getenv("ALERT_FROM", "noreply@phishdetect.local")
    msg["To"] = SOC_EMAIL

    try:
        if SMTP_USER and SMTP_PASS:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
            server.quit()
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.send_message(msg)
            server.quit()

        print(f"📧 SOC report sent for domain {domain} -> {SOC_EMAIL}")
        return jsonify({"status": "ok", "sent_to": SOC_EMAIL}), 200
    except Exception as e:
        print("⚠️ Failed to send SOC email:", e)
        try:
            with open("soc_reports.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.utcnow().isoformat()} REPORT domain={domain} reason={reason}\n")
        except Exception as e2:
            print("Failed to write local log:", e2)
        return jsonify({"status": "error", "error": str(e)}), 500

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

@app.route("/api/quarantine", methods=["POST"])
def quarantine_domain():
    data = request.get_json() or {}
    domain = data.get("domain")
    reason = data.get("reason", "Manual quarantine from Chrome extension")

    if not domain:
        return jsonify({"error": "missing domain"}), 400

    try:
        db = next(get_db())
        from models import DNSAlert
        from datetime import datetime, timedelta

        # vendos si quarantined (skadon pas 7 dite)
        expires_at = datetime.utcnow() + timedelta(days=7)
        alert = DNSAlert(
            domain=domain.lower(),
            score=1.0,
            reasons=reason,
            observed_at=datetime.utcnow(),
            expires_at=expires_at,
            report_count=999  # për ta dalluar si “manual quarantine”
        )
        db.add(alert)
        db.commit()
        db.close()

        # --- (Opsionale) Dërgo email tek SOC ---
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(f"Domain {domain} u karantinua.\nArsye: {reason}")
        msg["Subject"] = f"[AI CyberShield] Domain quarantined: {domain}"
        msg["From"] = "bardhtahiri15@gmail.com"
        msg["To"] = "drinkurti26@gmail.com"
        try:
            with smtplib.SMTP("localhost") as s:
                s.send_message(msg)
            print(f"📧 Email dërguar SOC për {domain}")
        except Exception as e:
            print(f"⚠️ Nuk u dërgua emaili SOC: {e}")

        return jsonify({"status": "ok", "domain": domain}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
