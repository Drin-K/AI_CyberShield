# server.py
from flask import Flask, request, jsonify
from dns_tunnel_lib.tunnel import extract_features_from_chunks
import traceback
import os
import joblib
import threading
import time

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
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "0.6"))

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
            return jsonify({"error":"missing message_id"}), 400

        with LOCK:
            info = STORE.setdefault(mid, {"chunks": {}, "total": total, "last_seen": time.time(), "client_id": client_id})
            info["chunks"][idx] = {"payload_b64": payload_b64, "chunk_index": idx, "timestamp": ts}
            received = len(info["chunks"])
            info["last_seen"] = time.time()

            if received == info["total"]:
                chunks = [info["chunks"][i] for i in sorted(info["chunks"].keys())]
                threading.Thread(target=process_reconstructed, args=(mid, chunks, info.get("client_id"))).start()
                del STORE[mid]
                return jsonify({"status":"complete","message_id": mid}), 200

        return jsonify({"status":"received","message_id":mid,"received_chunks":received}), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":"internal","detail":str(e)}), 500

def process_reconstructed(message_id, chunks, client_id=None):
    try:
        features, reassembled = extract_features_from_chunks(chunks)
        vec = [
            features["chunk_count"],
            features["avg_chunk_size"],
            features["std_chunk_size"],
            features["total_bytes"],
            features["interarrival_mean"],
            features["duration"],
            features["entropy"],
            features["printable_ratio"]
        ]
        score = None
        reasons = []
        if model:
            prob = model.predict_proba([vec])[0]
            score = float(prob[1])
            reasons.append("ml_model")
        else:
            score = heuristic_score_from_features(features)
            reasons.append("heuristic_fallback")

        alert = {
            "message_id": message_id,
            "client_id": client_id,
            "features": features,
            "score": score,
            "reasons": reasons,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        print("Processed message:", message_id, "score:", score)
        if score >= ALERT_THRESHOLD and PHISHING_URL:
            try:
                import requests
                requests.post(PHISHING_URL, json=alert, timeout=3)
            except Exception as e:
                print("Failed to POST alert:", e)

    except Exception:
        traceback.print_exc()

def heuristic_score_from_features(f):
    score = 0.0
    if f["chunk_count"] >= 6:
        score += 0.4
    if f["avg_chunk_size"] < 150:
        score += 0.25
    if f["entropy"] > 4.0:
        score += 0.2
    if f["printable_ratio"] < 0.5:
        score += 0.2
    return min(score, 1.0)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "model_loaded": bool(model)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8053))
    app.run(host="0.0.0.0", port=port, debug=True)
