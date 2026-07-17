"""FastAPI application entry point for Vercel serverless deployment."""

import logging
import secrets
import time
import hmac
import hashlib
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from api.config import get_settings
from api.extractor import ExtractionError, extract_instagram_post
from api.models import (
    ErrorResponse,
    HealthResponse,
    InstagramPostResponse,
)
from api.security import (
    is_private_ip,
    log_request,
)

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Server-side ephemeral secret for session validation (regenerated on startup/instance spin-up)
SERVER_SECRET = secrets.token_hex(32)

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add request ID and security headers to every response."""
    request_id = request.headers.get("x-request-id") or secrets.token_hex(8)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if "server" in response.headers:
        del response.headers["server"]
    return response


@app.exception_handler(ExtractionError)
async def extraction_error_handler(_: Any, exc: ExtractionError) -> JSONResponse:
    """Return a clean 400 response for extraction failures."""
    logger.warning("Extraction error: %s", exc)
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    """Serve a landing page that auto-generates the X-Temp-Token and fetches media."""
    timestamp = str(int(time.time()))
    sig = hmac.new(SERVER_SECRET.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    temp_token = f"{sig}.{timestamp}"

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{settings.app_name}</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0813;
            --surface: rgba(255, 255, 255, 0.03);
            --surface-border: rgba(255, 255, 255, 0.08);
            --text: #f3f0ff;
            --muted: #9f9ba8;
            --primary: #f27b54;
            --accent: #8b5cf6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Plus Jakarta Sans', sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 2rem 1rem;
            overflow-x: hidden;
        }}
        .container {{
            width: 100%;
            max-width: 640px;
            background: var(--surface);
            border: 1px solid var(--surface-border);
            backdrop-filter: blur(16px);
            border-radius: 24px;
            padding: 2.5rem;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
            text-align: center;
        }}
        h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 0%, var(--muted) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        .subtitle {{
            color: var(--muted);
            font-size: 0.95rem;
            margin-bottom: 2rem;
            line-height: 1.6;
        }}
        .form-group {{
            margin-bottom: 1.25rem;
            text-align: left;
        }}
        label {{
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: var(--text);
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        input {{
            width: 100%;
            padding: 0.9rem 1.2rem;
            background: rgba(0,0,0,0.2);
            border: 1px solid var(--surface-border);
            border-radius: 12px;
            color: white;
            font-family: inherit;
            font-size: 0.95rem;
            transition: all 0.2s ease;
        }}
        input:focus {{
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(242, 123, 84, 0.15);
        }}
        .btn {{
            width: 100%;
            padding: 1rem;
            background: linear-gradient(135deg, var(--primary) 0%, #e15f34 100%);
            border: none;
            border-radius: 12px;
            color: white;
            font-family: inherit;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-top: 0.5rem;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(242, 123, 84, 0.3);
        }}
        .btn:active {{ transform: translateY(0); }}
        .result-container {{
            margin-top: 2rem;
            border-top: 1px solid var(--surface-border);
            padding-top: 2rem;
            display: none;
        }}
        .image-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }}
        .image-card {{
            position: relative;
            aspect-ratio: 1;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--surface-border);
            transition: transform 0.2s ease;
        }}
        .image-card:hover {{
            transform: scale(1.05);
        }}
        .image-card img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .dl-btn {{
            position: absolute;
            bottom: 8px;
            right: 8px;
            background: rgba(0,0,0,0.7);
            border: none;
            padding: 6px;
            border-radius: 50%;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .links-row {{
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 2rem;
            font-size: 0.85rem;
        }}
        .links-row a {{
            color: var(--muted);
            text-decoration: none;
            transition: color 0.2s;
        }}
        .links-row a:hover {{ color: white; }}
        .status {{
            margin-top: 1rem;
            font-size: 0.9rem;
            color: var(--primary);
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{settings.app_name}</h1>
        <p class="subtitle">Extract and download high-resolution Instagram carousel media automatically.</p>

        <!-- Input Form -->
        <div class="form-group">
            <label for="postUrl">Instagram URL</label>
            <input type="text" id="postUrl" placeholder="https://www.instagram.com/p/DabIUkpEzAV/">
        </div>
        <button class="btn" onclick="fetchMedia()">Fetch Images</button>
        <div id="status" class="status"></div>

        <!-- Results Grid -->
        <div id="resultContainer" class="result-container">
            <h3 style="text-align: left; font-weight: 600;">Media Extracted</h3>
            <div id="imageGrid" class="image-grid"></div>
        </div>

        <div class="links-row">
            <a href="/docs">OpenAPI Docs</a>
            <a href="/api/health">System Health</a>
        </div>
    </div>

    <script>
        // Temporary session token auto-injected by server
        const sessionToken = "{temp_token}";

        async function fetchMedia() {{
            const postUrl = document.getElementById('postUrl').value.trim();
            const statusDiv = document.getElementById('status');
            const grid = document.getElementById('imageGrid');
            const resContainer = document.getElementById('resultContainer');

            if (!postUrl) {{
                alert('Please enter an Instagram post URL.');
                return;
            }}
            
            statusDiv.style.display = 'block';
            statusDiv.textContent = 'Fetching media from server...';
            resContainer.style.display = 'none';

            try {{
                const response = await fetch(`/api/fetch?url=${{encodeURIComponent(postUrl)}}`, {{
                    headers: {{
                        'X-Temp-Token': sessionToken
                    }}
                }});
                const data = await response.json();
                
                if (!response.ok) {{
                    throw new Error(data.detail || 'Extraction failed');
                }}
                
                statusDiv.style.display = 'none';
                grid.innerHTML = '';
                
                if (data.media && data.media.length > 0) {{
                    data.media.forEach((item, index) => {{
                        if (item.type === 'photo') {{
                            const card = document.createElement('div');
                            card.className = 'image-card';
                            
                            const img = document.createElement('img');
                            img.src = item.url;
                            img.alt = `Media ${{index + 1}}`;
                            
                            const dl = document.createElement('button');
                            dl.className = 'dl-btn';
                            dl.innerHTML = '⬇️';
                            dl.onclick = () => window.open(item.url, '_blank');
                            
                            card.appendChild(img);
                            card.appendChild(dl);
                            grid.appendChild(card);
                        }}
                    }});
                    resContainer.style.display = 'block';
                }} else {{
                    statusDiv.style.display = 'block';
                    statusDiv.textContent = 'No images returned in post.';
                }}

            }} catch (error) {{
                statusDiv.style.display = 'block';
                statusDiv.textContent = `Error: ${{error.message}}`;
            }}
        }}
    </script>
</body>
</html>"""
    )


@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Monitoring"],
)
async def health_check(request: Request) -> HealthResponse:
    """Return API health status."""
    log_request(request, status="health")
    return HealthResponse(status="ok", version=settings.app_version)


@app.get(
    "/api/fetch",
    response_model=InstagramPostResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Extract Instagram media",
    tags=["Extraction"],
)
async def fetch_media(
    request: Request,
    url: str = Query(
        ...,
        description="Public Instagram post, Reel, or IGTV URL",
        examples=["https://www.instagram.com/p/DabIUkpEzAV/"],
    ),
    x_temp_token: Optional[str] = Header(None, alias="X-Temp-Token"),
) -> InstagramPostResponse:
    """Fetch media URLs and metadata for a public Instagram post. Requires a valid ephemeral X-Temp-Token."""
    log_request(request, status="fetch_start")
    
    # 1. Validate X-Temp-Token header
    if not x_temp_token or "." not in x_temp_token:
        raise HTTPException(status_code=403, detail="Unauthorized: Session token missing or malformed.")
        
    sig, timestamp_str = x_temp_token.split(".", 1)
    
    # 2. Check if token expired (tokens expire after 10 minutes)
    try:
        ts = int(timestamp_str)
        if abs(int(time.time()) - ts) > 600:
            raise HTTPException(status_code=403, detail="Unauthorized: Session token expired.")
    except ValueError:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid session timestamp.")
        
    # 3. Validate signature
    expected_sig = hmac.new(SERVER_SECRET.encode(), timestamp_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=403, detail="Unauthorized: Session signature verification failed.")

    # 4. Extract post media
    try:
        result = extract_instagram_post(url, settings)
        log_request(request, status="fetch_ok")
        return result
    except ExtractionError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during extraction")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the request.",
        ) from exc


@app.get(
    "/api/proxy",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Proxy a media file",
    tags=["Extraction"],
)
async def proxy_media(
    request: Request,
    url: str = Query(
        ...,
        description="Direct URL of the media file to proxy",
    ),
    x_temp_token: Optional[str] = Header(None, alias="X-Temp-Token"),
) -> Response:
    """Proxy an Instagram media file to avoid CORS and referer issues. Requires a valid ephemeral X-Temp-Token."""
    # 1. Validate X-Temp-Token header
    if not x_temp_token or "." not in x_temp_token:
        raise HTTPException(status_code=403, detail="Unauthorized: Session token missing or malformed.")
        
    sig, timestamp_str = x_temp_token.split(".", 1)
    
    try:
        ts = int(timestamp_str)
        if abs(int(time.time()) - ts) > 600:
            raise HTTPException(status_code=403, detail="Unauthorized: Session token expired.")
    except ValueError:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid session timestamp.")
        
    expected_sig = hmac.new(SERVER_SECRET.encode(), timestamp_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=403, detail="Unauthorized: Session signature verification failed.")

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme.")

    try:
        from curl_cffi import requests as cf

        response = cf.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            impersonate=settings.impersonate_browser,
            timeout=settings.proxy_timeout,
        )
    except Exception as exc:
        logger.exception("Proxy request failed")
        raise HTTPException(
            status_code=500, detail="Failed to proxy media."
        ) from exc

    content_type = response.headers.get("content-type", "application/octet-stream")
    return Response(
        content=response.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )
