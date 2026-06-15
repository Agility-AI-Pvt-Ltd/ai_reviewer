-- FutureX Reviewer database schema.
-- Run this with a migration/admin DB role before starting the service in an
-- environment where the runtime app role only has SELECT + INSERT permissions.

CREATE TABLE IF NOT EXISTS feasibility_reports (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR UNIQUE NOT NULL,
    chain_of_thought JSON,
    idea_fit TEXT,
    competitors TEXT,
    opportunity TEXT,
    score VARCHAR,
    targeting TEXT,
    next_step TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_feasibility_reports_id
    ON feasibility_reports (id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_feasibility_reports_conversation_id
    ON feasibility_reports (conversation_id);

CREATE TABLE IF NOT EXISTS review_job_events (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR NOT NULL,
    github_url TEXT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    payload JSON NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_review_job_events_id
    ON review_job_events (id);

CREATE INDEX IF NOT EXISTS ix_review_job_events_job_id
    ON review_job_events (job_id);

CREATE INDEX IF NOT EXISTS ix_review_job_events_conversation_id
    ON review_job_events (conversation_id);

CREATE INDEX IF NOT EXISTS ix_review_job_events_event_type
    ON review_job_events (event_type);

CREATE TABLE IF NOT EXISTS review_state_snapshots (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR NOT NULL,
    github_url TEXT NOT NULL,
    stage VARCHAR(64) NOT NULL,
    project_path TEXT,
    state JSON NOT NULL DEFAULT '{}',
    idea_lab_report JSON,
    graphify_graph_json JSON,
    graph JSON,
    graph_summary JSON,
    review_report JSON,
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_review_state_snapshots_id
    ON review_state_snapshots (id);

CREATE INDEX IF NOT EXISTS ix_review_state_snapshots_conversation_id
    ON review_state_snapshots (conversation_id);

CREATE INDEX IF NOT EXISTS ix_review_state_snapshots_stage
    ON review_state_snapshots (stage);
