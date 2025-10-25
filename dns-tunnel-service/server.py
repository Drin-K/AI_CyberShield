# server.py - dns-tunnel-service (updated)
from flask import Flask, request, jsonify
import threading
import time
import os
import json
import traceback
import joblib
import re
from urllib.parse import urlparse
import tldextract
import requests

app = Flask(__name__)

STORE = {}
LOCK = threading.Lock()

# Model loading
MODEL_PATH = os.environ.get("MODEL_PATH", "model.pkl")
model = None
if os.path.exists(MODEL_PATH):
    try:
        model = joblib.load(MODEL_PATH)
        print("[dns-server] Loaded model:", MODEL_PATH)
    except Exception as e:
        print("[dns-server] Failed to load model:", e)
        traceback.print_exc()

PHISHING_URL = os.environ.get("PHISHING_SERVICE_URL")  # e.g. http://phishing:5000/api/phishing_alert
PHISHING_KEY = os.environ.get("PHISHING_ALERT_API_KEY")  # optional API key for Authorization header
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "0.6"))

# ------------- Helper: extract domain from reassembled payload -------------
def extract_domain_from_reassembled(reassembled):
    """
    Try multiple heuristics to extract a base domain from the reassembled bytes/string.
    Returns normalized base domain like example.com or None.
    """
    try:
        if isinstance(reassembled, bytes):
            text = reassembled.decode("utf-8", errors="ignore")
        else:
            text = str(reassembled)
    except Exception:
        text = str(reassembled)

    # 1) look for full URLs first
    m = re.search(r"https?://[^\s'\"<>()]+", text, flags=re.IGNORECASE)
    if m:
        try:
            host = urlparse(m.group(0)).hostname
            if host:
                ext = tldextract.extract(host)
                if ext.domain:
                    return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        except Exception:
            pass

    # 2) find hostname-like tokens e.g. sub.example.com or example.test
    m2 = re.search(r"([a-z0-9\-\.]+\.[a-z]{2,})(?:[:/\s]|$)", text, flags=re.IGNORECASE)
    if m2:
        candidate = m2.group(1).strip(".")
        try:
            ext = tldextract.extract(candidate)
            if ext.domain:
                return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        except Exception:
            pass

    # 3) fallback: try parse any host-looking token
    tokens = re.findall(r"[a-z0-9\-\.]{3,}", text, flags=re.IGNORECASE)
    for tok in tokens:
        if tok.count(".") >= 1 and len(tok) <= 253:
            try:
                ext = tldextract.extract(tok)
                if ext.domain:
                    return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
            except Exception:
                continue

    return None

# ------------- Helper: post alert to phishing service with retries -------------
def post_alert_to_phishing_service(alert: dict):
    if not PHISHING_URL:
        print("[dns-server] PHISHING_SERVICE_URL not set -> skipping POST")
        return None

    headers = {"Content-Type": "application/json"}
    if PHISHING_KEY:
        headers["Authorization"] = f"Bearer {PHISHING_KEY}"

    body = json.dumps(alert)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[dns-server] POST attempt {attempt} -> {PHISHING_URL}")
            print(f"[dns-server] headers keys: {list(headers.keys())} payload_preview: {body[:300]}")
            resp = requests.post(PHISHING_URL, data=body, headers=headers, timeout=6)
            status = getattr(resp, "status_code", None)
            text_preview = (resp.text or "")[:400] if hasattr(resp, "text") else ""
            print(f"[dns-server] POST status={status} resp_body_preview={text_preview}")
            if status and 200 <= status < 300:
                print("[dns-server] POST succeeded")
                return resp
            else:
                print(f"[dns-server] Non-success status {status}, will retry (if attempts remain)")
        except Exception as e:
            print("[dns-server] Exception during POST:", e)
            traceback.print_exc()

        # backoff
        time.sleep(1.0 * attempt)

    print("[dns-server] Failed to POST alert after retries")
    return None

# ------------- Endpoint: receive chunk stream -------------
@app.route("/api/sim/send_chunk", methods=["POST"])
def send_chunk():
    try:
        data = request.get_json() or {}
        mid = data.get("message_id")
        if not mid:
            return jsonify({"error": "missing message_id"}), 400

        idx = int(data.get("chunk_index", 0))
        total = int(data.get("total_chunks", 1))
        payload_b64 = data.get("payload_b64", "")
        client_id = data.get("client_id")
        ts = data.get("timestamp")

        with LOCK:
            info = STORE.setdefault(mid, {"chunks": {}, "total": total, "last_seen": time.time(), "client_id": client_id})
            info["chunks"][idx] = {"payload_b64": payload_b64, "chunk_index": idx, "timestamp": ts}
            # ensure total is the latest provided
            info["total"] = total
            info["last_seen"] = time.time()
            received = len(info["chunks"])

            if received == info["total"]:
                # copy and remove entry to avoid double processing
                chunks = [info["chunks"][i] for i in sorted(info["chunks"].keys())]
                client = info.get("client_id")
                try:
                    del STORE[mid]
                except KeyError:
                    pass
                # process in background thread
                threading.Thread(target=process_reconstructed, args=(mid, chunks, client), daemon=True).start()
                return jsonify({"status": "complete", "message_id": mid}), 200

        return jsonify({"status": "received", "message_id": mid, "received_chunks": received}), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "internal", "detail": str(e)}), 500

# ------------- Core processing of reconstructed message -------------
def process_reconstructed(message_id, chunks, client_id=None):
    try:
        # extract features and the reassembled payload from your library
        # expected: extract_features_from_chunks(chunks) -> (features, reassembled)
        # import lazily to avoid startup dependency if module not present
        from dns_tunnel_lib.tunnel import extract_features_from_chunks
        features, reassembled = extract_features_from_chunks(chunks)
    except Exception as e:
        print("[dns-server] Failed to extract features from chunks:", e)
        traceback.print_exc()
        # still attempt a minimal features dict so heuristic can run
        features = {
            "chunk_count": len(chunks),
            "avg_chunk_size": 0,
            "std_chunk_size": 0,
            "total_bytes": 0,
            "interarrival_mean": 0,
            "duration": 0,
            "entropy": 0,
            "printable_ratio": 1.0
        }
        reassembled = None

    # build vector for model (same ordering as training)
    vec = [
        features.get("chunk_count", 0),
        features.get("avg_chunk_size", 0.0),
        features.get("std_chunk_size", 0.0),
        features.get("total_bytes", 0),
        features.get("interarrival_mean", 0.0),
        features.get("duration", 0.0),
        features.get("entropy", 0.0),
        features.get("printable_ratio", 1.0),
    ]

    # scoring
    score = None
    reasons = []
    if model:
        try:
            prob = model.predict_proba([vec])[0]
            score = float(prob[1])
            reasons.append("ml_model")
        except Exception as e:
            print("[dns-server] model predict failed, falling back to heuristic:", e)
            traceback.print_exc()
            score = heuristic_score_from_features(features)
            reasons.append("heuristic_after_model_failure")
    else:
        score = heuristic_score_from_features(features)
        reasons.append("heuristic_fallback")

    # extract domain from reassembled (important!)
    domain = extract_domain_from_reassembled(reassembled)
    if domain:
        norm = domain.lower()
    else:
        norm = None

    alert = {
        # include domain (if available) - phishing-service requires this
        "domain": norm,
        "message_id": message_id,
        "client_id": client_id,
        "features": features,
        "score": score,
        "reasons": reasons,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    print(f"[dns-server] Processed message: {message_id} score: {score} domain: {norm}")

    # If above threshold and domain present (or you still want to send unknown-domain alerts, you can)
    if score is not None and score >= ALERT_THRESHOLD:
        # if domain is missing, phishing-service will reject (and return missing domain).
        # we could choose to send with domain="unknown" or skip; here we send only if domain present.
        if not norm:
            print("[dns-server] WARNING: domain not found in reassembled payload -> phishing-service may reject. Skipping POST.")
            return

        print(f"[dns-server] score {score} >= threshold {ALERT_THRESHOLD} -> sending alert")
        resp = post_alert_to_phishing_service(alert)
        if resp is None:
            print("[dns-server] Alert could not be delivered to phishing-service")
        # else logged inside post_alert...
    else:
        print(f"[dns-server] score {score} < threshold {ALERT_THRESHOLD} -> not sending")

def heuristic_score_from_features(f):
    score = 0.0
    try:
        if f.get("chunk_count", 0) >= 6:
            score += 0.4
        if f.get("avg_chunk_size", 9999) < 150:
            score += 0.25
        if f.get("entropy", 0.0) > 4.0:
            score += 0.2
        if f.get("printable_ratio", 1.0) < 0.5:
            score += 0.2
    except Exception as e:
        print("[dns-server] heuristic calc error:", e)
    return min(score, 1.0)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "model_loaded": bool(model)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8053))
    print(f"[dns-server] Starting on 0.0.0.0:{port}, PHISHING_URL={PHISHING_URL}, ALERT_THRESHOLD={ALERT_THRESHOLD}")
    app.run(host="0.0.0.0", port=port, debug=True)
