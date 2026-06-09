# Deployment Guide

Target stack: **Railway** (backend + Postgres) · **AWS S3** (file storage) · **Vercel** (frontend)

---

## 1. Prerequisites

- Docker Desktop installed and running
- Railway account + CLI (`npm install -g @railway/cli`)
- Vercel account + CLI (`npm install -g vercel`)
- AWS account with an S3 bucket and an IAM user (see §4)
- GitHub repo with `main` as the production branch

---

## 2. Dockerise the Backend

### `Dockerfile` (project root)

```dockerfile
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "5000"]
```

### `.dockerignore` (project root)

```
.env*
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
tests/
logs/
data/local/
.git/
*.md
```

### Test the build locally

```bash
# Build
docker build -t docuchat-backend .

# Run with your dev env vars
docker run --rm -p 5000:5000 --env-file .env.dev docuchat-backend

# Confirm health check responds
curl http://localhost:5000/api/health
```

---

## 3. Set Up Railway Project

```bash
railway login
railway init          # creates a new project
railway up            # first manual deploy to confirm it works
```

In the Railway dashboard:
1. **Add a PostgreSQL plugin** to your project (Railway → New → Database → PostgreSQL)
2. Copy the `DATABASE_URL` it generates — you'll need it in §5

---

## 4. Set Up AWS S3 + IAM

1. In the AWS Console go to **IAM → Users → Create user**
2. Attach an inline policy scoped to your bucket only:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    }
  ]
}
```

3. Generate **Access keys** for the user and save the key ID + secret — you'll add them in §5

---

## 5. Configure Production Environment Variables

Set these in the Railway dashboard under your service → **Variables**.
Do not use a `.env` file in the container.

| Variable | Value |
|---|---|
| `ENV` | `production` |
| `PORT` | `5000` |
| `HOST` | `0.0.0.0` |
| `DATABASE_URL` | from Railway Postgres plugin |
| `USER_SESSION_SECRET` | strong random string (e.g. `openssl rand -hex 32`) |
| `ANON_SESSION_COOKIE_SECURE` | `True` |
| `ANON_SESSION_COOKIE_DOMAIN` | your API domain |
| `CORS_ORIGINS` | `["https://your-frontend-domain.com"]` |
| `LOG_LEVEL` | `INFO` |
| `OPENAI_API_KEY` | your key |
| `SEARCH_API_KEY` | your key |
| `SEARCH_ENGINE_ID` | your engine ID |
| `AWS_REGION` | `eu-west-2` |
| `AWS_S3_BUCKET_NAME` | your bucket name |
| `AWS_ACCESS_KEY_ID` | from IAM user |
| `AWS_SECRET_ACCESS_KEY` | from IAM user |
| `IS_WEB_SEARCH_ENABLED` | `False` |
| `LLM_MODEL_NAME` | `gpt-3.5-turbo` |
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` |
| `LLM_TEMPERATURE` | `0.7` |

---

## 6. Set Up the Database (pgvector + Migrations)

### Enable pgvector on Railway Postgres

Connect to your Railway Postgres instance:

```bash
railway connect PostgreSQL
```

Then run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Run Alembic migrations

```bash
# Point at the prod DATABASE_URL
export DATABASE_URL="<your-railway-postgres-url>"

alembic upgrade head
```

You can also add this as a Railway deploy command so it runs automatically on each deploy:  
**Settings → Deploy → Start command:**
```
alembic upgrade head && uvicorn src.api.server:app --host 0.0.0.0 --port 5000
```

---

## 7. CD Pipeline — Backend

Create `.github/workflows/deploy-backend.yml`:

```yaml
name: Deploy Backend

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy to Railway
        run: railway up --service docuchat-backend --detach
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

**Setup:**
1. Get your Railway token: `railway whoami --token` or the Railway dashboard → Account → Tokens
2. Add it as a GitHub secret: `Settings → Secrets → RAILWAY_TOKEN`

---

## 8. Frontend — Vercel

### Deploy

```bash
cd ../docuchat-frontend
vercel --prod
```

Or connect the repo in the Vercel dashboard for automatic deploys on push.

### Environment variables (Vercel dashboard → Settings → Environment Variables)

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://your-railway-backend-url.up.railway.app/api` |

> Adjust the variable name to match what your frontend uses to call the API.

### CORS

Once you have the Vercel domain, update the `CORS_ORIGINS` variable in Railway to include it:

```
CORS_ORIGINS=["https://your-app.vercel.app"]
```

---

## 9. Verify the Deployment

```bash
# Health check
curl https://your-backend.up.railway.app/api/health

# Check the frontend loads and can reach the API
# Open browser → Network tab → confirm /api calls return 200
```

---

## Deployment Checklist

- [ ] `Dockerfile` and `.dockerignore` committed
- [ ] Container builds and runs locally with `.env.dev`
- [ ] Railway project created with Postgres plugin
- [ ] pgvector extension enabled on Railway Postgres
- [ ] Alembic migrations run against prod DB
- [ ] All env vars set in Railway dashboard
- [ ] IAM user created with least-privilege S3 policy
- [ ] `RAILWAY_TOKEN` secret added to GitHub
- [ ] GitHub Actions workflow committed to `main`
- [ ] Vercel project connected with `VITE_API_URL` set
- [ ] `CORS_ORIGINS` updated to include Vercel domain
- [ ] End-to-end test: upload a doc, send a chat message
