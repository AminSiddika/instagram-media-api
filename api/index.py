"""FastAPI application entry point for Vercel serverless deployment."""

import logging
import secrets
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, Response
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
    log_request,
)

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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


def validate_origin_and_referer(request: Request):
    """Enforce Origin/Referer checks to protect the API from unauthorized hotlinking."""
    referer = request.headers.get("referer")
    origin = request.headers.get("origin")
    
    # Define allowed domains
    allowed_domains = ["instagram-media-api.vercel.app", "localhost", "127.0.0.1", "localhost:3000"]
    for org in settings.cors_origins_list:
        parsed_org = urlparse(org)
        if parsed_org.netloc:
            allowed_domains.append(parsed_org.netloc.lower())

    is_allowed = False
    
    # Check Referer
    if referer:
        ref_domain = urlparse(referer).netloc.lower()
        if any(dom in ref_domain for dom in allowed_domains):
            is_allowed = True
            
    # Check Origin
    if origin:
        orig_domain = urlparse(origin).netloc.lower()
        if any(dom in orig_domain for dom in allowed_domains):
            is_allowed = True
            
    # Only enforce if Origin or Referer is supplied (prevents browser extensions/third-party domains from abusing)
    if (referer or origin) and not is_allowed:
        raise HTTPException(
            status_code=403, 
            detail="Access forbidden: This domain/origin is not authorized to use this API."
        )


@app.exception_handler(ExtractionError)
async def extraction_error_handler(_: Any, exc: ExtractionError) -> JSONResponse:
    """Return a clean 400 response for extraction failures."""
    logger.warning("Extraction error: %s", exc)
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.get("/", include_in_schema=False)
async def root() -> Response:
    """Serve the upgraded landing page with direct fetch client and Mobius credits."""
    return Response(
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        },
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
        .thank-you {{
            margin-top: 2.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--surface-border);
            font-size: 0.85rem;
            color: var(--muted);
        }}
        .thank-you a {{
            color: var(--primary);
            text-decoration: none;
            font-weight: 600;
        }}
        .thank-you a:hover {{
            text-decoration: underline;
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
            <a href="/docs">Swagger UI Docs</a>
            <a href="/api/health">System Health</a>
        </div>

        <!-- Thank you section -->
        <div class="thank-you">
            Thank you for using our service! ❤️ Developed by <a href="https://t.me/JalebiBae" target="_blank">Mobius</a>
        </div>
    </div>

    <script>
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
                const response = await fetch(`/api/fetch?url=${{encodeURIComponent(postUrl)}}`);
                const data = await response.json();
                
                if (!response.ok) {{
                    throw new Error(data.detail || 'Extraction failed');
                }}
                
                statusDiv.style.display = 'none';
                grid.innerHTML = '';
                
                if (data.media && data.media.length > 0) {{
                    data.media.forEach((item, index) => {{
                        const card = document.createElement('div');
                        card.className = 'image-card';
                        
                        // Use proxy_url to bypass Instagram's CORS and hotlinking protections
                        const mediaUrl = item.proxy_url || item.url;
                        
                        if (item.type === 'video') {{
                            const video = document.createElement('video');
                            video.src = mediaUrl;
                            video.controls = true;
                            video.style.width = '100%';
                            video.style.height = '100%';
                            video.style.objectFit = 'cover';
                            card.appendChild(video);
                        }} else {{
                            const img = document.createElement('img');
                            img.src = mediaUrl;
                            img.alt = `Media ${{index + 1}}`;
                            card.appendChild(img);
                        }}
                        
                        const dl = document.createElement('button');
                        dl.className = 'dl-btn';
                        dl.innerHTML = '⬇️';
                        dl.onclick = () => window.open(mediaUrl, '_blank');
                        
                        card.appendChild(dl);
                        grid.appendChild(card);
                    }});
                    resContainer.style.display = 'block';
                }} else {{
                    statusDiv.style.display = 'block';
                    statusDiv.textContent = 'No media files returned.';
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
        examples=["https://www.instagram.com/p/ABC123xyz/"],
    ),
) -> InstagramPostResponse:
    """Fetch media URLs and metadata for a public Instagram post. Access is restricted to authorized origins/referers."""
    log_request(request, status="fetch_start")
    
    # Enforce Origin/Referer checks to protect the API from unauthorized hotlinking
    validate_origin_and_referer(request)

    # Extract post media
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
) -> Response:
    """Proxy an Instagram media file to avoid CORS and referer issues. Access is restricted to authorized origins/referers."""
    # Enforce Origin/Referer checks to protect the API from unauthorized hotlinking
    validate_origin_and_referer(request)

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
    ext = "mp4" if "video" in content_type.lower() else "jpg"
    return Response(
        content=response.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": f"attachment; filename=ig_media.{ext}"
        },
    )
