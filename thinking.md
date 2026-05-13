# Thinking

## Question A — The Immediate Response

### The Reply (3am, WhatsApp)

> Hi [Guest Name], I'm really sorry about the hot water issue — I completely understand how frustrating this is, especially with guests arriving in a few hours. I've already alerted our caretaker Ravi, and he's being dispatched to Villa B1 right now to diagnose and fix this. He'll call you within 15 minutes to confirm he's on his way.
>
> For your morning, I've also asked our team to arrange hot water through our backup system so your guests aren't affected at breakfast. Regarding tonight's stay, I'll have our property manager Priya reach out to you by 9am to discuss a fair resolution — she can be reached directly at +91-XXXXX-XXXXX if you need her sooner.
>
> Again, I'm sorry for the inconvenience. We'll make this right.

### Why this wording

The reply leads with empathy, not policy. It names real people (Ravi, Priya) because at 3am a guest needs to know an actual human is moving, not a chatbot acknowledging a ticket. It commits to a specific timeline (15 minutes, 9am) without promising a refund — that's a decision for the property manager, not an AI. The backup hot water line addresses the immediate practical problem (guests arriving for breakfast) rather than just the abstract complaint.

---

## Question B — The System Design

When that 3am message hits the webhook, several things fire in parallel:

**Immediate triggers (within seconds):**
- Message is classified as `complaint`, confidence drops, action is set to `escalate`
- The AI drafts a reply (the one above) but it's held for human review — complaints are never auto-sent
- Push notification goes to the on-call property manager's phone
- SMS alert goes to the Villa B1 caretaker with the message summary
- A high-priority ticket is created in the internal dashboard

**Notification chain:**
1. Caretaker (Ravi) — SMS + WhatsApp with the specific issue and villa number
2. Property manager (Priya) — push notification + email with the full conversation
3. If neither responds within 15 minutes, the regional operations lead gets paged
4. If no human responds within 30 minutes, the system auto-sends the AI draft (marked as AI-sent), creates an incident report, and notifies the CEO-level escalation channel

**What gets logged in the database:**
- `messages` table: raw content, normalized JSONB, query_type=complaint, confidence score, draft_status=escalated
- `conversations` table: last_active_at updated, linked to reservation
- A new entry in an `escalations` table (not in the current schema but would be added) tracking response times and resolution status

---

## Question C — The Learning

Third hot water complaint at Villa B1 in two months — this is no longer an incident, it's a pattern.

**What the system should flag:**
I'd build a simple anomaly detector that runs nightly over complaint tags. When the same property + complaint category (e.g., "hot_water", "plumbing") hits 3 occurrences within 60 days, it triggers an automated alert to the maintenance team. No ML needed for this — a SQL query with a sliding window and threshold count is enough.

**What I'd build:**
1. **Automated maintenance ticket** — the third complaint auto-generates a maintenance work order tagged as "recurring issue" with links to all three complaint conversations. This goes directly to the maintenance vendor, not just the caretaker.
2. **Preventive checklist** — a weekly caretaker inspection checklist for Villa B1 that now includes "test hot water in all 3 bathrooms" as a mandatory item. The system tracks checklist completion and flags if it's skipped.
3. **Proactive guest communication** — for the next guest checking into Villa B1, the system sends a pre-arrival message: "We've recently upgraded the hot water system at Villa B1. If you notice anything at all, text us and our caretaker Ravi will be there within 15 minutes." This turns a liability into a trust-building moment.

The goal is to close the feedback loop: complaints → pattern detection → maintenance action → verification → proactive communication. The system shouldn't just react to problems, it should prevent them from recurring.
