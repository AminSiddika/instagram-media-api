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


class IssueKeyRequest(BaseModel):
    role: str = Field(default="user", description="Role assigned to the key")
    ttl_hours: int = Field(default=24, ge=1, le=8760, description="Key lifetime in hours")
    key_id: Optional[str] = Field(default=None, description="Optional custom key identifier")
    single_use: bool = Field(default=True, description="If true, the key rotates after each request")


class IssueKeyResponse(BaseModel):
    api_key: str = Field(..., description="Encrypted API key")
    expires_at: int = Field(..., description="Unix timestamp when the key expires")
    role: str = Field(..., description="Assigned role")
    key_id: str = Field(..., description="Key identifier")
    single_use: bool = Field(..., description="Whether this key rotates after each request")


class VerifyKeyResponse(BaseModel):
    valid: bool = Field(..., description="Whether the key is valid")
    key_id: str = Field(..., description="Key identifier")
    role: str = Field(..., description="Assigned role")
    expires_at: Optional[int] = Field(None, description="Unix expiry timestamp (null for master)")
    type: str = Field(..., description="Key type: master or issued")
    single_use: Optional[bool] = Field(None, description="Whether this key rotates after each request")
