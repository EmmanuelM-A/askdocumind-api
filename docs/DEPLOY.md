# Deployment Guide

Target stack: **Railway** (backend + Postgres) · **AWS S3** (file storage) · **Vercel** (frontend)

---

## 1. Prerequisites

- Docker Desktop installed and running
- Railway account (railway.app)
- Vercel account (vercel.com)
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

# Run (override DATABASE_URL so Docker can reach your local Postgres)
docker run --rm -p 5000:5000 --env-file .env.dev \
  -e DATABASE_URL=postgresql+asyncpg://docu_chat:secret@host.docker.internal:5432/docu_chat_postgres \
  docuchat-backend

# Confirm health check responds
curl http://localhost:5000/api/health/api
```

---

## 3. Set Up Railway Project

### 3a. Create the project

1. Go to **railway.app** and sign in
2. Click **New Project → Deploy from GitHub repo**
3. Authorise Railway to access your GitHub account if prompted, then select your backend repo
4. Railway will detect the `Dockerfile` automatically — leave settings as-is and click **Deploy**

> Railway will attempt a first deploy now. It will fail because env vars aren't set yet — that's expected. Continue to §3b.

### 3b. Add a Postgres database

1. Inside your project, click **+ New** (top right of the project canvas)
2. Choose **Database → Add PostgreSQL**
3. Railway provisions Postgres and wires a `DATABASE_URL` variable into your project automatically

### 3c. Note your backend URL

After the first successful deploy (once env vars are set in §5), Railway assigns a public URL to your backend service. Find it under your backend service → **Settings → Networking → Public domain**. It looks like `https://docuchat-backend-production-xxxx.up.railway.app`. You'll need this for the frontend in §8.

---

## 4. Set Up AWS S3 + IAM

1. In the AWS Console go to **IAM → Users → Create user**
2. On the **Permissions** step, choose **Attach policies directly → Create inline policy**, then paste:

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

3. After creating the user, go to the user → **Security credentials → Access keys → Create access key**
4. Choose **Application running outside AWS**, then download the CSV — you'll add the key ID and secret in §5

---

## 5. Configure Production Environment Variables

In the Railway dashboard, click your **backend service** → **Variables** tab → **+ New Variable** for each row below.

| Variable | Value |
|---|---|
| `ENV` | `production` |
| `PORT` | `5000` |
| `HOST` | `0.0.0.0` |
| `DATABASE_URL` | auto-set by Railway Postgres — verify it appears under Variables |
| `USER_SESSION_SECRET` | a strong random string — generate one with `openssl rand -hex 32` in your terminal |
| `ANON_SESSION_COOKIE_SECURE` | `True` |
| `ANON_SESSION_COOKIE_DOMAIN` | your Railway backend domain (from §3c) |
| `CORS_ORIGINS` | `["https://your-vercel-app.vercel.app"]` — update after §8 |
| `LOG_LEVEL` | `INFO` |
| `OPENAI_API_KEY` | your key |
| `IS_WEB_SEARCH_ENABLED` | `False` |
| `SEARCH_API_KEY` | your Google key |
| `SEARCH_ENGINE_ID` | your engine ID |
| `AWS_REGION` | `eu-west-2` |
| `AWS_S3_BUCKET_NAME` | your bucket name |
| `AWS_ACCESS_KEY_ID` | from IAM user (§4) |
| `AWS_SECRET_ACCESS_KEY` | from IAM user (§4) |
| `LLM_MODEL_NAME` | `gpt-3.5-turbo` |
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` |
| `LLM_TEMPERATURE` | `0.7` |

Once all variables are saved, Railway will automatically redeploy the service.

---

## 6. Set Up the Database (pgvector + Migrations)

### 6a. Enable pgvector

1. In your Railway project, click the **Postgres** service
2. Go to the **Query** tab
3. Run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 6b. Run Alembic migrations

Railway can run migrations automatically on every deploy. In your **backend service**:

1. Go to **Settings → Deploy → Custom start command**
2. Set it to:

```
alembic upgrade head && uvicorn src.api.server:app --host 0.0.0.0 --port 5000
```

This runs migrations before the server starts on every deploy — safe to run repeatedly.

> **First-time only:** trigger a manual redeploy after setting this. Click **Deployments → Redeploy** on the latest deployment.

---

## 7. CD Pipeline — Auto-Deploy on Push

Railway's GitHub integration handles this without any extra tooling.

1. In your backend service, go to **Settings → Source**
2. Confirm the connected repo and branch are correct (`main`)
3. Make sure **Auto-deploy** is toggled on

Every push to `main` will now trigger a Railway build and deploy automatically.

### Optional: GitHub Actions for more control

If you want deploy status visible in GitHub pull requests, create `.github/workflows/deploy-backend.yml`:

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

      - name: Deploy to Railway
        uses: bervProject/railway-deploy@main
        with:
          railway_token: ${{ secrets.RAILWAY_TOKEN }}
          service: docuchat-backend
```

**Getting the Railway token:**
1. railway.app → click your **avatar (top right) → Account Settings**
2. Go to the **Tokens** tab → **Create Token**
3. Copy the token

**Adding it to GitHub:**
1. Your repo on github.com → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**, name it `RAILWAY_TOKEN`, paste the value

---

## 8. Frontend — Vercel

### 8a. Create the Vercel project

1. Go to **vercel.com** and sign in
2. Click **Add New → Project**
3. Click **Import** next to your frontend GitHub repo (authorise Vercel if prompted)
4. Leave the build settings as auto-detected, then click **Deploy**

### 8b. Set environment variables

1. After the initial deploy, go to your project → **Settings → Environment Variables**
2. Add:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://your-railway-backend-url.up.railway.app/api` |

> Adjust the variable name to match what your frontend uses to call the API.

3. Go to **Deployments** and click **Redeploy** on the latest deployment so the new variable takes effect

### 8c. Update CORS on Railway

Now that you have your Vercel domain (e.g. `your-app.vercel.app`), go back to your Railway backend service → **Variables** and update:

```
CORS_ORIGINS=["https://your-app.vercel.app"]
```

Railway will redeploy automatically.

---

## 9. Verify the Deployment

Open your browser or run from your terminal:

```bash
# Backend health check
curl https://your-backend.up.railway.app/api/health/api

# Frontend
# Open https://your-app.vercel.app in a browser
# Open DevTools → Network tab → confirm /api calls return 200
```

---

## Deployment Checklist

- [x] `Dockerfile` and `.dockerignore` committed
- [x] Container builds and runs locally with `.env.dev`
- [ ] Railway project created and connected to GitHub repo
- [ ] Railway Postgres database added to project
- [ ] pgvector extension enabled via Railway Query tab
- [ ] All env vars set in Railway Variables tab
- [ ] Custom start command set (runs Alembic + uvicorn)
- [ ] IAM user created with least-privilege S3 policy
- [ ] Vercel project created and connected to frontend repo
- [ ] `VITE_API_URL` set in Vercel environment variables
- [ ] `CORS_ORIGINS` updated to include Vercel domain
- [ ] End-to-end test: upload a doc, send a chat message
