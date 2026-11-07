-- 001_init.sql : core schema (plain PostgreSQL 15+; Citus distribution is in 002)
BEGIN;

CREATE TABLE IF NOT EXISTS sellers (
    id          uuid PRIMARY KEY,
    state       char(2)     NOT NULL,
    kyc_status  varchar(16) NOT NULL DEFAULT 'PENDING',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS listings (
    seller_id   uuid         NOT NULL,
    id          uuid         NOT NULL,
    state       char(2)      NOT NULL,
    title       varchar(120) NOT NULL,
    price_inr   integer      NOT NULL CHECK (price_inr > 0),
    status      varchar(16)  NOT NULL DEFAULT 'DRAFT',
    created_at  timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_id, id)
);
CREATE INDEX IF NOT EXISTS listings_state_status ON listings (state, status);

CREATE TABLE IF NOT EXISTS animals (
    seller_id   uuid        NOT NULL,
    id          uuid        NOT NULL,
    listing_id  uuid        NOT NULL,
    species     varchar(16) NOT NULL,
    breed       varchar(48),
    sex         varchar(8)  NOT NULL,
    age_months  integer CHECK (age_months IS NULL OR age_months BETWEEN 0 AND 480),
    tag_id      varchar(20),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_id, id)
);
CREATE INDEX IF NOT EXISTS animals_listing ON animals (seller_id, listing_id);
CREATE INDEX IF NOT EXISTS animals_tag ON animals (tag_id) WHERE tag_id IS NOT NULL;

-- Partitioned by month: ~16M rows/month at target scale.
CREATE TABLE IF NOT EXISTS animal_images (
    seller_id    uuid         NOT NULL,
    id           uuid         NOT NULL,
    animal_id    uuid         NOT NULL,
    view         varchar(8)   NOT NULL,
    storage_key  varchar(255) NOT NULL,
    content_type varchar(32)  NOT NULL,
    capture_meta jsonb        NOT NULL DEFAULT '{}',
    uploaded     boolean      NOT NULL DEFAULT false,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_id, id, created_at)
) PARTITION BY RANGE (created_at);
CREATE INDEX IF NOT EXISTS animal_images_animal ON animal_images (seller_id, animal_id);

-- Create current + next 12 monthly partitions. Run monthly (pg_partman or cron) in prod.
DO $$
DECLARE m date := date_trunc('month', now())::date;
BEGIN
  FOR i IN 0..12 LOOP
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS animal_images_%s PARTITION OF animal_images FOR VALUES FROM (%L) TO (%L)',
      to_char(m + (i || ' month')::interval, 'YYYY_MM'),
      m + (i || ' month')::interval,
      m + ((i + 1) || ' month')::interval);
  END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS verifications (
    seller_id      uuid        NOT NULL,
    id             uuid        NOT NULL,
    animal_id      uuid        NOT NULL,
    workflow_id    varchar(80) NOT NULL,
    status         varchar(16) NOT NULL DEFAULT 'PENDING',
    score          real,
    evidence       jsonb       NOT NULL DEFAULT '{}',
    flags          jsonb       NOT NULL DEFAULT '[]',
    reasons        jsonb       NOT NULL DEFAULT '[]',
    model_versions jsonb       NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    decided_at     timestamptz,
    PRIMARY KEY (seller_id, id)
);
CREATE INDEX IF NOT EXISTS verifications_animal ON verifications (seller_id, animal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS verifications_review_queue ON verifications (created_at) WHERE status = 'NEEDS_REVIEW';

CREATE TABLE IF NOT EXISTS reviews (
    seller_id   uuid        NOT NULL,
    id          uuid        NOT NULL,
    animal_id   uuid        NOT NULL,
    reviewer_id varchar(64) NOT NULL,
    decision    varchar(16) NOT NULL,
    reason      text        NOT NULL DEFAULT '',
    labels      jsonb       NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_id, id)
);

CREATE TABLE IF NOT EXISTS outbox (
    seller_id    uuid        NOT NULL,
    id           uuid        NOT NULL,
    topic        varchar(64) NOT NULL,
    key          varchar(64) NOT NULL,
    payload      jsonb       NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    PRIMARY KEY (seller_id, id)
);
CREATE INDEX IF NOT EXISTS outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS state_rules (
    state            char(2)     NOT NULL,
    species          varchar(16) NOT NULL,
    action           varchar(16) NOT NULL,
    allowed          boolean     NOT NULL,
    docs_required    jsonb       NOT NULL DEFAULT '[]',
    note             text        NOT NULL DEFAULT '',
    legally_reviewed boolean     NOT NULL DEFAULT false,
    PRIMARY KEY (state, species, action)
);

COMMIT;
