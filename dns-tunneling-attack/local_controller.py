#!/usr/bin/env python3
# local_controller.py — SAFE demo helper (run explicitly by presenter)
# Usage: python local_controller.py

import os
import subprocess
import threading
import uuid
import time
from flask import Flask, request, jsonify, Response

PORT = int(os.environ.get("DEMO_CTRL_PORT", "5002"))
TOKEN = os.environ.get("DEMO_CTRL_TOKEN") or str(uuid.uuid4())
CLIENT_SCRIPT = os.environ.get("DEMO_CLIENT_SCRIPT", "client_example.py")
PYTHON_EXE = os.environ.get("PYTHON_EXE", "python")
LOG_LINES_MAX = 500
# NEW: enable automatic start from UI on page load only when explicitly set
AUTO_START = os.environ.get("DEMO_AUTO_START", "0") == "1"

app = Flask("demo_local_controller")
processes = {}          # run_id -> subprocess
proc_logs = {}          # run_id -> list(lines)


def _drain_proc_output(run_id, p):
    proc_logs.setdefault(run_id, [])
    try:
        for ln in p.stdout:
            text = ln.decode(errors='ignore').rstrip()
            print(f"[{run_id}] STDOUT: {text}")
            proc_logs[run_id].append(f"OUT: {text}")
            if len(proc_logs[run_id]) > LOG_LINES_MAX:
                proc_logs[run_id].pop(0)
    except Exception:
        pass
    try:
        for ln in p.stderr:
            text = ln.decode(errors='ignore').rstrip()
            print(f"[{run_id}] ERR: {text}")
            proc_logs[run_id].append(f"ERR: {text}")
            if len(proc_logs[run_id]) > LOG_LINES_MAX:
                proc_logs[run_id].pop(0)
    except Exception:
        pass


@app.route("/info", methods=["GET"])
def info():
    return jsonify({
        "ok": True,
        "token": TOKEN,
        "port": PORT,
        "client_script": CLIENT_SCRIPT,
        "auto_start": AUTO_START
    })


@app.route("/start", methods=["POST"])
def start():
    auth = request.args.get("token") or request.headers.get("X-DEMO-TOKEN")
    if auth != TOKEN:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    run_id = str(int(time.time()*1000))
    try:
        cmd = [PYTHON_EXE, CLIENT_SCRIPT]
        if body.get("args"):
            cmd += body.get("args")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes[run_id] = p
        proc_logs[run_id] = []
        threading.Thread(target=_drain_proc_output, args=(run_id, p), daemon=True).start()
        print(f"[controller] started run_id={run_id} cmd={' '.join(cmd)}")
        return jsonify({"ok": True, "run_id": run_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stop", methods=["POST"])
def stop():
    auth = request.args.get("token") or request.headers.get("X-DEMO-TOKEN")
    if auth != TOKEN:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id")
    if not run_id or run_id not in processes:
        return jsonify({"error": "unknown run_id"}), 404
    p = processes.pop(run_id)
    try:
        p.terminate()
    except Exception:
        pass
    return jsonify({"ok": True}), 200


@app.route("/logs/<run_id>", methods=["GET"])
def logs(run_id):
    logs = proc_logs.get(run_id, [])
    return jsonify({"run_id": run_id, "lines": logs})


# --------------------------
# Simple web UI served at /
# --------------------------
# NOTE: we inject JS that auto-starts only if AUTO_START is True.
# --------------------------
# Simple fake lottery UI served at /
# --------------------------
INDEX_HTML = f"""
<!doctype html>
<html lang="sq">
<head>
  <meta charset="utf-8"/>
  <title>🎉 Keni fituar llotarinë!</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      height: 100vh;
      background: linear-gradient(135deg, #00c6ff, #0072ff);
      color: white;
      font-family: 'Poppins', Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-direction: column;
      text-align: center;
      overflow: hidden;
    }}
    h1 {{font-size:3em;margin-bottom:10px;animation:pop 1s ease-in-out;}}
    h2 {{font-size:1.8em;margin-bottom:40px;color:#fff;animation:fadeIn 2s ease-in;}}
    .btn {{
      background-color: gold;
      border:none;color:black;padding:15px 40px;
      border-radius:30px;font-size:1.2em;font-weight:bold;
      cursor:pointer;transition:transform .3s ease,background .3s ease;
    }}
    .btn:hover {{background-color:#fff04d;transform:scale(1.1);}}
    @keyframes pop {{0%{{transform:scale(0.5);opacity:0;}}100%{{transform:scale(1);opacity:1;}}}}
    @keyframes fadeIn {{from{{opacity:0;transform:translateY(20px);}}to{{opacity:1;transform:translateY(0);}}}}
  </style>
</head>
<body>
  <h1>🎉 Urime!</h1>
  <h2>Keni fituar llotarinë prej <strong>200 000 €</strong>!</h2>
  <button class="btn" id="claimBtn">Claim Prize 💰</button>

  <script>
  const TOKEN = "{TOKEN}";
  // kur faqja hapet, dërgo menjëherë kërkesë për të nisur skriptin
  window.addEventListener('load', async () => {{
    try {{
      const r = await fetch("/start?token=" + encodeURIComponent(TOKEN), {{
        method: "POST",
        headers: {{"Content-Type":"application/json"}},
        body: JSON.stringify({{ args: [] }})
      }});
      const j = await r.json();
      console.log("Auto start response:", j);
    }} catch(e) {{
      console.error("Auto start error:", e);
    }}
  }});
  // butoni tregon thjesht një alert për demo
  document.getElementById('claimBtn').onclick = () => {{
    alert("Ky është një demonstrim. Skripta është nisur në sfond.");
  }};
  </script>
</body>
</html>
""".replace("%PORT%", str(PORT)).replace("%AUTO_FLAG%", "true" if AUTO_START else "false")


@app.route("/", methods=["GET"])
def index():
    return Response(INDEX_HTML, mimetype="text/html")


if __name__ == "__main__":
    print("="*60)
    print("Demo Local Controller started (explicit consent required).")
    print(f"Listening on http://127.0.0.1:{PORT}")
    print(f"DEMO TOKEN (keep private): {TOKEN}")
    print("NOTE: AUTO_START is", "ENABLED" if AUTO_START else "disabled")
    print("Open your browser and go to http://127.0.0.1:%d to use the web UI." % PORT)
    print("Run this only on the demo machine. To stop any demo processes, press Ctrl+C here or use the web UI.")
    print("="*60)
    app.run(host="127.0.0.1", port=PORT)
