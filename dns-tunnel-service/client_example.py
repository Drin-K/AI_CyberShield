# client_example_debug.py
import requests
import base64
import time
import uuid
import os
from requests.exceptions import RequestException, ConnectionError, Timeout

SERVER = os.environ.get("SIM_SERVER", "http://127.0.0.1:8053")
ENDPOINT = f"{SERVER.rstrip('/')}/api/sim/send_chunk"

def send_message(payload_bytes, chunk_size=100, max_attempts=3):
    message_id = str(uuid.uuid4())
    chunks = [payload_bytes[i:i+chunk_size] for i in range(0, len(payload_bytes), chunk_size)]
    total = len(chunks)
    for idx, c in enumerate(chunks):
        b64 = base64.b64encode(c).decode()
        data = {
            "message_id": message_id,
            "chunk_index": idx,
            "total_chunks": total,
            "payload_b64": b64,
            "client_id": "dev-42",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                resp = requests.post(ENDPOINT, json=data, timeout=6)
                print(f"[chunk {idx}] attempt {attempt} -> status {resp.status_code}")
                # print small preview only for debugging, avoid huge outputs
                print("  resp preview:", (resp.text or "")[:300])
                break
            except (ConnectionError, Timeout) as e:
                print(f"[chunk {idx}] attempt {attempt} -> connection error/timeout: {e}")
                if attempt >= max_attempts:
                    print(f"[chunk {idx}] failed after {max_attempts} attempts, aborting message send")
                    return
                time.sleep(0.5 * attempt)
            except RequestException as e:
                print(f"[chunk {idx}] attempt {attempt} -> request exception: {e}")
                return

        # small inter-chunk delay to simulate real traffic
        time.sleep(0.15)

if __name__ == "__main__":
    print("SIM_SERVER:", SERVER)
    # quick health check
    try:
        h = requests.get(f"{SERVER.rstrip('/')}/health", timeout=3)
        print("health:", h.status_code, h.text[:200])
    except Exception as e:
        print("health check failed:", e)

    text = ("Hello user, this is a normal message. " * 20).encode()
    print("Sending benign example...")
    send_message(text, chunk_size=200)

    import os
    rand = os.urandom(1200)
    print("Sending malicious-like example...")
    send_message(rand, chunk_size=80)
