from flask import Flask, request, jsonify
from flask_cors import CORS
from phish_model import heuristic_score_and_reasons, predict_text_ml

app = Flask(name)
CORS(app)

@app.route("/api/scan_text", methods=["POST"])
def scan_text():
    data = request.get_json() or {}
    subject = data.get("subject", "")
    body = data.get("body", "")
    ml = predict_text_ml(subject, body)
    ml_score = ml[0] if ml else None
    ml_label = ml[1] if ml else None

    combined = (subject + "\n" + body)[:5000]
    h_score, h_label, h_reasons = heuristic_score_and_reasons(combined)

    final_score = h_score if ml_score is None else max(h_score, ml_score)
    final_label = "phishing" if final_score >= 0.5 else "benign"
    reasons = h_reasons
    if ml_score is not None:
        reasons.append(f"ml_score:{ml_score:.3f}")

    return jsonify({
        "score": final_score,
        "label": final_label,
        "reasons": reasons,
        "heuristic_score": h_score,
        "ml_score": ml_score
    }), 200

if name == "main":
    app.run(host="0.0.0.0", port=5000, debug=True)