# server.py
import base64
import uuid
import time
import logging
from flask import Flask, request, jsonify
from threading import Lock

app = Flask(__name__)
LOCK = Lock()
MESSAGES = {}

@app.route('/api/sim/send_chunk', methods=['POST'])
def send_chunk():
    """
    Accepts JSON:
    {
        "message_id": "<id>" or null to request new id,
        "chunk_index": 0,
        "total_chunks": 3,
        "payload_b64": "<base64 string>"
    }
    """
    data = request.get_json() or {}
    mid = data.get('message_id')
    idx = data.get('chunk_index')
    total = data.get('total_chunks')
    payload_b64 = data.get('payload_b64')

    # Basic validation
    if payload_b64 is None:
        return jsonify({'error': 'missing payload_b64'}), 400
    if idx is None or total is None:
        return jsonify({'error': 'chunk_index and total_chunks required'}), 400

    # If client asks for a new message_id
    if not mid:
        mid = str(uuid.uuid4())

    try:
        raw = base64.b64decode(payload_b64)
    except Exception as e:
        return jsonify({'error': 'invalid base64', 'detail': str(e)}), 400

    with LOCK:
        info = MESSAGES.setdefault(
            mid, {'chunks': {}, 'total': int(total), 'last_seen': time.time()})
        info['chunks'][int(idx)] = raw
        info['last_seen'] = time.time()

    logging.info(f"Received chunk {idx + 1}/{total} for message {mid}")

    # If complete -> reassemble and return full payload (base64)
    if len(info['chunks']) == info['total']:
        parts = [info['chunks'][i] for i in range(info['total'])]
        full = b''.join(parts)
        reconstructed_b64 = base64.b64encode(full).decode()
        # optional: remove from store after reconstruction
        del MESSAGES[mid]
        return jsonify({
            'status': 'complete',
            'message_id': mid,
            'reconstructed_b64': reconstructed_b64
        }), 200

    return jsonify({
        'status': 'received',
        'message_id': mid,
        'received_chunks': len(info['chunks'])
    }), 202


@app.route('/api/sim/status/<message_id>', methods=['GET'])
def status(message_id):
    with LOCK:
        info = MESSAGES.get(message_id)
        if not info:
            return jsonify({'status': 'not_found'}), 404
        return jsonify({
            'status': 'in_progress',
            'received_chunks': len(info['chunks']),
            'total': info['total']
        }), 200


@app.route('/api/sim/reconstruct/<message_id>', methods=['GET'])
def reconstruct(message_id):
    """Return reconstructed base64 if the message is complete. (Optional endpoint)"""
    with LOCK:
        info = MESSAGES.get(message_id)
        if not info:
            return jsonify({'status': 'not_found'}), 404
        if len(info['chunks']) != info['total']:
            return jsonify({
                'status': 'incomplete',
                'received_chunks': len(info['chunks']),
                'total': info['total']
            }), 202
        parts = [info['chunks'][i] for i in range(info['total'])]
        full = b''.join(parts)
        reconstructed_b64 = base64.b64encode(full).decode()
        return jsonify({
            'status': 'complete',
            'message_id': message_id,
            'reconstructed_b64': reconstructed_b64
        }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8053, debug=True)
