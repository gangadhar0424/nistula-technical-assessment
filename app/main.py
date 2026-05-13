"""
main.py — FastAPI application entry point.

This file is intentionally minimal. It handles:
  1. Loading environment variables from .env
  2. Creating the FastAPI app instance
  3. Registering route modules (webhook.py)
  4. Adding a health check endpoint

All business logic lives in dedicated modules (classifier.py, confidence.py, etc.).
This keeps main.py clean as the app grows — you'd just add more router includes.

Run with: uvicorn app.main:app --reload
"""

import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.webhook import router as webhook_router

# Load .env file BEFORE anything else accesses os.getenv() —
# this is why it's at module level, not inside a function
load_dotenv()

# Configure logging — match the LOG_LEVEL from .env
# Using basicConfig for simplicity; production would use a more
# structured logging setup (e.g., JSON logs for log aggregation)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Create the FastAPI app with metadata for auto-generated docs
# Visit /docs after starting the server to see interactive Swagger UI
app = FastAPI(
    title="Nistula Guest Communication Platform",
    description=(
        "AI-powered guest messaging platform for Nistula villa rentals. "
        "Receives messages from multiple channels (WhatsApp, Booking.com, etc.), "
        "classifies intent, and drafts contextual replies using Claude."
    ),
    version="1.0.0",
)

# Register the webhook routes — all routes defined in webhook.py
# are now accessible under the app
app.include_router(webhook_router)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to Swagger docs for easy browser access."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.

    Used by load balancers, monitoring tools, and deployment pipelines
    to verify the service is running. Returns 200 with a status message.
    No authentication required.
    """
    return {"status": "healthy", "service": "nistula-guest-platform"}


# Log startup — useful for confirming the app loaded correctly
logger.info("Nistula Guest Communication Platform initialized")
