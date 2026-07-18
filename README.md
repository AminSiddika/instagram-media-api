# Instagram Media API

A professional, production-ready FastAPI service that extracts high-resolution photos, videos, and metadata from public Instagram posts, Reels, and IGTV videos. Built for serverless deployment on Vercel with browser impersonation and proxy support to completely bypass Instagram's login wall and scraper blocking.

## Features

- **Media & Metadata Extraction**: Extract images, videos, captions, author details, and usernames from public posts and carousels.
- **Upgraded Landing Page**: Built-in interactive Web UI to fetch, view, and directly download media with ease.
- **Security Headers & Request ID Tracking**: Automatically appends essential security headers (`X-Frame-Options`, `X-Content-Type-Options`, etc.) and trace IDs.
- **Origin/Referer Protection**: Enforces strict origin and referer verification based on `CORS_ORIGINS` to protect your endpoint from unauthorized third-party hotlinking.
- **Zero API Keys Required**: Simplified client-facing interface protected by domain restriction rather than complex key rotations.
- **Built-in Proxy Support**: Easily routes requests through proxies to bypass IP-based scraping blocks.
- **Browser Impersonation**: Uses `curl_cffi` to mimic genuine TLS fingerprints (Chrome 120) to avoid detection.
- **Proxied Media Endpoint**: Access files directly via a `/api/proxy` endpoint to avoid CORS and media hotlinking block issues on client apps.

---

## Endpoints

| Endpoint | Method | Description | Auth / Security |
|----------|--------|-------------|-----------------|
| `/` | `GET` | Upgraded Interactive UI Webpage | No auth |
| `/docs` | `GET` | Swagger UI documentation | No auth |
| `/redoc` | `GET` | ReDoc documentation | No auth |
| `/api/health` | `GET` | Health check | No auth |
| `/api/fetch?url=<instagram-url>` | `GET` | Extract media & metadata | Origin/Referer Check |
| `/api/proxy?url=<media-url>` | `GET` | Proxy media contents to bypass CORS | Origin/Referer Check |

---

## Configuration

Settings are loaded via environment variables or fall back to defaults in `api/config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_TIMEOUT` | `20` | Timeout for fetching Instagram pages |
| `PROXY_TIMEOUT` | `30` | Timeout for media proxy requests |
| `IMPERSONATE_BROWSER` | `chrome120` | Browser profile for `curl_cffi` |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (enforced in fetch/proxy) |
| `PROXY_URL` | `http://rtxuydyo:ziapktcf4725@64.137.96.74:6641` | Default proxy to bypass Instagram login walls |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Hotlink Protection (Origin & Referer Check)

To prevent unauthorized domains from abusing your API, endpoints check incoming `Origin` and `Referer` headers. If these headers are supplied, the domain must match the allowed list defined in `CORS_ORIGINS`.

---

## Quick Start

### Local Development

1. **Clone & Setup**:
   ```bash
   git clone https://github.com/AminSiddika/instagram-media-api.git
   cd instagram-media-api
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run Server**:
   ```bash
   uvicorn api.index:app --reload
   ```
   Open `http://127.0.0.1:8000` to access the interactive web interface.

### Docker Support

```bash
docker build -t instagram-media-api .
docker run -p 8000:8000 instagram-media-api
```

---

## Deployment on Vercel

The repository is fully configured for serverless deployment on Vercel using the provided `vercel.json` configurations.

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```
2. **Deploy**:
   ```bash
   vercel --prod
   ```

---

## License

Released under the [MIT License](LICENSE).

