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
EC2_ENV_FILE
```

Use `EC2_ENV_FILE` to upload the production `.env` during deploy. If this secret is not set, the workflow expects `.env` to already exist in the app directory on EC2.

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
