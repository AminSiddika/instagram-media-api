from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    CAROUSEL = "carousel"


class InstagramMediaItem(BaseModel):
    type: str = Field(..., pattern="^(photo|video)$", description="Media item type: photo or video")
    url: HttpUrl = Field(..., description="Direct URL to the media file")
    proxy_url: str = Field(..., description="Proxied URL served through this API")


class InstagramPostResponse(BaseModel):
    shortcode: str = Field(..., description="Instagram post shortcode")
    input_url: HttpUrl = Field(..., description="Original Instagram URL provided")
    type: MediaType = Field(..., description="Detected post type")
    title: Optional[str] = Field(None, description="Post title from OpenGraph metadata")
    author: str = Field("Unknown", description="Author display name")
    username: str = Field("unknown", description="Instagram username")
    caption: Optional[str] = Field(None, description="Post caption text")
    media_count: int = Field(..., description="Total number of extracted media items")
    media: List[InstagramMediaItem] = Field(..., description="List of extracted media items")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error message")


class HealthResponse(BaseModel):
    status: str
    version: str
