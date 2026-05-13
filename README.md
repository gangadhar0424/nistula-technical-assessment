# Nistula Guest Communication Platform

AI-powered backend for Nistula's villa rental guest messaging. Receives guest messages from multiple channels (WhatsApp, Booking.com, Airbnb, Instagram, direct), classifies intent, drafts contextual replies using Claude, and routes them based on confidence scoring.

Built for the Nistula Summer Technology Internship 2026 technical assessment.

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/gangadhar0424/nistula-technical-assessment.git
cd nistula-technical-assessment

# 2. Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux

# Edit .env and add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-...

# 5. Run the server
uvicorn app.main:app --reload
```

The server starts at `http://127.0.0.1:8000`. Interactive API docs are at `http://127.0.0.1:8000/docs`.

---

## Testing the Endpoint

### 1. Availability enquiry (should auto_send)

```bash
curl -X POST http://127.0.0.1:8000/webhook/message \
  -H "Content-Type: application/json" \
  -d '{
    "source": "whatsapp",
    "guest_name": "Rahul Sharma",
    "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
    "timestamp": "2026-05-05T10:30:00Z",
    "booking_ref": "NIS-2024-0891",
    "property_id": "villa-b1"
  }'
```

Expected: `query_type: "pre_sales_availability"`, `action: "auto_send"`, confidence ~0.91

### 2. Complaint (should always escalate)

```bash
curl -X POST http://127.0.0.1:8000/webhook/message \
  -H "Content-Type: application/json" \
  -d '{
    "source": "whatsapp",
    "guest_name": "Anjali Mehta",
    "message": "There is no hot water and we have guests arriving for breakfast in 4 hours. This is unacceptable. I want a refund for tonight.",
    "timestamp": "2026-05-05T03:00:00Z",
    "booking_ref": "NIS-2024-0912",
    "property_id": "villa-b1"
  }'
```

Expected: `query_type: "complaint"`, `action: "escalate"` (complaints always escalate regardless of score)

### 3. Pre-sales from Instagram, no booking ref (should agent_review)

```bash
curl -X POST http://127.0.0.1:8000/webhook/message \
  -H "Content-Type: application/json" \
  -d '{
    "source": "instagram",
    "guest_name": "Priya Nair",
    "message": "Hey! How much for a weekend stay at your Goa villa?",
    "timestamp": "2026-05-06T14:20:00Z",
    "property_id": "villa-b1"
  }'
```

Expected: `query_type: "pre_sales_pricing"`, `action: "agent_review"` (no booking ref = lower confidence)

---

## Confidence Scoring

The confidence score (0.0 – 1.0) determines what happens to the AI-drafted reply:

| Score Range | Action | Meaning |
|---|---|---|
| > 0.85 | `auto_send` | Reply sent to guest automatically |
| 0.60 – 0.85 | `agent_review` | Queued for human review before sending |
| < 0.60 | `escalate` | Flagged for immediate human attention |
| Any (complaint) | `escalate` | Complaints always escalate, no exceptions |

The score is built from six binary factors:

| Factor | Points | Rationale |
|---|---|---|
| Query type matched cleanly (not general_enquiry) | +0.30 | We understood the intent |
| Property ID is known (e.g., villa-b1) | +0.20 | We have context to answer accurately |
| Booking reference present | +0.15 | This is a real guest with a real booking |
| Source is a known channel | +0.10 | We can send the reply back |
| Message length 10–500 chars | +0.10 | Single-intent, answerable message |
| No complaint detected | +0.15 | Safe for automated handling |

**Maximum score: 1.0** (all factors present). The additive approach was chosen because each factor is binary — either present or not — and the math is easy to audit.

---

## Design Decisions

### Why FastAPI?

- Built-in request validation via Pydantic — one model definition gives you type checking, error messages, and OpenAPI docs for free
- Async-capable out of the box — ready for high-throughput if needed
- Lightweight — no ORM, no admin panel, just request → response
- Interactive docs at `/docs` make testing during development fast

### How Classification Works

Rule-based keyword matching with explicit priority ordering:

1. **Complaints** checked first — always escalated, highest priority
2. **Availability** → **Pricing** → **Check-in** → **Special requests** checked in specificity order
3. **General enquiry** as fallback — routes to human review, which is the safest default

Why not ML? For this scope, keyword matching is transparent, debuggable, requires no training data, and the priority logic is immediately readable. In production, I'd use Claude itself for classification (structured output with a classification prompt) or a fine-tuned intent classifier.

### Architecture

```
Incoming Webhook → Pydantic Validation → Normalization → Classification
    → Confidence Scoring → Claude API → Action Routing → Response
```

Each step is a separate module with a single responsibility. The webhook handler (`webhook.py`) orchestrates the flow but doesn't contain business logic.

### What I'd Add With More Time

- **Database integration** — connect to PostgreSQL using the schema in `schema.sql`, store every message and conversation
- **Claude-based classification** — replace keyword matching with Claude structured output for better accuracy on ambiguous messages
- **Conversation threading** — track multi-message conversations so Claude has context from previous messages
- **Rate limiting** — per-source rate limits to prevent abuse
- **Async Claude client** — switch to `AsyncAnthropic` for better throughput under load
- **Webhook signature verification** — validate that incoming requests are actually from WhatsApp/Booking.com
- **Message deduplication** — idempotency keys to prevent processing the same message twice
- **Metrics and monitoring** — track classification distribution, confidence score distribution, Claude latency, and error rates
