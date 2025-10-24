from flask import Flask, request, jsonify
from flask_cors import CORS
import phish_model
import re

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "<h3>PhishDetect backend running with multi-level risk classification</h3>"

@app.route("/api/scan_text", methods=["POST"])
def scan_text():
    data = request.get_json() or {}
    subject = data.get("subject", "")
    body = data.get("body", "")
    sender = data.get("sender", "")

    # ML prediction
    ml = phish_model.predict_text_ml(subject, body, sender)
    ml_score = ml[0] if ml else None
    ml_label = ml[1] if ml else None

    # Heuristic layer
    combined = (subject + "\n" + body)[:5000]
    h_score, h_label, h_reasons = phish_model.heuristic_score_and_reasons(combined)

    final_score = h_score if ml_score is None else max(h_score, ml_score)

    # === Multi-level classification ===
    if final_score < 0.3:
        final_label = "safe"
    elif final_score < 0.7:
        final_label = "suspicious"
    else:
        final_label = "high_alert"

    reasons = list(h_reasons) if h_reasons else []
    if ml_score is not None:
        reasons.append(f"ml_score:{ml_score:.3f}")
    if sender:
        reasons.append(f"sender:{sender}")

    return jsonify({
        "score": final_score,
        "risk_level": final_label,
        "reasons": reasons,
        "heuristic_score": h_score,
        "ml_score": ml_score
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
