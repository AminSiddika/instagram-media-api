"""Unit tests for the Instagram media extractor."""

import pytest

from api.config import Settings
from api.extractor import (
    ExtractionError,
    _extract_meta_tags,
    extract_instagram_post,
    extract_metadata,
    extract_shortcode,
    normalize_instagram_url,
)


class TestURLNormalization:
    def test_normalizes_short_url(self):
        url = normalize_instagram_url("https://www.instagram.com/p/ABC123/")
        assert url == "https://www.instagram.com/p/ABC123/"

    def test_adds_https_when_missing(self):
        url = normalize_instagram_url("www.instagram.com/p/ABC123/")
        assert url.startswith("https://")

    def test_rejects_non_instagram_domain(self):
        with pytest.raises(ExtractionError):
            normalize_instagram_url("https://www.twitter.com/p/ABC123/")

    def test_rejects_unsupported_path(self):
        with pytest.raises(ExtractionError):
            normalize_instagram_url("https://www.instagram.com/stories/user/123/")


class TestShortcodeExtraction:
    def test_extracts_post_shortcode(self):
        assert extract_shortcode("https://www.instagram.com/p/ABC123/") == "ABC123"

    def test_extracts_reel_shortcode(self):
        assert extract_shortcode("https://www.instagram.com/reel/XYZ789/") == "XYZ789"

    def test_extracts_shortcode_with_query(self):
        url = "https://www.instagram.com/p/ABC123/?igsh=foo"
        assert extract_shortcode(url) == "ABC123"


class TestMetadataExtraction:
    def test_extracts_username_and_author(self):
        html = '''
        <meta name="twitter:title" content="John Doe (@johndoe) • Instagram photos and videos">
        <meta property="og:title" content='John Doe on Instagram: "Hello world"'>
        '''
        meta_tags = _extract_meta_tags(html)
        meta = extract_metadata(meta_tags)
        assert meta["username"] == "johndoe"
        assert meta["author"] == "John Doe"
        assert meta["caption"] == "Hello world"


class TestExtractInstagramPost:
    def test_raises_on_invalid_url(self):
        settings = Settings()
        with pytest.raises(ExtractionError):
            extract_instagram_post("not-a-url", settings)

    def test_raises_on_private_or_missing_post(self):
        settings = Settings()
        with pytest.raises(ExtractionError):
            # This post does not exist and should fail quickly
            extract_instagram_post(
                "https://www.instagram.com/p/this_post_does_not_exist_12345/",
                settings,
            )
