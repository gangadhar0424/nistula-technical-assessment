"""
models.py — Pydantic schemas for request/response validation.

Why Pydantic?
FastAPI uses Pydantic models to automatically validate incoming JSON,
generate OpenAPI docs, and serialize responses. By defining schemas here
we get type safety + documentation for free.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


# --- Allowed values ---
# Using Literal types instead of Enums because they're simpler to work with
# in FastAPI request/response models and produce cleaner error messages.

SourceType = Literal["whatsapp", "booking_com", "airbnb", "instagram", "direct"]

QueryType = Literal[
    "pre_sales_availability",
    "pre_sales_pricing",
    "post_sales_checkin",
    "special_request",
    "complaint",
    "general_enquiry",
]

ActionType = Literal["auto_send", "agent_review", "escalate"]


class IncomingMessage(BaseModel):
    """
    Raw webhook payload from any messaging channel.

    This is the external-facing schema — what partner platforms send us.
    We normalize this into NormalizedMessage internally.
    """

    # Source channel — validated against allowed values automatically
    source: SourceType

    guest_name: str = Field(
        ...,
        min_length=1,
        description="Guest's full name as it appears on the booking platform",
    )

    message: str = Field(
        ...,
        min_length=1,
        description="The raw message text from the guest",
    )

    # ISO 8601 timestamp — Pydantic parses this automatically
    timestamp: datetime

    # Optional because not all messages come with a booking reference
    # (e.g., pre-sales enquiries from Instagram)
    booking_ref: Optional[str] = None

    # Optional because guests may message before selecting a property
    property_id: Optional[str] = None


class NormalizedMessage(BaseModel):
    """
    Internal unified schema after normalization.

    Every message from every channel gets converted to this shape
    before classification and AI processing. This is what gets
    stored in the database.
    """

    # We generate UUIDs server-side so every message is uniquely trackable
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    source: SourceType
    guest_name: str
    message_text: str
    timestamp: datetime
    booking_ref: Optional[str] = None
    property_id: Optional[str] = None

    # Populated after classification — starts as None
    query_type: Optional[QueryType] = None


class WebhookResponse(BaseModel):
    """
    Response returned to the caller after processing.

    Contains the AI-drafted reply, classification, confidence score,
    and the recommended action (auto_send / agent_review / escalate).
    """

    message_id: str
    query_type: QueryType
    drafted_reply: str
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score from 0.0 to 1.0 indicating AI confidence in the response",
    )
    action: ActionType
