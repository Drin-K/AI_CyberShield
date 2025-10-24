# dns_tunnel_lib/tunnel.py
import base64
import math
from collections import Counter

def decode_payload_b64(b64: str) -> bytes:
    try:
        return base64.b64decode(b64)
    except Exception:
        return b''

def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    cnt = Counter(data)
    probs = [v / len(data) for v in cnt.values()]
    return -sum(p * (math.log2(p) if p>0 else 0) for p in probs)

def extract_features_from_chunks(chunks: list):
    """
    chunks: list of dicts with keys:
      - payload_b64 (str)
      - chunk_index (int)
      - timestamp (optional ISO string)
      - client_id (optional)
    returns: (features_dict, reassembled_bytes)
    """
    import statistics
    times = []
    sizes = []
    raws = []
    for c in chunks:
        payload = decode_payload_b64(c.get("payload_b64",""))
        raws.append(payload)
        sizes.append(len(payload))
        ts = c.get("timestamp")
        if ts:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(ts.replace("Z","+00:00"))
                times.append(dt.timestamp())
            except Exception:
                pass

    chunk_count = len(chunks)
    avg_chunk_size = float(statistics.mean(sizes)) if sizes else 0.0
    std_chunk_size = float(statistics.pstdev(sizes)) if sizes else 0.0
    total_bytes = sum(sizes)

    interarrival_mean = 0.0
    duration = 0.0
    if len(times) >= 2:
        times_sorted = sorted(times)
        diffs = [times_sorted[i+1]-times_sorted[i] for i in range(len(times_sorted)-1)]
        interarrival_mean = float(statistics.mean(diffs)) if diffs else 0.0
        duration = times_sorted[-1] - times_sorted[0]

    reassembled = b"".join(raws)
    entropy = shannon_entropy(reassembled)
    printable = sum(1 for b in reassembled if 32 <= b <= 126)
    printable_ratio = (printable / len(reassembled)) if reassembled else 0.0

    features = {
        "chunk_count": chunk_count,
        "avg_chunk_size": avg_chunk_size,
        "std_chunk_size": std_chunk_size,
        "total_bytes": total_bytes,
        "interarrival_mean": interarrival_mean,
        "duration": duration,
        "entropy": entropy,
        "printable_ratio": printable_ratio
    }
    return features, reassembled
