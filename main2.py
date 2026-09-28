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

app = FastAPI(title="VidLink Pro API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

KEY_HEX = "c75136c5668bbfe65a7ecad431a745db68b5f381555b38d8f6c699449cf11fcd"
KEY = bytes.fromhex(KEY_HEX)
BOX = nacl.secret.SecretBox(KEY)
NONCE = bytes(24)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'Origin': 'https://vidlink.pro',
    'Referer': 'https://vidlink.pro/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Cache for stream URLs
stream_cache = {}

def encrypt_token(media_id: str):
    timestamp = int(time.time() + 480)
    message = media_id.encode("utf-8") + struct.pack(">Q", timestamp)
    encrypted = BOX.encrypt(message, NONCE)
    full_payload = NONCE + encrypted.ciphertext
    return base64.urlsafe_b64encode(full_payload).decode("utf-8").rstrip("=")

def fetch_with_retry(url: str, max_retries: int = 3):
    """Fetch API with retry logic"""
    for attempt in range(max_retries):
        try:
            response = curl_requests.get(
                url, 
                headers=DEFAULT_HEADERS, 
                impersonate="chrome110",
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            
            if response.status_code == 429:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"429 rate limited, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue
            
            raise HTTPException(status_code=response.status_code, detail=f"Upstream error: {response.status_code}")
            
        except HTTPException:
            raise
        except Exception as e:
            if attempt == max_retries - 1:
                raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")
            time.sleep(2 ** attempt)
    
    raise HTTPException(status_code=429, detail="Rate limited by VidLink")

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VidLink Pro API</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@300;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: #0a0a0c;
                --card-bg: rgba(255, 255, 255, 0.03);
                --accent: #3b82f6;
                --text: #ffffff;
                --text-dim: #94a3b8;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                overflow: hidden;
            }
            .glow {
                position: absolute;
                width: 600px;
                height: 600px;
                background: radial-gradient(circle, rgba(59, 130, 246, 0.08) 0%, transparent 70%);
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                z-index: -1;
                pointer-events: none;
            }
            .container {
                max-width: 800px;
                width: 90%;
                background: var(--card-bg);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 24px;
                padding: 40px;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            }
            h1 {
                font-family: 'Outfit', sans-serif;
                font-size: 2.5rem;
                margin-bottom: 12px;
                background: linear-gradient(to right, #fff, #94a3b8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            p.desc {
                color: var(--text-dim);
                margin-bottom: 32px;
                font-weight: 300;
            }
            .endpoints {
                text-align: left;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 16px;
                padding: 24px;
                margin-bottom: 32px;
            }
            .endpoint {
                margin-bottom: 24px;
            }
            .endpoint:last-child { margin-bottom: 0; }
            .label {
                font-family: 'Outfit', sans-serif;
                font-weight: 600;
                color: var(--accent);
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 8px;
                display: block;
            }
            .info {
                color: var(--text-dim);
                font-size: 0.85rem;
                margin-bottom: 8px;
                font-weight: 300;
            }
            .path {
                font-family: monospace;
                background: rgba(255, 255, 255, 0.05);
                padding: 10px 14px;
                border-radius: 8px;
                display: block;
                word-break: break-all;
                color: #e2e8f0;
                margin-bottom: 12px;
                font-size: 0.9rem;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: var(--accent);
                color: #000;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 0.9rem;
                transition: all 0.2s;
                font-family: 'Outfit', sans-serif;
            }
            .btn:hover {
                filter: brightness(1.2);
                transform: translateY(-1px);
            }
            .footer {
                position: absolute;
                bottom: 40px;
                left: 50%;
                transform: translateX(-50%);
                font-family: 'Outfit', sans-serif;
                font-weight: 300;
                letter-spacing: 2px;
                color: var(--text-dim);
                opacity: 0.6;
                font-size: 0.8rem;
            }
            .accent-text { color: var(--accent); font-weight: 600; }
        </style>
    </head>
    <body>
        <div class="glow"></div>
        <div class="container">
            <h1>VidLink Pro Generator</h1>
            <p class="desc">Encrypted Stream Acquisition with Video Proxy.</p>
            
            <div class="endpoints">
                <div class="endpoint">
                    <span class="label">Movie Endpoint</span>
                    <p class="info">Get stream URLs (proxied for playback).</p>
                    <span class="path">/movie/{tmdb_id}</span>
                    <a href="/movie/533535" target="_blank" class="btn">Test Movie Endpoint</a>
                </div>

                <div class="endpoint">
                    <span class="label">TV Endpoint</span>
                    <p class="info">Get TV episode stream URLs.</p>
                    <span class="path">/tv/{tmdb_id}/{season}/{episode}</span>
                    <a href="/tv/105248/1/1" target="_blank" class="btn">Test TV Endpoint</a>
                </div>

                <div class="endpoint">
                    <span class="label">Video Proxy</span>
                    <p class="info">Proxy video streams to bypass CORS/referer checks.</p>
                    <span class="path">/proxy?url={encoded_url}&referer={referer}</span>
                </div>
            </div>
        </div>
        <div class="footer">
            Developer: <span class="accent-text">Walter</span>
        </div>
    </body>
    </html>
    """

@app.get("/movie/{movie_id}")
async def get_movie(movie_id: str):
    cache_key = f"movie:{movie_id}"
    if cache_key in stream_cache:
        cached_time, cached_data = stream_cache[cache_key]
        if time.time() - cached_time < 3600:  # 1 hour cache
            return cached_data
    
    token = encrypt_token(movie_id)
    url = f"https://vidlink.pro/api/b/movie/{token}?multiLang=1"
    
    data = fetch_with_retry(url)
    
    if not data:
        raise HTTPException(status_code=404, detail="No source found")
    
    # Rewrite stream URLs to use our proxy
    processed_data = process_stream_data(data)
    stream_cache[cache_key] = (time.time(), processed_data)
    
    return processed_data

@app.get("/tv/{tv_id}/{season}/{episode}")
async def get_tv(tv_id: str, season: int, episode: int):
    cache_key = f"tv:{tv_id}:{season}:{episode}"
    if cache_key in stream_cache:
        cached_time, cached_data = stream_cache[cache_key]
        if time.time() - cached_time < 3600:
            return cached_data
    
    token = encrypt_token(tv_id)
    url = f"https://vidlink.pro/api/b/tv/{token}/{season}/{episode}?multiLang=1"
    
    data = fetch_with_retry(url)
    
    if not data:
        raise HTTPException(status_code=404, detail="No source found")
    
    processed_data = process_stream_data(data)
    stream_cache[cache_key] = (time.time(), processed_data)
    
    return processed_data

def process_stream_data(data: dict) -> dict:
    """Rewrite stream URLs to use our proxy"""
    import urllib.parse
    
    if "stream" in data and "qualities" in data["stream"]:
        for quality, stream_info in data["stream"]["qualities"].items():
            if "url" in stream_info:
                original_url = stream_info["url"]
                referer = stream_info.get("headers", {}).get("referer", "https://filmboom.top/")
                
                # Encode URL for proxy
                encoded_url = urllib.parse.quote(original_url, safe='')
                encoded_referer = urllib.parse.quote(referer, safe='')
                
                # Replace with proxied URL
                proxy_url = f"/proxy?url={encoded_url}&referer={encoded_referer}"
                stream_info["url"] = proxy_url
                stream_info["proxied"] = True
                
                # Remove requiresProxy flag since we handle it
                if "requiresProxy" in stream_info:
                    stream_info["requiresProxy"] = False
    
    return data

@app.get("/proxy")
async def proxy_video(url: str, referer: str = "https://filmboom.top/"):
    """Proxy video streams with proper headers"""
    import urllib.parse
    
    # Decode URL
    decoded_url = urllib.parse.unquote(url)
    decoded_referer = urllib.parse.unquote(referer)
    
    # Headers to mimic browser request
    video_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Referer': decoded_referer,
        'Origin': decoded_referer.rstrip('/'),
        'Accept': '*/*',
        'Accept-Encoding': 'identity',  # Don't compress video
        'Connection': 'keep-alive',
        'Range': 'bytes=0-',  # Support seeking
    }
    
    try:
        # Stream the video
        req = requests.get(
            decoded_url,
            headers=video_headers,
            stream=True,
            timeout=30,
            allow_redirects=True
        )
        
        if req.status_code not in [200, 206]:
            raise HTTPException(status_code=req.status_code, detail=f"Upstream video error: {req.status_code}")
        
        # Forward important headers
        response_headers = {}
        for header in ['Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'Cache-Control']:
            if header in req.headers:
                response_headers[header] = req.headers[header]
        
        # Ensure content type is correct
        if 'Content-Type' not in response_headers:
            response_headers['Content-Type'] = 'video/mp4'
        
        # Return streaming response
        return StreamingResponse(
            req.iter_content(chunk_size=8192),
            status_code=req.status_code,
            headers=response_headers,
            media_type=response_headers.get('Content-Type', 'video/mp4')
        )
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Video proxy error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/proxy-segment")
async def proxy_segment(url: str, referer: str = "https://filmboom.top/"):
    """Proxy video segments (for HLS/DASH if needed)"""
    import urllib.parse
    
    decoded_url = urllib.parse.unquote(url)
    decoded_referer = urllib.parse.unquote(referer)
    
    video_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Referer': decoded_referer,
        'Origin': decoded_referer.rstrip('/'),
    }
    
    try:
        req = requests.get(decoded_url, headers=video_headers, timeout=30)
        
        if req.status_code != 200:
            raise HTTPException(status_code=req.status_code)
        
        return Response(
            content=req.content,
            status_code=200,
            headers={
                'Content-Type': req.headers.get('Content-Type', 'application/octet-stream'),
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'public, max-age=3600'
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Segment proxy error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
