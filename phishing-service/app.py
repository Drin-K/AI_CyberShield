from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/api/scan_text", methods=["POST"])
def scan_text():
    data = request.get_json() or {}
    subject = data.get("subject", "").lower()
    body = data.get("body", "").lower()
    reasons = []
    score = 0.0

    # Shembull i thjeshtë heuristik
    if "verify" in body or "confirm" in body:
        reasons.append("contains suspicious token(s): verify/confirm")
        score += 0.4
    if "password" in body or "bank" in body:
        reasons.append("contains credential-related word(s)")
        score += 0.4
    if "http://" in body or "https://" in body:
        reasons.append("contains URL")
        score += 0.2

    label = "phishing" if score >= 0.5 else "benign"
    return jsonify({
        "label": label,
        "score": score,
        "reasons": reasons or ["no suspicious indicators"]
    })

@app.route("/")
def home():
    return "PhishDetect backend running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
