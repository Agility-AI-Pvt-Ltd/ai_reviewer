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

CREATE TABLE IF NOT EXISTS github_oauth_states (
    id SERIAL PRIMARY KEY,
    state VARCHAR(128) UNIQUE NOT NULL,
    auth_identity VARCHAR(255) NOT NULL,
    conversation_id VARCHAR NOT NULL,
    github_url TEXT NOT NULL,
    repo_owner VARCHAR(255) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    requested_scope VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_github_oauth_states_id
    ON github_oauth_states (id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_github_oauth_states_state
    ON github_oauth_states (state);

CREATE INDEX IF NOT EXISTS ix_github_oauth_states_auth_identity
    ON github_oauth_states (auth_identity);

CREATE TABLE IF NOT EXISTS github_credentials (
    id SERIAL PRIMARY KEY,
    auth_identity VARCHAR(255) NOT NULL,
    github_login VARCHAR(255),
    encrypted_access_token TEXT NOT NULL,
    token_type VARCHAR(32) NOT NULL DEFAULT 'bearer',
    scope VARCHAR(255),
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_github_credentials_id
    ON github_credentials (id);

CREATE INDEX IF NOT EXISTS ix_github_credentials_auth_identity
    ON github_credentials (auth_identity);

CREATE INDEX IF NOT EXISTS ix_github_credentials_github_login
    ON github_credentials (github_login);

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
