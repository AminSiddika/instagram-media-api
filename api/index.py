"""FastAPI application entry point for Vercel serverless deployment."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from api.config import get_settings
from api.extractor import ExtractionError, extract_instagram_post
from api.models import ErrorResponse, HealthResponse, InstagramPostResponse

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


@app.exception_handler(ExtractionError)
async def extraction_error_handler(_: Any, exc: ExtractionError) -> JSONResponse:
    """Return a clean 400/500 response for extraction failures."""
    logger.warning("Extraction error: %s", exc)
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    """Serve a friendly landing page."""
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{settings.app_name}</title>
    <style>
        :root {{
            --bg: #0f0c19;
            --text: #f3f0ff;
            --muted: #8f8aa3;
            --accent: #e6683c;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            text-align: center;
            padding: 2rem;
        }}
        .container {{ max-width: 520px; }}
        h1 {{ font-size: 2.5rem; margin-bottom: 1rem; }}
        p {{ color: var(--muted); line-height: 1.6; margin-bottom: 1.5rem; }}
        .links {{ display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }}
        a {{
            color: var(--text);
            text-decoration: none;
            border: 1px solid rgba(255,255,255,0.12);
            padding: 0.6rem 1.2rem;
            border-radius: 999px;
            transition: all 0.2s ease;
        }}
        a:hover {{ background: white; color: var(--bg); border-color: white; }}
        .version {{ color: var(--accent); font-weight: 600; font-size: 0.85rem; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 2rem; display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{settings.app_name}</h1>
        <p>{settings.app_description}</p>
        <div class="links">
            <a href="/docs">Swagger UI</a>
            <a href="/redoc">ReDoc</a>
            <a href="/api/health">Health</a>
        </div>
        <span class="version">v{settings.app_version}</span>
    </div>
</body>
</html>"""
    )


@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Monitoring"],
)
async def health_check() -> HealthResponse:
    """Return API health status."""
    return HealthResponse(status="ok", version=settings.app_version)


@app.get(
    "/api/fetch",
    response_model=InstagramPostResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Extract Instagram media",
    tags=["Extraction"],
)
async def fetch_media(
    url: str = Query(
        ...,
        description="Public Instagram post, Reel, or IGTV URL",
        examples=["https://www.instagram.com/p/ABC123xyz/"],
    )
) -> InstagramPostResponse:
    """Fetch media URLs and metadata for a public Instagram post."""
    try:
        return extract_instagram_post(url, settings)
    except ExtractionError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during extraction")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {exc}",
        ) from exc


@app.get(
    "/api/proxy",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Proxy a media file",
    tags=["Extraction"],
)
async def proxy_media(
    url: str = Query(
        ...,
        description="Direct URL of the media file to proxy",
    )
) -> Response:
    """Proxy an Instagram media file to avoid CORS and referer issues."""
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
            status_code=500, detail=f"Failed to proxy media: {exc}"
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
