# dns_tunnel_lib/utils.py
import base64
import math




def chunk_bytes(data: bytes, chunk_size: int):
"""Yield chunks of `chunk_size` bytes from data."""
for i in range(0, len(data), chunk_size):
yield data[i:i+chunk_size]




def encode_chunk(chunk: bytes) -> str:
"""Return base64 encoded string (utf-8) of chunk."""
return base64.b64encode(chunk).decode('ascii')