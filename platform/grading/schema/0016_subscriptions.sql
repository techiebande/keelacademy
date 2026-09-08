-- 0016_subscriptions.sql — all-access subscription billing (Paddle) (S2.6)
--
-- Sales model (owner decision 2026-09-07): a monthly all-access subscription.
-- Enrollments are granted by an ACTIVE subscription, not by per-unit payment.
--
-- subscription_signups: one row per Paddle transaction the enroll service
-- created for a subscription checkout. It is the student <-> paddle-customer
-- link made at checkout creation, used by the webhook to resolve which
-- student a subscription belongs to (custom_data is the primary carrier,
-- this table is the fallback when custom_data is absent).
CREATE TABLE subscription_signups (
    id             bigserial     PRIMARY KEY,
    transaction_id text          NOT NULL UNIQUE,
    customer_id    text          NOT NULL,
    student_id     bigint        NOT NULL REFERENCES students (id),
    created_at     timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX subscription_signups_student_idx ON subscription_signups (student_id);

-- subscriptions: the Paddle subscription entity, convergent (UPSERT to
-- latest state — webhooks are not ordered). status mirrors Paddle Billing:
-- active | trialing | past_due | paused | canceled.
CREATE TABLE subscriptions (
    id                      bigserial   PRIMARY KEY,
    paddle_subscription_id  text        NOT NULL UNIQUE,
    student_id              bigint      NOT NULL REFERENCES students (id),
    customer_id             text        NOT NULL,
    price_id                text        NOT NULL,
    status                  text        NOT NULL
                            CHECK (status IN ('active','trialing','past_due','paused','canceled')),
    scheduled_change        text,
    current_period_ends_at  timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    canceled_at             timestamptz
);

CREATE INDEX subscriptions_student_idx ON subscriptions (student_id);

-- payments: ledger of completed transactions. The rebate state machine
-- (school-architecture §completion rebate) consumes gate events against
-- payments made within its window; this table is its input.
CREATE TABLE payments (
    id                     bigserial   PRIMARY KEY,
    paddle_transaction_id  text        NOT NULL UNIQUE,
    student_id             bigint      REFERENCES students (id),
    paddle_subscription_id text,
    amount_cents           bigint      NOT NULL,
    currency               text        NOT NULL,
    occurred_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX payments_student_idx ON payments (student_id);
