# FutureX Reviewer

FastAPI microservice that reviews a GitHub project against a FutureX Idea Lab feasibility report.

## Local Setup

Run:

```bash
python script/setup.py
```

The setup script starts local Postgres and Redis with Docker, writes safe localhost values into `.env`, installs dependencies with `uv`, and creates local development tables.

Then start the service:

```bash
uv run fastapi dev app/main.py
```

Useful setup options:

```bash
python script/setup.py --skip-docker
python script/setup.py --skip-install
python script/setup.py --skip-schema
```

## Review Queue

Submitting a review does not block the user session. The API writes a durable job event into Postgres and returns a `job_id` immediately:

```http
POST /review
```

The background worker polls Postgres and continues the LangGraph review even if the user closes the page. When the user comes back, the UI can read:

```http
GET /review/jobs/{job_id}
GET /review/{conversation_id}/job
GET /review/{conversation_id}/state
```

Worker settings:

```env
REVIEW_WORKER_ENABLED=true
REVIEW_WORKER_POLL_SECONDS=3
REVIEW_WORKER_STALE_SECONDS=1800
```

## Private GitHub Repositories

Private repo support is available through GitHub OAuth. Enable it only in
environments where the GitHub OAuth app is configured:

```env
GITHUB_OAUTH_ENABLED=true
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_OAUTH_CALLBACK_URL=https://api.futurex.ai/auth/github/callback
GITHUB_OAUTH_SCOPE=repo
GITHUB_TOKEN_ENCRYPTION_KEY=use-a-long-random-secret
```

Use `POST /review` or `POST /review/start` with the existing review payload. If
the repository is public or already authorized, the API returns the normal
queued-job response. If GitHub access is denied, the API returns:

```json
{
  "requires_auth": true,
  "status": "requires_auth",
  "oauth_url": "https://github.com/login/oauth/authorize?...",
  "state": "..."
}
```

After the user approves access, GitHub redirects to
`GET /auth/github/callback?code=...&state=...`. The callback exchanges the code,
stores the encrypted token server-side, verifies repo access, queues the review,
and returns the same queued-job response shape as `POST /review`.

If you see an error like `relation "review_job_events" does not exist`, the app
tables have not been created in Postgres yet. Run the schema once with a
migration/admin DB role:

```bash
psql "$(printf '%s' "$DATABASE_URL" | sed 's/^postgresql+asyncpg:/postgresql:/')" -f db/schema.sql
```

Do not run this with the restricted runtime role if that role only has
`SELECT` and `INSERT`.

## EC2 CI/CD

The GitHub Actions workflow at `.github/workflows/ec2-deploy.yml` runs tests and a Docker build check before deploying to EC2 with Docker Compose.

Required GitHub secrets:

```text
EC2_HOST
EC2_USER
EC2_SSH_KEY
```

Optional secret:

```text
ENV_FILE
```

Use `ENV_FILE` to upload the production `.env` during deploy. If this secret is not set, the workflow expects `.env` to already exist in the app directory on EC2.

Optional GitHub variable:

```text
EC2_APP_DIR=/opt/futurex-reviewer
```

The EC2 compose stack runs only the API container. Postgres and Redis must be external services configured through `.env`.

Minimum EC2 `.env` values:

```env
DATABASE_URL=postgresql+asyncpg://user:password@external-postgres-host/db
REDIS_URL=redis://external-redis-host:6379/0
```

Deploy command used by CI/CD:

```bash
docker compose -f docker-compose.ec2.yml up -d --build
```
