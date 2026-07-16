"""Instagram media extraction logic.

This module fetches public Instagram post pages and extracts media URLs,
author metadata, and captions from the HTML response. It relies on
browser impersonation (curl_cffi) to reduce the chance of blocking.
"""

import html
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlparse

from curl_cffi import requests as cf

from api.config import Settings
from api.models import InstagramMediaItem, InstagramPostResponse, MediaType

logger = logging.getLogger(__name__)

INSTAGRAM_DOMAIN = "instagram.com"
VALID_PATH_PREFIXES = ("/p/", "/reel/", "/reels/", "/tv/")


class ExtractionError(Exception):
    """Raised when media extraction fails."""

    pass


def normalize_instagram_url(url: str) -> str:
    """Validate and normalize an Instagram post URL.

    Args:
        url: Raw Instagram URL.

    Returns:
        Normalized HTTPS URL.

    Raises:
        ExtractionError: If the URL is not a supported Instagram post URL.
    """
    url = url.strip()
    parsed = urlparse(url)

    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ExtractionError("URL must use HTTP or HTTPS scheme.")

    netloc = parsed.netloc.lower().lstrip("www.")
    if INSTAGRAM_DOMAIN not in netloc:
        raise ExtractionError("URL must point to an instagram.com domain.")

    if not any(parsed.path.startswith(prefix) for prefix in VALID_PATH_PREFIXES):
        raise ExtractionError(
            "Unsupported Instagram URL. Only posts, Reels, and IGTV are supported."
        )

    return f"https://www.{netloc}{parsed.path}"


def extract_shortcode(url: str) -> str:
    """Extract the Instagram shortcode from a normalized URL."""
    for prefix in VALID_PATH_PREFIXES:
        if prefix in url:
            remainder = url.split(prefix, 1)[1]
            parts = [p for p in remainder.split("/") if p]
            if parts:
                return parts[0].split("?")[0].split("#")[0]
    return "unknown"


def _unescape_url(raw_url: str) -> str:
    """Clean escaped JSON URLs returned by Instagram."""
    return html.unescape(raw_url).replace("\\/", "/")


def _deduplicate_urls(urls: List[str]) -> List[str]:
    """Deduplicate URLs by filename, preferring longer (often higher-quality) URLs."""
    best: Dict[str, str] = {}
    for url in urls:
        path = url.split("?")[0].split("/")[-1]
        if path not in best or len(url) > len(best[path]):
            best[path] = url
    return sorted(best.values())


def _extract_meta_tags(html_content: str) -> List[str]:
    """Return all <meta ...> tag strings from the HTML."""
    return re.findall(r"<meta\s+([^>]+)>", html_content, re.IGNORECASE)


def _parse_meta_content(tag: str) -> Optional[str]:
    """Extract the content attribute from a meta tag string."""
    match = re.search(r'content=["\']([^"\']+)["\']', tag)
    if match:
        return html.unescape(match.group(1))
    return None


def _extract_og_image(meta_tags: List[str]) -> Optional[str]:
    """Return the first og:image URL found in meta tags."""
    for tag in meta_tags:
        if 'property="og:image"' in tag or "property='og:image'" in tag:
            content = _parse_meta_content(tag)
            if content:
                return _unescape_url(content)
    return None


def _extract_core_id(first_image_url: Optional[str]) -> str:
    """Derive a short core identifier from an og:image URL.

    This helps filter out unrelated sidebar recommendation images.
    """
    if not first_image_url:
        return ""
    filename = first_image_url.split("/")[-1]
    parts = filename.split("_")
    if len(parts) >= 2:
        return parts[1][:8]
    return ""


def extract_metadata(meta_tags: List[str]) -> Dict[str, str]:
    """Parse author, username, title, and caption from meta tags."""
    twitter_title = ""
    og_title = ""
    description = ""

    for tag in meta_tags:
        content = _parse_meta_content(tag)
        if content is None:
            continue

        if 'name="twitter:title"' in tag or "name='twitter:title'" in tag:
            twitter_title = content
        elif 'property="og:title"' in tag or "property='og:title'" in tag:
            og_title = content
        elif 'name="description"' in tag or 'property="og:description"' in tag:
            if not description or len(content) > len(description):
                description = content

    author = "Unknown"
    username = "unknown"
    caption = ""
    title = og_title or twitter_title

    # "Author Name (@username) • Instagram..."
    if twitter_title:
        user_match = re.search(r"\((@\w+)\)", twitter_title)
        if user_match:
            username = user_match.group(1).replace("@", "")
        author_match = re.search(r"^(.*?)\s*\(@", twitter_title)
        if author_match:
            author = author_match.group(1).strip()

    # Fallback username from description: "comments - username on June..."
    if username == "unknown" and description:
        desc_user = re.search(r"comments\s*-\s*(\w+)\s+on", description)
        if desc_user:
            username = desc_user.group(1)

    # Caption from og:title: 'Name on Instagram: "CaptionText"'
    if og_title:
        cap_match = re.search(r'on Instagram:\s*"(.*?)"$', og_title, re.DOTALL)
        if cap_match:
            caption = cap_match.group(1).strip()

    # Fallback caption from description
    if not caption and description:
        cap_match = re.search(
            r'on\s+[A-Za-z]+\s+\d+,\s+\d+:\s*"(.*?)"', description, re.DOTALL
        )
        if cap_match:
            caption = cap_match.group(1).strip()

    if not caption:
        caption = og_title or description

    return {
        "title": title,
        "author": author,
        "username": username,
        "caption": caption,
    }


def extract_media_urls(
    html_content: str, core_id: str
) -> Tuple[List[str], List[str]]:
    """Extract unique image and video URLs from Instagram HTML.

    Args:
        html_content: Raw HTML text.
        core_id: Short identifier used to filter unrelated images.

    Returns:
        Tuple of (image_urls, video_urls).
    """
    # Images
    raw_display_uris = re.findall(
        r'"display_uri"\s*:\s*"(https:[^"]+)"', html_content
    )
    candidate_images: Set[str] = set()
    for raw_url in raw_display_uris:
        clean_url = _unescape_url(raw_url)
        if not core_id or core_id in clean_url:
            candidate_images.add(clean_url)

    # Videos
    video_blocks = re.findall(
        r'"video_versions"\s*:\s*\[(.*?)\]', html_content
    )
    candidate_videos: Set[str] = set()
    for block in video_blocks:
        for raw_url in re.findall(r'"url"\s*:\s*"(https:[^"]+)"', block):
            candidate_videos.add(_unescape_url(raw_url))

    # og:video fallback
    meta_tags = _extract_meta_tags(html_content)
    for tag in meta_tags:
        if 'property="og:video"' in tag or "property='og:video'" in tag:
            content = _parse_meta_content(tag)
            if content:
                candidate_videos.add(_unescape_url(content))

    return _deduplicate_urls(list(candidate_images)), _deduplicate_urls(
        list(candidate_videos)
    )


def fetch_instagram_page(url: str, settings: Settings) -> str:
    """Fetch an Instagram post page using browser impersonation.

    Args:
        url: Normalized Instagram URL.
        settings: Application settings.

    Returns:
        Raw HTML content.

    Raises:
        ExtractionError: If the request fails or returns a non-200 status.
    """
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    logger.info("Fetching Instagram page", extra={"url": url})

    try:
        response = cf.get(
            url,
            headers=headers,
            impersonate=settings.impersonate_browser,
            timeout=settings.request_timeout,
        )
    except Exception as exc:
        logger.exception("Network request to Instagram failed")
        raise ExtractionError(f"Failed to reach Instagram: {exc}") from exc

    if response.status_code != 200:
        logger.error(
            "Instagram returned non-200 status",
            extra={"status_code": response.status_code},
        )
        raise ExtractionError(
            f"Instagram returned status code {response.status_code}. "
            "The post may be private, removed, or rate-limited."
        )

    return response.text


def extract_instagram_post(url: str, settings: Settings) -> InstagramPostResponse:
    """Main entry point: fetch and parse an Instagram post.

    Args:
        url: Raw Instagram post URL.
        settings: Application settings.

    Returns:
        Parsed Instagram post response.

    Raises:
        ExtractionError: If extraction fails.
    """
    normalized_url = normalize_instagram_url(url)
    shortcode = extract_shortcode(normalized_url)

    html_content = fetch_instagram_page(normalized_url, settings)

    meta_tags = _extract_meta_tags(html_content)
    first_image_url = _extract_og_image(meta_tags)
    core_id = _extract_core_id(first_image_url)

    metadata = extract_metadata(meta_tags)
    image_urls, video_urls = extract_media_urls(html_content, core_id)

    if first_image_url:
        image_urls_set = set(image_urls)
        image_urls_set.add(first_image_url)
        image_urls = _deduplicate_urls(list(image_urls_set))

    media: List[InstagramMediaItem] = []

    for video_url in video_urls:
        escaped = quote(str(video_url), safe="")
        media.append(
            InstagramMediaItem(
                type="video",
                url=video_url,
                proxy_url=f"/api/proxy?url={escaped}",
            )
        )

    for image_url in image_urls:
        escaped = quote(str(image_url), safe="")
        media.append(
            InstagramMediaItem(
                type="photo",
                url=image_url,
                proxy_url=f"/api/proxy?url={escaped}",
            )
        )

    if len(media) > 1:
        post_type = MediaType.CAROUSEL
    elif video_urls:
        post_type = MediaType.VIDEO
    else:
        post_type = MediaType.PHOTO

    return InstagramPostResponse(
        shortcode=shortcode,
        input_url=normalized_url,
        type=post_type,
        title=metadata.get("title") or None,
        author=metadata.get("author", "Unknown"),
        username=metadata.get("username", "unknown"),
        caption=metadata.get("caption") or None,
        media_count=len(media),
        media=media,
    )
