# server.py (final fixed)
from flask import Flask, request, jsonify
from dns_tunnel_lib.tunnel import extract_features_from_chunks
import traceback
import os
import joblib
import threading
import time
import json
import requests
import traceback as _tb

app = Flask(__name__)

STORE = {}
LOCK = threading.Lock()

MODEL_PATH = os.environ.get("MODEL_PATH", "model.pkl")
model = None
if os.path.exists(MODEL_PATH):
    try:
        model = joblib.load(MODEL_PATH)
        print("Loaded model:", MODEL_PATH)
    except Exception as e:
        print("Failed to load model:", e)

PHISHING_URL = os.environ.get("PHISHING_SERVICE_URL")
PHISHING_KEY = os.environ.get("PHISHING_ALERT_API_KEY")  # if set, will send Authorization header
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "0.6"))

# -------------------------
# Helper: POST to phishing service with retries + logging
# -------------------------
def post_alert_to_phishing_service(alert: dict):
    """
    Post alert (dict) to PHISHING_URL with optional Authorization header.
    Retries on failure (max 3 attempts). Prints detailed logs.
    Returns response object on success (2xx), or None on failure.
    """
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
            _tb.print_exc()
        # simple backoff
        time.sleep(1.0 * attempt)
    print("[dns-server] Failed to POST alert after retries")
    return None


# -------------------------
# Flask endpoints
# -------------------------
@app.route("/api/sim/send_chunk", methods=["POST"])
def send_chunk():
    try:
        data = request.get_json() or {}
        mid = data.get("message_id")
        idx = int(data.get("chunk_index", 0))
        total = int(data.get("total_chunks", 1))
        payload_b64 = data.get("payload_b64", "")
        client_id = data.get("client_id")
        ts = data.get("timestamp")

        if not mid:
            return jsonify({"error": "missing message_id"}), 400

        with LOCK:
            info = STORE.setdefault(mid, {"chunks": {}, "total": total, "last_seen": time.time(), "client_id": client_id})
            info["chunks"][idx] = {"payload_b64": payload_b64, "chunk_index": idx, "timestamp": ts}
            received = len(info["chunks"])
            info["total"] = total
            info["last_seen"] = time.time()

            if received == info["total"]:
                chunks = [info["chunks"][i] for i in sorted(info["chunks"].keys())]
                client = info.get("client_id")
                try:
                    del STORE[mid]
                except KeyError:
                    pass
                threading.Thread(target=process_reconstructed, args=(mid, chunks, client), daemon=True).start()
                return jsonify({"status": "complete", "message_id": mid}), 200

        return jsonify({"status": "received", "message_id": mid, "received_chunks": received}), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "internal", "detail": str(e)}), 500


def process_reconstructed(message_id, chunks, client_id=None):
    try:
        features, reassembled = extract_features_from_chunks(chunks)

        vec = [
            features.get("chunk_count", 0),
            features.get("avg_chunk_size", 0.0),
            features.get("std_chunk_size", 0.0),
            features.get("total_bytes", 0),
            features.get("interarrival_mean", 0.0),
            features.get("duration", 0.0),
            features.get("entropy", 0.0),
            features.get("printable_ratio", 1.0)
        ]

        score = None
        reasons = []
        if model:
            try:
                prob = model.predict_proba([vec])[0]
                score = float(prob[1])
                reasons.append("ml_model")
            except Exception as e:
                print("[dns-server] model predict failed, falling back to heuristic:", e)
                _tb.print_exc()
                score = heuristic_score_from_features(features)
                reasons.append("heuristic_after_model_failure")
        else:
            score = heuristic_score_from_features(features)
            reasons.append("heuristic_fallback")

        # ✅ FIX: define domain_name before using it
        domain_name = f"dns-alert-{client_id or message_id}.local"

        alert = {
            "domain": domain_name,
            "message_id": message_id,
            "client_id": client_id,
            "features": features,
            "score": score,
            "reasons": reasons,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        print(f"Processed message: {message_id} score: {score}")

        if score is not None and score >= ALERT_THRESHOLD:
            print(f"[dns-server] score {score} >= threshold {ALERT_THRESHOLD} -> sending alert")
            resp = post_alert_to_phishing_service(alert)
            if resp is None:
                print("[dns-server] Alert could not be delivered to phishing-service")
        else:
            print(f"[dns-server] score {score} < threshold {ALERT_THRESHOLD} -> not sending")

    except Exception:
        traceback.print_exc()


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
    print(f"Starting dns-tunnel-service on 0.0.0.0:{port}, PHISHING_URL={PHISHING_URL}, ALERT_THRESHOLD={ALERT_THRESHOLD}")
    app.run(host="0.0.0.0", port=port, debug=True)
