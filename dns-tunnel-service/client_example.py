# client_example.py
import requests
import uuid
from dns_tunnel_lib import chunk_bytes, encode_chunk


SERVER = 'http://localhost:8053'
CHUNK_SIZE = 1000 # bytes per chunk (tweak for tests)




def send_message(payload_bytes: bytes):
message_id = None
chunks = list(chunk_bytes(payload_bytes, CHUNK_SIZE))
total = len(chunks)


for idx, chunk in enumerate(chunks):
payload_b64 = encode_chunk(chunk)
data = {
'message_id': message_id, # None for first request to get an id
'chunk_index': idx,
'total_chunks': total,
'payload_b64': payload_b64
}
resp = requests.post(SERVER + '/api/sim/send_chunk', json=data)
if resp.status_code in (200, 202):
j = resp.json()
message_id = j.get('message_id')
print(f"Sent chunk {idx+1}/{total}, server status: {j.get('status')}")
else:
print('Error from server:', resp.status_code, resp.text)
return None


# poll for completion (optional)
if message_id:
status = requests.get(SERVER + f'/api/sim/status/{message_id}').json()
print('final status:', status)
# fetch reconstruct endpoint
rec = requests.get(SERVER + f'/api/sim/reconstruct/{message_id}')
print('reconstruct status:', rec.status_code, rec.text)




if __name__ == '__main__':
sample = b'This is a demo payload for the dns-tunnel mock. ' * 20
send_message(sample)