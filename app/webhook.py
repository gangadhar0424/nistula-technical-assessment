"""
webhook.py — POST /webhook/message endpoint.

This is the main orchestration layer. It ties together:
  1. Payload validation (via Pydantic models)
  2. Normalization (IncomingMessage → NormalizedMessage)
  3. Classification (classifier.py)
  4. Confidence scoring (confidence.py)
  5. AI reply generation (prompt_builder.py + Claude API)
  6. Action determination (auto_send / agent_review / escalate)

Why a separate webhook.py instead of putting routes in main.py?
Separation of concerns — main.py handles app configuration and startup,
webhook.py handles business logic. As the app grows, you'd add more
route files (e.g., admin.py, health.py) without cluttering main.py.
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from anthropic import Anthropic, APIError, APIConnectionError

from app.models import IncomingMessage, NormalizedMessage, WebhookResponse
from app.classifier import classify_message
from app.confidence import calculate_confidence, determine_action
from app.prompt_builder import build_system_prompt, build_user_prompt

# Set up logging — using Python's built-in logging because it's
# simple and integrates well with uvicorn's logging
logger = logging.getLogger(__name__)

# Create a router instead of using the app directly —
# this lets main.py include this router with a prefix if needed
router = APIRouter()

# Fallback message when Claude API is unavailable —
# guests still get a response, just not an AI-generated one
FALLBACK_REPLY = (
    "Thank you for reaching out! Our team has received your message "
    "and will get back to you shortly. If this is urgent, please call "
    "our property manager directly."
)


@router.post("/webhook/message", response_model=WebhookResponse)
async def handle_webhook(payload: IncomingMessage) -> WebhookResponse:
    """
    Process an incoming guest message from any channel.

    Flow:
    1. Normalize the incoming payload into our internal schema
    2. Classify the message type (availability, pricing, complaint, etc.)
    3. Calculate confidence score
    4. Generate an AI-drafted reply via Claude
    5. Determine action (auto_send / agent_review / escalate)
    6. Return the complete response

    Args:
        payload: Validated IncomingMessage from the request body.

    Returns:
        WebhookResponse with drafted reply and action recommendation.

    Raises:
        HTTPException 503: If the Claude API is unavailable.
    """
    # --- Step 1: Normalize ---
    # Convert external payload format to our internal unified schema.
    # The field mapping is simple here (message → message_text) but in
    # production, different sources would have wildly different payload
    # shapes that all get normalized to this one format.
    normalized = NormalizedMessage(
        source=payload.source,
        guest_name=payload.guest_name,
        message_text=payload.message,
        timestamp=payload.timestamp,
        booking_ref=payload.booking_ref,
        property_id=payload.property_id,
    )

    logger.info(
        "Received message %s from %s via %s",
        normalized.message_id,
        normalized.guest_name,
        normalized.source,
    )

    # --- Step 2: Classify ---
    # Determine what the guest is asking about so we can
    # focus the AI response and route appropriately
    query_type = classify_message(normalized.message_text)
    normalized.query_type = query_type

    logger.info(
        "Message %s classified as: %s",
        normalized.message_id,
        query_type,
    )

    # Log a warning for unknown properties — we still process them,
    # but the AI will have limited context
    if normalized.property_id and normalized.property_id not in {"villa-b1"}:
        logger.warning(
            "Unknown property_id '%s' for message %s — processing with limited context",
            normalized.property_id,
            normalized.message_id,
        )

    # --- Step 3: Calculate confidence ---
    confidence_score = calculate_confidence(
        query_type=query_type,
        property_id=normalized.property_id,
        booking_ref=normalized.booking_ref,
        source=normalized.source,
        message_text=normalized.message_text,
    )

    # --- Step 4: Determine action ---
    # Done before AI call so we know the routing even if Claude fails
    action = determine_action(confidence_score, query_type)

    logger.info(
        "Message %s — confidence: %.2f, action: %s",
        normalized.message_id,
        confidence_score,
        action,
    )

    # --- Step 5: Generate AI reply ---
    drafted_reply = await _generate_ai_reply(
        guest_name=normalized.guest_name,
        query_type=query_type,
        message_text=normalized.message_text,
        property_id=normalized.property_id,
        message_id=normalized.message_id,
    )

    # --- Step 6: Build and return response ---
    return WebhookResponse(
        message_id=normalized.message_id,
        query_type=query_type,
        drafted_reply=drafted_reply,
        confidence_score=round(confidence_score, 2),
        action=action,
    )


async def _generate_ai_reply(
    guest_name: str,
    query_type: str,
    message_text: str,
    property_id: str | None,
    message_id: str,
) -> str:
    """
    Call Claude API to generate a guest-facing reply.

    Handles API errors gracefully — if Claude is down, we return
    a fallback message rather than failing the entire request.
    The webhook still returns classification and action info.

    Args:
        guest_name: Guest's name for personalization.
        query_type: Classified query type.
        message_text: The guest's original message.
        property_id: Property ID for context lookup.
        message_id: For logging/tracking purposes.

    Returns:
        The AI-generated reply string, or a fallback message on failure.

    Raises:
        HTTPException 503: If Claude API is completely unreachable.
    """
    # Get API key from environment — python-dotenv loads .env at startup
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set in environment")
        # Return fallback instead of crashing — the classification
        # and routing are still valuable even without an AI reply
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AI service unavailable",
                "message": FALLBACK_REPLY,
                "reason": "API key not configured",
            },
        )

    # Build prompts
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        guest_name=guest_name,
        query_type=query_type,
        message_text=message_text,
        property_id=property_id,
    )

    try:
        # Using the synchronous Anthropic client because FastAPI handles
        # async at the route level. For high-throughput production use,
        # you'd switch to AsyncAnthropic.
        client = Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,  # Keep replies concise — this is a chat message, not an essay
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
        )

        # Extract the text from Claude's response
        # Claude returns a list of content blocks — we want the first text block
        drafted_reply = response.content[0].text

        logger.info(
            "AI reply generated for message %s (%d chars)",
            message_id,
            len(drafted_reply),
        )

        return drafted_reply

    except APIConnectionError as exc:
        # Network issue — Claude is unreachable
        logger.error(
            "Claude API connection error for message %s: %s",
            message_id,
            str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AI service unavailable",
                "message": FALLBACK_REPLY,
                "reason": "Could not connect to AI service",
            },
        )

    except APIError as exc:
        # Claude returned an error (rate limit, invalid request, etc.)
        logger.error(
            "Claude API error for message %s: status=%s, message=%s",
            message_id,
            exc.status_code,
            str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AI service error",
                "message": FALLBACK_REPLY,
                "reason": f"AI service returned status {exc.status_code}",
            },
        )

    except Exception as exc:
        # Catch-all for unexpected errors — log and return fallback
        logger.error(
            "Unexpected error generating AI reply for message %s: %s",
            message_id,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AI service error",
                "message": FALLBACK_REPLY,
                "reason": "Unexpected error during AI reply generation",
            },
        )
