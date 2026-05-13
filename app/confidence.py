"""
confidence.py — Confidence scoring for AI-drafted responses.

Confidence Score Logic
======================
The confidence score determines what happens to the AI-drafted reply:
  - > 0.85   →  auto_send    (reply sent to guest immediately)
  - 0.60-0.85 → agent_review (queued for human review before sending)
  - < 0.60   →  escalate     (flagged for immediate human attention)
  - complaint →  ALWAYS escalate, regardless of score

The score is built from six independent factors, each contributing
a fixed amount to the total. This additive approach was chosen over
a weighted average because:
1. Each factor is binary (present/absent), not a spectrum
2. It's easy to explain and debug
3. New factors can be added without re-tuning existing weights

Factor Breakdown:
  +0.30  Query type matched cleanly (not general_enquiry fallback)
  +0.20  Property ID is a known property (we have context to answer)
  +0.15  Booking reference is present (we can look up their stay)
  +0.10  Source is a known/supported channel
  +0.10  Message length is reasonable (10-500 chars)
  +0.15  No complaint detected in the message

Maximum possible score: 1.0 (all factors present)
Minimum practical score: 0.0 (nothing matches)
"""

from app.models import QueryType, ActionType

# Properties we have full context for — can be expanded as new
# properties are onboarded to the platform
KNOWN_PROPERTIES = {"villa-b1"}

# Channels we officially support and can send replies back through
KNOWN_CHANNELS = {"whatsapp", "booking_com", "airbnb", "instagram", "direct"}


def calculate_confidence(
    query_type: QueryType,
    property_id: str | None,
    booking_ref: str | None,
    source: str,
    message_text: str,
) -> float:
    """
    Calculate a confidence score for the AI-drafted response.

    Each factor adds to the score independently. The final score
    is capped at 1.0. Higher scores mean we're more confident the
    AI can handle this without human intervention.

    Args:
        query_type: The classified query type from classifier.py.
        property_id: The property ID from the webhook payload (may be None).
        booking_ref: The booking reference (may be None).
        source: The messaging channel (whatsapp, airbnb, etc.).
        message_text: The raw message text from the guest.

    Returns:
        A float between 0.0 and 1.0 representing confidence.
    """
    score = 0.0

    # Factor 1: Clean classification (+0.30)
    # If the classifier matched a specific category (not the fallback),
    # we're more confident the AI understands the intent
    if query_type != "general_enquiry":
        score += 0.30

    # Factor 2: Known property (+0.20)
    # If we have property context hardcoded (rates, amenities, etc.),
    # the AI can give accurate, specific answers
    if property_id and property_id in KNOWN_PROPERTIES:
        score += 0.20

    # Factor 3: Booking reference present (+0.15)
    # Having a booking ref means this is a real guest with a real reservation,
    # not a cold enquiry — we have more context to work with
    if booking_ref:
        score += 0.15

    # Factor 4: Known channel (+0.10)
    # Messages from supported channels have predictable formats
    # and we can send replies back through them
    if source in KNOWN_CHANNELS:
        score += 0.10

    # Factor 5: Reasonable message length (+0.10)
    # Very short messages ("hi") lack context for good AI replies.
    # Very long messages often contain multiple issues that need
    # human parsing. 10-500 chars is the sweet spot for single-intent messages.
    message_length = len(message_text)
    if 10 <= message_length <= 500:
        score += 0.10

    # Factor 6: No complaint detected (+0.15)
    # Complaints are sensitive — even if we're "confident" in the
    # classification, we don't want the AI handling grievances alone
    if query_type != "complaint":
        score += 0.15

    # Cap at 1.0 — shouldn't exceed this given our weights sum to 1.0,
    # but defensive programming is good practice
    return min(score, 1.0)


def determine_action(confidence_score: float, query_type: QueryType) -> ActionType:
    """
    Decide what to do with the AI-drafted reply based on confidence and type.

    Complaints are ALWAYS escalated regardless of confidence score.
    This is a business rule — we never want a bot handling an upset guest
    without human oversight, even if we're technically confident in the reply.

    Args:
        confidence_score: Float from 0.0 to 1.0.
        query_type: The classified query type.

    Returns:
        One of: "auto_send", "agent_review", "escalate"
    """
    # Business rule: complaints always get human eyes, no exceptions
    if query_type == "complaint":
        return "escalate"

    # High confidence — safe to send automatically
    # "above 0.85" per spec means strictly greater than
    if confidence_score > 0.85:
        return "auto_send"

    # Medium confidence — draft is probably good but needs a human check
    if confidence_score >= 0.60:
        return "agent_review"

    # Low confidence — something is off, escalate to a human
    return "escalate"
