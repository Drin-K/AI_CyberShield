# client_example.py
import requests
import base64
import time
import uuid
import os

SERVER = os.environ.get("SIM_SERVER", "http://localhost:8053")
ENDPOINT = f"{SERVER}/api/sim/send_chunk"

def send_message(payload_bytes, chunk_size=100):
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
        resp = requests.post(ENDPOINT, json=data)
        print("Sent chunk", idx, "resp", resp.status_code, resp.text)
        time.sleep(0.15)

if __name__ == "__main__":
    text = ("Hello user, this is a normal message. " * 20).encode()
    print("Sending benign example...")
    send_message(text, chunk_size=200)

    import os
    rand = os.urandom(1200)
    print("Sending malicious-like example...")
    send_message(rand, chunk_size=80)
