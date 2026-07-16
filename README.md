# Instagram Media API

A professional, production-ready FastAPI service that extracts high-resolution photos, videos, and metadata from public Instagram posts, Reels, and IGTV videos. Built for serverless deployment on Vercel with browser impersonation to reduce blocking.

## Features

- Extract images and videos from Instagram posts, Reels, and carousels
- Author, username, title, and caption parsing
- Proxied media endpoint to avoid CORS/referer issues
- Pydantic request/response validation
- Structured logging and clear error responses
- CORS support
- Docker support for local development
- GitHub Actions CI pipeline (lint + test + Docker build)

## Live Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Landing page |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc documentation |
| `GET /api/health` | Health check |
| `GET /api/fetch?url=<instagram-url>` | Extract media and metadata |
| `GET /api/proxy?url=<media-url>` | Proxy a media file |

## Quick Start

### Local Development

```bash
# Clone the repository
git clone https://github.com/Mobius/instagram-media-api.git
cd instagram-media-api

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn api.index:app --reload
```

Visit `http://127.0.0.1:8000/docs` to test the API.

### Docker

```bash
docker build -t instagram-media-api .
docker run -p 8000:8000 instagram-media-api
```

### Example API Request

```bash
curl "https://your-domain.com/api/fetch?url=https://www.instagram.com/p/ABC123xyz/"
```

## Deployment

### Vercel

1. Install the Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Deploy:
   ```bash
   vercel --prod
   ```

The included `vercel.json` routes all traffic to `api/index.py`.

## Configuration

Configuration is loaded from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_TIMEOUT` | `20` | Timeout for Instagram page requests |
| `PROXY_TIMEOUT` | `30` | Timeout for media proxy requests |
| `IMPERSONATE_BROWSER` | `chrome120` | curl_cffi browser profile |
| `CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level |

## Project Structure

```
instagram-media-api/
├── api/
│   ├── __init__.py
│   ├── config.py          # Settings and environment variables
│   ├── extractor.py       # Instagram scraping logic
│   ├── index.py           # FastAPI entry point
│   └── models.py          # Pydantic schemas
├── tests/
│   ├── test_api.py
│   └── test_extractor.py
├── .github/
│   └── workflows/
│       └── ci.yml         # GitHub Actions CI
├── Dockerfile
├── LICENSE
├── README.md
├── pyproject.toml
├── requirements.txt
└── vercel.json
```

## Important Notes

- This API only works with **public** Instagram posts.
- Instagram's HTML structure may change, which can affect extraction reliability.
- Be respectful of Instagram's terms of service and rate limits.

## License

MIT License - see [LICENSE](LICENSE).
