"""
prompt_builder.py — Constructs system and user prompts for Claude API.

This module owns the "personality" of the AI assistant and the property
knowledge base. In production, property context would come from a database.
For this assessment, it's hardcoded as a constant.

Design decision: System prompt and user prompt are separated because
Claude performs better when the "persona" instructions are in the system
prompt and the per-request context is in the user prompt. This follows
Anthropic's own best practices.
"""

from app.models import QueryType

# --- Property Knowledge Base ---
# In production, this would be fetched from the `properties` table in PostgreSQL.
# Hardcoding here because Part 1 doesn't require a live database.
# The structure mimics what a DB query would return.

PROPERTY_CONTEXT = {
    "villa-b1": {
        "name": "Villa B1",
        "location": "Assagao, North Goa",
        "bedrooms": 3,
        "max_guests": 6,
        "private_pool": True,
        "check_in_time": "2:00 PM",
        "check_out_time": "11:00 AM",
        "base_rate_inr": 18000,
        "base_rate_guests": 4,
        "extra_guest_charge_inr": 2000,
        "wifi_password": "Nistula@2024",
        "caretaker_hours": "8:00 AM to 10:00 PM",
        "chef_available": True,
        "chef_note": "Pre-booking required",
        "availability_apr_20_24": "Available",
        "cancellation_policy": "Free cancellation up to 7 days before check-in",
    }
}

# Default context for unknown properties — we still try to help,
# but flag that we don't have specific details
UNKNOWN_PROPERTY_CONTEXT = {
    "name": "Unknown Property",
    "note": "Property details not found in our system. Provide a general helpful response and suggest the guest contact us directly for specific property information.",
}


def build_system_prompt() -> str:
    """
    Build the system prompt that defines Claude's persona.

    The system prompt is the same for every request — it sets the tone,
    boundaries, and behavioral rules. It does NOT include per-request
    context like guest name or message.

    Returns:
        The system prompt string for Claude.
    """
    return """You are a warm, professional, and knowledgeable villa host assistant for Nistula — a premium villa rental company in Goa, India.

Your communication style:
- Friendly but professional — like a five-star hotel concierge who is also approachable
- Use the guest's first name naturally (not excessively)
- Be specific with facts (dates, prices, times) — never vague
- Keep responses concise — 2 to 4 short paragraphs maximum
- If you don't have information, say so honestly and offer to find out
- For complaints, be empathetic first, then solution-oriented

Rules:
- Never invent availability, pricing, or policies not in the provided context
- Never promise refunds or discounts without noting it needs manager approval
- Always include relevant practical details (check-in time, wifi, etc.) when appropriate
- Sign off warmly but briefly — no lengthy closings
- Do not use excessive emojis — one or two at most, and only if natural"""


def build_user_prompt(
    guest_name: str,
    query_type: QueryType,
    message_text: str,
    property_id: str | None,
) -> str:
    """
    Build the user prompt with all per-request context.

    This includes the guest's message, their query classification,
    and all relevant property details. Claude uses this context
    to generate an accurate, personalized reply.

    Args:
        guest_name: The guest's name from the webhook payload.
        query_type: The classified query type (used to focus Claude's response).
        message_text: The raw message from the guest.
        property_id: The property ID (used to look up context).

    Returns:
        The user prompt string for Claude.
    """
    # Look up property context — fall back to generic if unknown
    property_info = PROPERTY_CONTEXT.get(property_id, UNKNOWN_PROPERTY_CONTEXT)

    # Format property details as readable text for Claude
    # Using a simple key-value format because Claude processes this
    # more reliably than nested JSON in prompts
    property_text = _format_property_context(property_info)

    # Build the complete prompt with all context sections clearly labeled
    # Clear section headers help Claude distinguish between instructions
    # and reference data
    return f"""--- GUEST INFORMATION ---
Name: {guest_name}
Query Type: {query_type}

--- GUEST MESSAGE ---
{message_text}

--- PROPERTY CONTEXT ---
{property_text}

--- INSTRUCTIONS ---
Draft a reply to this guest's message using the property context above.
The query has been classified as: {query_type}

Focus your response on addressing their specific query type:
- For availability queries: confirm dates and mention rates
- For pricing queries: break down costs clearly (base rate, extra guests, total)
- For check-in queries: provide practical arrival details
- For special requests: confirm what's possible and what needs pre-booking
- For complaints: acknowledge the issue, empathize, and offer concrete next steps
- For general enquiries: be helpful and provide relevant property highlights

Reply directly as if you are messaging the guest. Do not include any meta-commentary."""


def _format_property_context(property_info: dict) -> str:
    """
    Convert a property context dictionary into readable text.

    Simple line-by-line formatting — chosen over JSON because Claude
    processes natural language descriptions more accurately than
    structured data in prompts.

    Args:
        property_info: Dictionary of property details.

    Returns:
        Formatted string of property details.
    """
    lines = []
    for key, value in property_info.items():
        # Convert snake_case keys to readable labels
        readable_key = key.replace("_", " ").title()

        # Format boolean values as human-readable text
        if isinstance(value, bool):
            value = "Yes" if value else "No"

        lines.append(f"{readable_key}: {value}")

    return "\n".join(lines)
