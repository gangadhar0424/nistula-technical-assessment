-- ============================================================
-- Nistula Guest Communication Platform — Database Schema
-- ============================================================
-- PostgreSQL CREATE TABLE statements for the core data model.
--
-- Design principles:
--   1. UUIDs as primary keys — safe for distributed systems,
--      no collision risk when merging data across services
--   2. Timestamps with timezone — always store UTC, display local
--   3. Foreign keys enforced — data integrity at the DB level
--   4. JSONB for normalized_content — flexible schema for
--      different message formats without altering the table
-- ============================================================


-- Enable UUID generation (PostgreSQL built-in)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- -----------------------------------------------------------
-- 1. guests — One record per guest across ALL channels.
--
-- A guest who messages on WhatsApp and Booking.com should
-- map to the same row. Deduplication happens at the
-- application layer using email/phone matching.
-- -----------------------------------------------------------
CREATE TABLE guests (
    guest_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name             TEXT NOT NULL,
    email            TEXT,                               -- nullable: not all channels provide email
    phone            TEXT,                               -- nullable: not all channels provide phone
    preferred_channel TEXT,                              -- last channel they used, e.g. 'whatsapp'
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- when we first heard from this guest
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- last profile update
);

-- Index on email and phone for deduplication lookups
CREATE INDEX idx_guests_email ON guests (email) WHERE email IS NOT NULL;
CREATE INDEX idx_guests_phone ON guests (phone) WHERE phone IS NOT NULL;


-- -----------------------------------------------------------
-- 2. properties — One record per managed property.
--
-- Stores the static property information that feeds into
-- the AI prompt builder. property_id is a human-readable
-- slug (e.g., "villa-b1") rather than a UUID because it's
-- used in URLs, logs, and webhook payloads.
-- -----------------------------------------------------------
CREATE TABLE properties (
    property_id   TEXT PRIMARY KEY,                       -- e.g., 'villa-b1' — readable and stable
    name          TEXT NOT NULL,                           -- display name, e.g. 'Villa B1, Assagao'
    location      TEXT NOT NULL,                           -- e.g., 'North Goa'
    max_guests    INTEGER NOT NULL CHECK (max_guests > 0),
    base_rate_inr NUMERIC(10, 2) NOT NULL,                -- per night base rate in INR
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- -----------------------------------------------------------
-- 3. reservations — Bookings linking guests to properties.
--
-- Each reservation has a unique booking_ref (like "NIS-2024-0891")
-- which is the external-facing identifier guests see in
-- confirmation emails and use when messaging us.
-- -----------------------------------------------------------
CREATE TABLE reservations (
    reservation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_ref    TEXT UNIQUE NOT NULL,                   -- external reference, e.g. 'NIS-2024-0891'
    guest_id       UUID NOT NULL REFERENCES guests(guest_id),
    property_id    TEXT NOT NULL REFERENCES properties(property_id),
    check_in       DATE NOT NULL,
    check_out      DATE NOT NULL,
    num_guests     INTEGER NOT NULL CHECK (num_guests > 0),
    status         TEXT NOT NULL DEFAULT 'confirmed'       -- confirmed / checked_in / completed / cancelled
                   CHECK (status IN ('confirmed', 'checked_in', 'completed', 'cancelled')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Check-out must be after check-in
    CONSTRAINT valid_dates CHECK (check_out > check_in)
);

-- Index on booking_ref for fast lookups from webhook payloads
CREATE INDEX idx_reservations_booking_ref ON reservations (booking_ref);
-- Index on guest_id for "show all bookings for this guest" queries
CREATE INDEX idx_reservations_guest_id ON reservations (guest_id);


-- -----------------------------------------------------------
-- 4. conversations — One thread per guest interaction.
--
-- A conversation groups related messages together. It may
-- or may not be linked to a reservation — pre-sales enquiries
-- won't have one. reservation_id is nullable for this reason.
-- -----------------------------------------------------------
CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guest_id        UUID NOT NULL REFERENCES guests(guest_id),
    reservation_id  UUID REFERENCES reservations(reservation_id), -- nullable for pre-sales
    property_id     TEXT NOT NULL REFERENCES properties(property_id),
    channel         TEXT NOT NULL,                                  -- 'whatsapp', 'booking_com', etc.
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for "find all conversations for this guest" queries
CREATE INDEX idx_conversations_guest_id ON conversations (guest_id);
-- Index for "find all conversations about this property" queries
CREATE INDEX idx_conversations_property_id ON conversations (property_id);


-- -----------------------------------------------------------
-- 5. messages — Every message across all channels.
--
-- This is the highest-volume table. Every inbound guest message
-- and every outbound AI/agent reply is stored here.
--
-- Key design decisions:
--   - raw_content stores the original message as-is (for audit)
--   - normalized_content (JSONB) stores the parsed/enriched version
--   - draft_status tracks the lifecycle of AI-generated replies
--   - ai_confidence_score is stored for analytics and threshold tuning
-- -----------------------------------------------------------
CREATE TABLE messages (
    message_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID NOT NULL REFERENCES conversations(conversation_id),
    direction           TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    raw_content         TEXT NOT NULL,                    -- original message text, unmodified
    normalized_content  JSONB,                            -- parsed/enriched message data
    query_type          TEXT,                              -- classification result, e.g. 'pre_sales_availability'
    ai_confidence_score NUMERIC(4, 3),                    -- 0.000 to 1.000
    draft_status        TEXT NOT NULL DEFAULT 'ai_drafted' -- tracks what happened to the AI draft
                        CHECK (draft_status IN ('ai_drafted', 'agent_edited', 'auto_sent', 'escalated')),
    sent_at             TIMESTAMPTZ,                      -- when the message was actually sent (null if not yet sent)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for retrieving conversation history in order
CREATE INDEX idx_messages_conversation_id ON messages (conversation_id, created_at);
-- Index for analytics — find all messages by query type
CREATE INDEX idx_messages_query_type ON messages (query_type) WHERE query_type IS NOT NULL;
-- Index for finding escalated messages that need attention
CREATE INDEX idx_messages_draft_status ON messages (draft_status) WHERE draft_status = 'escalated';


-- ============================================================
-- HARDEST DESIGN DECISION
-- ============================================================
--
-- The hardest decision was whether to store normalized message
-- data as typed columns or as a single JSONB blob. Typed columns
-- (guest_name TEXT, query_type TEXT, etc.) give you validation,
-- indexing, and queryability for free — but every new channel
-- with a different payload shape means an ALTER TABLE migration.
-- JSONB is flexible but makes querying and enforcing constraints
-- harder.
--
-- I chose a hybrid: raw_content as TEXT for the untouched original
-- (audit trail), normalized_content as JSONB for the flexible
-- enriched version, and the most critical fields (query_type,
-- ai_confidence_score, draft_status) as typed columns with CHECK
-- constraints. This way, the fields we filter and report on daily
-- are fast and validated, but we can still handle unpredictable
-- channel-specific metadata without schema changes.
-- ============================================================
