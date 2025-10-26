# phish_model.py
import os
import re
import math
import joblib

MODEL_PATH = os.path.join(os.path.dirname(__file__), "phish_model.joblib")

_artifacts = None
if os.path.exists(MODEL_PATH):
    try:
        _artifacts = joblib.load(MODEL_PATH)
        tfidf = _artifacts.get("tfidf")
        scaler = _artifacts.get("scaler")
        clf = _artifacts.get("clf")
        meta = _artifacts.get("meta", {})
        FREE_DOMAINS = set(meta.get("free_domains", []))
        print("phish_model: loaded artifacts")
    except Exception as e:
        print("phish_model: failed loading model:", e)
        tfidf = scaler = clf = None
        FREE_DOMAINS = set()
else:
    tfidf = scaler = clf = None
    FREE_DOMAINS = set()

def extract_links(text):
    return re.findall(r"https?://[^\s)\"'>]+", text or "")

def host_entropy_from_url(url):
    try:
        from urllib.parse import urlparse
        h = urlparse(url).hostname or ""
        if not h: return 0.0
        counts = {}
        for c in h:
            counts[c] = counts.get(c, 0) + 1
        probs = [v/len(h) for v in counts.values()]
        ent = -sum(p * math.log(p, 2) for p in probs)
        return ent
    except Exception:
        return 0.0

def sender_domain(email_or_domain):
    if not isinstance(email_or_domain, str) or email_or_domain.strip() == "":
        return ""
    if "@" in email_or_domain:
        return email_or_domain.split("@")[-1].lower().strip()
    return email_or_domain.lower().strip()

def extract_sender_features(sender):
    d = sender_domain(sender)
    sender_domain_len = len(d)
    sender_has_digits = int(bool(re.search(r'\d', d)))
    sender_is_free = int(d in FREE_DOMAINS)
    sender_tld_unusual = int(d.endswith(('.tk','.xyz','.top','.club','.info')) or d.endswith('.ru'))
    return {
        "sender_domain_len": sender_domain_len,
        "sender_has_digits": sender_has_digits,
        "sender_is_free": sender_is_free,
        "sender_tld_unusual": sender_tld_unusual
    }

def heuristic_score_and_reasons(text):
    text = (text or "").lower()
    reasons = []
    score = 0.0

    # token words (slightly reduced)
    if re.search(r'\b(verify|confirm|login|password|secure)\b', text):
        reasons.append("contains-token:verify/confirm/login")
        score += 0.40  # was 0.35

    # URL presence (reduced)
    if re.search(r'https?://', text):
        reasons.append("contains-url")
        score += 0.3  # was 0.25

    # banking keywords (reduced)
    if re.search(r'\b(bank|account|payment)\b', text):
        reasons.append("contains-credential-words")
        score += 0.25  # was 0.2

    # entropy for URL host (reduced weight and threshold)
    urls = extract_links(text)
    if urls:
        ent = host_entropy_from_url(urls[0])
        # lower threshold and weight so it triggers less aggressively
        if ent > 2.0:               # previously > 3.0
            reasons.append("high entropy in host")
            score += 0.25          # was 0.2

    score = max(0.0, min(1.0, score))
    label = "phishing" if score >= 0.5 else "benign"
    return score, label, reasons

def predict_text_ml(subject, body, sender=""):
    """
    Returns (proba, label) or None if model not available.
    """
    if clf is None or tfidf is None or scaler is None:
        return None
    try:
        text = ((subject or "") + " " + (body or "")).lower()
        X_text = tfidf.transform([text])
        # numeric features must match training order
        num_links = len(extract_links(body or ""))
        has_login = 1 if re.search(r'\b(verify|confirm|login|password|secure)\b', (body or ""), flags=re.I) else 0
        links = extract_links(body or "")
        first_entropy = host_entropy_from_url(links[0]) if links else 0.0
        sfeat = extract_sender_features(sender or "")
        import numpy as np
        from scipy.sparse import hstack
        X_num = scaler.transform([[num_links, has_login, first_entropy,
                                   sfeat['sender_domain_len'], sfeat['sender_has_digits'],
                                   sfeat['sender_is_free'], sfeat['sender_tld_unusual']]])
        X = hstack([X_text, X_num])
        proba = float(clf.predict_proba(X)[:,1][0])
        label = "phishing" if proba >= 0.5 else "benign"
        return proba, label
    except Exception as e:
        print("predict_text_ml error:", e)
        return None
