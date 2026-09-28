import os
import time
import base64
import struct
import random
import json
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import nacl.secret
from curl_cffi import requests as curl_requests

# --- Configuration ---
# Use environment variables in Vercel for these
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-key-change-me-in-vercel-settings")
BASE_URL = os.getenv("BASE_URL", "https://vidlink.pro") # Example base, change as needed

# --- Crypto Helpers ---
def encrypt_token(token: str) -> str:
    try:
        key_bytes = base64.b64decode(ENCRYPTION_KEY)
        if len(key_bytes) != 32:
            # Simple padding or error handling if key is wrong length
            key_bytes = (key_bytes * 2)[:32]
        
        nonce = nacl.secret.SecretBox(key_bytes).generate_nonce()
        box = nacl.secret.SecretBox(key_bytes)
        encrypted = box.encrypt(token.encode('utf-8'), nonce)
        encrypted_with_nonce = nonce + encrypted
        return base64.b64encode(encrypted_with_nonce).decode('utf-8')
    except Exception:
        # Fallback for debugging if key is invalid
        return base64.b64encode(token.encode()).decode()

def decrypt_token(token: str) -> str:
    try:
        key_bytes = base64.b64decode(ENCRYPTION_KEY)
        if len(key_bytes) != 32:
            key_bytes = (key_bytes * 2)[:32]
            
        decoded = base64.b64decode(token)
        nonce = decoded[:24]
        box = nacl.secret.SecretBox(key_bytes)
        decrypted = box.decrypt(decoded, nonce)
        return decrypted.decode('utf-8')
    except Exception:
        try:
            return base64.b64decode(token).decode()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid token")

# --- FastAPI App ---
app = FastAPI(title="VidLink Pro API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def fetch_with_retry(url, headers=None, retries=3, delay=2):
    """Helper to fetch URL with retry logic using curl_cffi"""
    if headers is None:
        headers = {}
    
    # Add standard headers if not present
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    for i in range(retries):
        try:
            # Use curl_cffi for better anti-bot support
            resp = curl_requests.get(url, headers=headers, impersonate="chrome120", timeout=30)
            return resp
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(delay)

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VidLink Pro</title>
        <style>
            body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #111; color: white; }
            .container { text-align: center; }
            h1 { margin-bottom: 10px; }
            p { color: #aaa; }
            a { color: #00d2ff; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>VidLink Pro API</h1>
            <p>API is running. Visit /docs for Swagger UI.</p>
            <a href="/docs">API Docs</a>
        </div>
    </body>
    </html>
    """

@app.get("/encrypt/{token}")
async def encrypt_endpoint(token: str):
    try:
        encrypted = encrypt_token(token)
        return {"encrypted_token": encrypted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/decrypt/{token}")
async def decrypt_endpoint(token: str):
    try:
        decrypted = decrypt_token(token)
        return {"decrypted_token": decrypted}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/proxy")
async def proxy_stream(request: Request):
    """
    Proxies video/stream requests.
    Note: This is synchronous. For long streams, Vercel's 60s timeout might kill it 
    unless you use the "Edge" runtime or a dedicated VM (Fly.io).
    """
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")
    
    try:
        decrypted_token = decrypt_token(token)
        # Assume the token contains the full URL or path. 
        # If your token is just an ID, you need to map it here.
        # For this generic proxy, we assume the decrypted token IS the target URL.
        target_url = decrypted_token
        
        # Forward headers from the original request
        forwarded_headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ["host", "transfer-encoding", "connection", "keep-alive"]:
                forwarded_headers[key] = value
        
        # Fetch the stream
        resp = fetch_with_retry(target_url, headers=forwarded_headers)
        
        # Return streaming response
        return StreamingResponse(
            iter([chunk for chunk in resp.iter_bytes(chunk_size=8192)]),
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy Error: {str(e)}")

# Vercel Handler
handler = app
