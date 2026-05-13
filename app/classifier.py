"""
classifier.py — Rule-based message classification.

Why keyword matching instead of ML?
For this scope, keyword matching is transparent, debuggable, and doesn't
need training data. In production, this would be replaced with a fine-tuned
classifier or Claude-based classification, but for an assessment, clarity
and explainability matter more than sophistication.

Classification priority:
1. Complaints are checked FIRST because they require immediate escalation
   regardless of other content in the message.
2. Specific categories (availability, pricing, check-in) are checked next.
3. Special requests are caught before the general fallback.
4. If nothing matches, we default to general_enquiry — it's the safest
   bucket because it routes to an agent for review.
"""

import re
from app.models import QueryType


# --- Keyword patterns ---
# Each category has a list of keywords/phrases that indicate that intent.
# We use lowercase matching so "AVAILABLE" and "available" both work.
# Patterns are ordered from most specific to least specific within each list.

COMPLAINT_KEYWORDS = [
    "complaint", "unacceptable", "refund", "terrible", "worst",
    "disgusting", "broken", "not working", "disappointed", "angry",
    "horrible", "poor service", "demand", "compensation", "furious",
    "no hot water", "no water", "no electricity", "filthy", "dirty",
]

AVAILABILITY_KEYWORDS = [
    "available", "availability", "vacant", "free dates", "open dates",
    "book for", "can i book", "any rooms", "any villas",
    "dates available", "is it available",
]

PRICING_KEYWORDS = [
    "rate", "price", "cost", "charge", "tariff", "per night",
    "how much", "total cost", "pricing", "budget", "expensive",
    "discount", "offer", "deal",
]

CHECKIN_KEYWORDS = [
    "check-in", "checkin", "check in", "check-out", "checkout",
    "check out", "arrival", "arriving", "key", "keys", "wifi",
    "wi-fi", "password", "directions", "address", "location",
    "how to reach", "parking",
]

SPECIAL_REQUEST_KEYWORDS = [
    "birthday", "anniversary", "cake", "decoration", "surprise",
    "special", "arrange", "organize", "extra bed", "crib",
    "baby", "pet", "dog", "cat", "chef", "cook", "meal",
    "airport pickup", "transfer", "late checkout", "early checkin",
]


def classify_message(message_text: str) -> QueryType:
    """
    Classify a guest message into one of six query types.

    Uses simple keyword matching against the message text.
    Returns the most specific category that matches, with
    complaints taking highest priority.

    Args:
        message_text: The raw message string from the guest.

    Returns:
        A QueryType string indicating the classification.

    Examples:
        >>> classify_message("Is the villa available next week?")
        'pre_sales_availability'
        >>> classify_message("This is unacceptable, I want a refund")
        'complaint'
    """
    # Normalize to lowercase for case-insensitive matching
    text_lower = message_text.lower()

    # PRIORITY 1: Complaints — always check first because these need
    # immediate escalation, even if the message also mentions pricing/availability
    if _matches_any(text_lower, COMPLAINT_KEYWORDS):
        return "complaint"

    # PRIORITY 2: Availability — guest asking if dates are open
    if _matches_any(text_lower, AVAILABILITY_KEYWORDS):
        return "pre_sales_availability"

    # PRIORITY 3: Pricing — guest asking about rates/costs
    # Checked after availability because "Is it available and what's the rate?"
    # should be classified as availability (the primary intent)
    if _matches_any(text_lower, PRICING_KEYWORDS):
        return "pre_sales_pricing"

    # PRIORITY 4: Check-in/logistics — guest with existing booking
    # asking about arrival details
    if _matches_any(text_lower, CHECKIN_KEYWORDS):
        return "post_sales_checkin"

    # PRIORITY 5: Special requests — extras beyond the standard stay
    if _matches_any(text_lower, SPECIAL_REQUEST_KEYWORDS):
        return "special_request"

    # FALLBACK: If no keywords match, it's a general enquiry.
    # This is intentionally broad — better to route to an agent
    # than to misclassify.
    return "general_enquiry"


def _matches_any(text: str, keywords: list[str]) -> bool:
    """
    Check if any keyword from the list appears in the text.

    Uses simple substring matching rather than word-boundary regex
    because many of our keywords are multi-word phrases like
    "no hot water" that wouldn't work well with word boundaries.

    Args:
        text: The lowercased message text.
        keywords: List of keyword strings to check.

    Returns:
        True if any keyword is found in the text.
    """
    return any(keyword in text for keyword in keywords)
