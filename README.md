# Instagram Media API

A professional, production-ready FastAPI service that extracts high-resolution photos, videos, and metadata from public Instagram posts, Reels, and IGTV videos. Built for serverless deployment on Vercel with browser impersonation to reduce blocking.

## Features

- Extract images and videos from Instagram posts, Reels, and carousels
- Author, username, title, and caption parsing
- Proxied media endpoint to avoid CORS/referer issues
- **AES-encrypted API keys with expiry**
- **Single-use rolling keys: a new key is issued after every request**
- **Static master key for owner/admin access (no expiry)**
- **Per-key/IP rate limiting and brute-force protection**
- **Security headers, request ID tracking, and sanitized logging**
- Pydantic request/response validation
- Structured logging and clear error responses
- CORS support
- Docker support for local development
- GitHub Actions CI pipeline (lint + test + Docker build)

## Live Endpoints

| Endpoint | Description | Auth |
|----------|-------------|------|
| `GET /` | Landing page | No |
| `GET /docs` | Swagger UI | No |
| `GET /redoc` | ReDoc documentation | No |
| `GET /api/health` | Health check | No |
| `POST /api/auth/issue-key` | Issue encrypted API key | Master key |
| `GET /api/auth/verify-key` | Verify API key | Any key |
| `GET /api/fetch?url=<instagram-url>` | Extract media and metadata | API key |
| `GET /api/proxy?url=<media-url>` | Proxy a media file | API key |

## Quick Start

### Local Development

```bash
# Clone the repository
git clone https://github.com/AminSiddika/instagram-media-api.git
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

#### Example Response

```json
{
  "shortcode": "Da5hgKLj4yQ",
  "input_url": "https://www.instagram.com/p/Da5hgKLj4yQ/",
  "type": "carousel",
  "title": "Tasfiya on Instagram: \"বদলায় তো সবকিছু আমরা শুধু 'সময়'কে দোষ দিই 💔\"",
  "author": "Tasfiya",
  "username": "tasfiya4599",
  "caption": "বদলায় তো সবকিছু আমরা শুধু 'সময়'কে দোষ দিই 💔",
  "media_count": 5,
  "media": [
    {
      "type": "photo",
      "url": "https://scontent.cdninstagram.com/v/...",
      "proxy_url": "/api/proxy?url=https%3A//scontent.cdninstagram.com/v/..."
    }
  ]
}
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
| `AES_KEY` | — | Base64-encoded AES key (16/24/32 bytes) |
| `MASTER_API_KEY` | — | Static owner key; never expires |
| `DEFAULT_KEY_TTL_HOURS` | `24` | Default lifetime for issued keys |
| `RATE_LIMIT_REQUESTS` | `30` | Max requests per key/IP per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window in seconds |
| `MAX_FAILED_AUTH_ATTEMPTS` | `10` | Max failed auth attempts per IP window |
| `FAILED_AUTH_WINDOW_SECONDS` | `300` | Failed-auth block window in seconds |

### Authentication

All extraction endpoints require an API key. Keys are accepted via:

- `X-API-Key: <token>` header
- `Authorization: Bearer <token>` header
- `?api_key=<token>` query parameter

#### Master Key

Set `MASTER_API_KEY` to a strong random string. It never expires and has admin access.

#### Issued Keys

Use the master key to issue temporary encrypted keys:

```bash
# Issue a 1-hour key
curl -X POST "https://your-domain.com/api/auth/issue-key" \
  -H "X-API-Key: $MASTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "ttl_hours": 1}'
```

Response:

```json
{
  "api_key": "<encrypted-token>",
  "expires_at": 1712345678,
  "role": "user",
  "key_id": "usr_xxx"
}
```

Use the returned `api_key` for subsequent requests:

```bash
curl "https://your-domain.com/api/fetch?url=<instagram-url>" \
  -H "X-API-Key: <encrypted-token>"
```

#### Single-Use Rolling Keys

By default, issued keys are **single-use**. After each authenticated request, a new key is returned in the `X-New-API-Key` response header and the old key is revoked.

```bash
# First request
curl "https://your-domain.com/api/fetch?url=<instagram-url>" \
  -H "X-API-Key: <token-1>" \
  -D headers.txt

# Extract the new key for the next request
TOKEN_2=$(grep -i "X-New-API-Key" headers.txt | awk '{print $2}' | tr -d '\r')

# Second request must use the new key
curl "https://your-domain.com/api/fetch?url=<instagram-url>" \
  -H "X-API-Key: $TOKEN_2"
```

To issue a reusable key, set `single_use: false`:

```bash
curl -X POST "https://your-domain.com/api/auth/issue-key" \
  -H "X-API-Key: $MASTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "ttl_hours": 24, "single_use": false}'
```

#### Generating an AES Key

```bash
python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

### Security Hardening

- **Never commit secrets.** `AES_KEY` and `MASTER_API_KEY` must be set via environment variables. The code refuses to run extraction/auth if they are missing.
- **Rate limiting:** Each API key + IP combination is limited to `RATE_LIMIT_REQUESTS` per window (default 30/min).
- **Brute-force protection:** More than `MAX_FAILED_AUTH_ATTEMPTS` failed attempts from the same IP in the window returns 403.
- **Sanitized logging:** API keys are never logged. Only a SHA-256 fingerprint is recorded.
- **Security headers:** All responses include `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`.
- **Request IDs:** Every response has an `X-Request-ID` header for tracing abuse.

## Project Structure

```
instagram-media-api/
├── api/
│   ├── __init__.py
│   ├── auth.py            # AES encryption and key validation
│   ├── config.py          # Settings and environment variables
│   ├── extractor.py       # Instagram scraping logic
│   ├── index.py           # FastAPI entry point
│   ├── models.py          # Pydantic schemas
│   └── security.py        # Rate limiting and abuse logging
├── tests/
│   ├── test_api.py
│   ├── test_auth.py
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
