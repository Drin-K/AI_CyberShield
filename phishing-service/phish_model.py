# phish_model.py
from urllib.parse import urlparse
import tldextract, re, math
from collections import Counter
import os, joblib, pandas as pd

# --- helpers (entropy etc.) ---
def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    cnt = Counter(s)
    probs = [v / len(s) for v in cnt.values()]
    import math
    return -sum(p * math.log2(p) for p in probs)

def url_lexical_features(url: str) -> dict:
    try:
        p = urlparse(url if url.startswith(("http://","https://")) else "http://" + url)
    except Exception:
        p = urlparse("http://" + url.replace(" ", ""))
    ext = tldextract.extract(p.netloc + p.path)
    host = p.netloc or ""
    path = p.path or ''
    q = p.query or ''
    features = {}
    features['len_url'] = len(url)
    features['host_len'] = len(host)
    features['path_len'] = len(path)
    features['query_len'] = len(q)
    features['n_subdomains'] = 0 if ext.subdomain=='' else len(ext.subdomain.split('.'))
    features['has_ip'] = 1 if re.match(r'^\d+\.\d+\.\d+\.\d+$', host) else 0
    features['count_dashes'] = url.count('-')
    features['count_at'] = url.count('@')
    features['count_percent'] = url.count('%')
    features['count_digits'] = sum(c.isdigit() for c in url)
    features['entropy_host'] = shannon_entropy(host)
    features['entropy_path'] = shannon_entropy(path)
    return features

# --- simple heuristic score (kept for interpretability) ---
SUSPICIOUS_TOKENS = ["login","signin","bank","secure","update","verify","confirm","account","ebank","paypal"]

def heuristic_score_and_reasons(text: str):
    # Works for URL or general text (will search tokens)
    reasons = []
    score = 0.0
    lower = (text or "").lower()
    hits = [t for t in SUSPICIOUS_TOKENS if t in lower]
    if hits:
        reasons.append(f"contains suspicious token(s): {', '.join(hits)}")
        score += 0.35
    # if looks like URL, add lexical heuristics
    url_like = False
    if text.startswith(("http://","https://","www.")) or "://" in text:
        url_like = True
    if url_like:
        try:
            f = url_lexical_features(text)
            if f['len_url'] > 100:
                reasons.append("very long URL")
                score += 0.15
            if f['count_at'] > 0:
                reasons.append("contains '@' character")
                score += 0.12
            if f['has_ip']:
                reasons.append("host is an IP address")
                score += 0.18
            if f['entropy_host'] > 3.8:
                reasons.append("high entropy in host")
                score += 0.18
        except Exception:
            pass

    score = min(1.0, score)
    label = "phishing" if score >= 0.5 else "benign"
    return score, label, reasons

# --- ML model loader (optional) ---
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "text_model.pkl")
_model = None
def load_model():
    global _model
    if _model is None and os.path.exists(MODEL_PATH):
        _model = joblib.load(MODEL_PATH)
    return _model

def predict_text_ml(subject: str, body: str):
    clf = load_model()
    if not clf:
        return None
    df = pd.DataFrame([{"subject": subject, "body": body}])
    proba = clf.predict_proba(df)[:,1][0]
    label = "phishing" if proba >= 0.5 else "benign"
    return proba, label
