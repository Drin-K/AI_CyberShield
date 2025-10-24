# db_helpers.py
from datetime import datetime, timedelta
import json
from models import DNSAlert

ALERT_TTL_HOURS = 24

def upsert_dns_alert(db, domain, score=0.0, reasons=None, features=None, client_id=None, observed_at=None, raw=None):
    reasons = reasons or []
    features = features or {}
    observed_at = observed_at or datetime.utcnow()
    expires_at = datetime.utcnow() + timedelta(hours=ALERT_TTL_HOURS)

    alert = db.query(DNSAlert).filter(DNSAlert.domain == domain).first()
    if alert:
        alert.score = max(alert.score, float(score or 0.0))
        # merge reasons dedup
        existing = (alert.reasons or "").split(",") if alert.reasons else []
        merged = list(dict.fromkeys(existing + reasons))
        alert.reasons = ",".join(merged)
        alert.features = json.dumps(features)
        alert.client_id = client_id
        alert.observed_at = observed_at
        alert.expires_at = expires_at
        alert.report_count = (alert.report_count or 1) + 1
    else:
        alert = DNSAlert(
            domain=domain,
            score=float(score or 0.0),
            reasons=",".join(reasons),
            features=json.dumps(features),
            client_id=client_id,
            observed_at=observed_at,
            expires_at=expires_at,
        )
        db.add(alert)
    db.commit()
    return alert

def get_active_alerts(db):
    now = datetime.utcnow()
    return db.query(DNSAlert).filter(DNSAlert.expires_at >= now).all()
