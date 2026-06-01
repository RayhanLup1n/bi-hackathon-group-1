# Deployment Guide - R.A.D.A.R Pangan

Panduan deployment ke Railway untuk demo dan production.

## Architecture Overview

```
Railway Project
  |
  +-- Service: app (FastAPI + Frontend)     port $PORT
  +-- Service: ml-model (ML Inference)      port $PORT
  +-- Service: kestra (ETL Orchestrator)    port $PORT
  +-- Service: kestra-postgres (PostgreSQL) internal only
  |
  +-- External: Supabase PostgreSQL (Gold layer DB)
  +-- External: BigQuery (Bronze + Silver, via Service Account)
```

## Exposed Ports

| Service | Local Port | Railway | Description |
|---------|-----------|---------|-------------|
| FastAPI App | 8000 | `$PORT` (auto) | Backend API + Frontend |
| ML Engine | 8001 | `$PORT` (auto) | ML Inference Server |
| Kestra UI | 8080 | `$PORT` (auto) | ETL Orchestrator |
| Kestra DB | 5432 | internal | Kestra metadata store |

> Railway assigns `$PORT` dynamically. Each service gets its own public URL.

## Railway Deployment (Step-by-Step)

### Prerequisites

- Railway account (free trial: $5 credit)
- GitHub repo connected to Railway
- GCP Service Account JSON (for BigQuery)
- Supabase credentials

### Step 1: Create Railway Project

```bash
# Option A: Via CLI
npm install -g @railway/cli
railway login
railway init

# Option B: Via Dashboard
# https://railway.app/new → Deploy from GitHub repo
```

### Step 2: Create Services (4 total)

#### Service 1: App (auto-created from repo)

- **Root directory**: `/` (project root)
- **Dockerfile**: `Dockerfile`
- **Config**: uses `railway.toml` automatically
- **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

#### Service 2: ML Model

1. Railway Dashboard → Project → **New Service** → **Docker**
2. Connect same GitHub repo
3. Settings:
   - **Root directory**: `/ml`
   - **Dockerfile path**: `Dockerfile`
   - **Start command**: `uvicorn ml.serve.api:app --host 0.0.0.0 --port $PORT`

#### Service 3: Kestra PostgreSQL

1. Railway Dashboard → **New Service** → **Database** → **PostgreSQL**
2. Or: **New Service** → **Docker Image** → `postgres:16-alpine`
3. Environment variables:
   ```
   POSTGRES_USER=kestra
   POSTGRES_PASSWORD=kestra
   POSTGRES_DB=kestra
   ```

#### Service 4: Kestra Orchestrator

1. Railway Dashboard → **New Service** → **Docker**
2. Connect same GitHub repo
3. Settings:
   - **Root directory**: `/etl/kestra`
   - **Dockerfile path**: `Dockerfile`
   - **Start command**: `server standalone --worker-thread=128`
4. Set `KESTRA_CONFIGURATION` env var (see Environment Variables below)

### Step 3: Set Environment Variables

#### App Service (Required)

```env
# PostgreSQL (Supabase - Gold layer)
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>

# JWT (production secret, min 32 chars)
JWT_SECRET=<generated-secret>

# GCP BigQuery (base64-encoded service account JSON)
GOOGLE_CREDENTIALS_BASE64=<base64-string>
GCP_PROJECT=radar-pangan-hackathon
BQ_LOCATION=asia-southeast2

# API Docs (enable for demo)
ENABLE_DOCS=true

# CORS (Railway auto-generates domain)
CORS_ORIGINS=https://<app-name>.up.railway.app

# ML server URL (Railway internal networking)
ML_SERVER_URL=http://<ml-service-name>.railway.internal:<ml-port>
```

#### ML Model Service

```env
# Supabase (for persisting predictions)
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>

# LLM for Lapis 3 reasoning (optional)
LLM_API_KEY=<api-key>
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=google/gemini-2.5-flash
```

#### Kestra Service

```env
KESTRA_CONFIGURATION=|
  datasources:
    postgres:
      url: jdbc:postgresql://<kestra-db>.railway.internal:5432/kestra
      driver-class-name: org.postgresql.Driver
      username: kestra
      password: kestra
  kestra:
    security:
      basic-auth:
        enabled: true
        username: admin@radar-pangan.local
        password: "Admin1234"
    repository:
      type: postgres
    storage:
      type: local
      local:
        base-path: "/app/storage"
    queue:
      type: postgres

GCP_PROJECT=radar-pangan-hackathon
BQ_LOCATION=asia-southeast2
GOOGLE_CREDENTIALS_BASE64=<base64-string>
```

### Step 4: Generate GCP Service Account

```bash
# 1. Create service account
gcloud iam service-accounts create radar-pangan-sa \
  --display-name="R.A.D.A.R Pangan Railway"

# 2. Grant BigQuery access
gcloud projects add-iam-policy-binding radar-pangan-hackathon \
  --member="serviceAccount:radar-pangan-sa@radar-pangan-hackathon.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding radar-pangan-hackathon \
  --member="serviceAccount:radar-pangan-sa@radar-pangan-hackathon.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# 3. Download JSON key
gcloud iam service-accounts keys create gcp-sa-key.json \
  --iam-account=radar-pangan-sa@radar-pangan-hackathon.iam.gserviceaccount.com

# 4. Base64 encode (for Railway env var)
# PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("gcp-sa-key.json"))

# Linux/macOS:
base64 -w 0 gcp-sa-key.json

# 5. Paste the base64 string as GOOGLE_CREDENTIALS_BASE64 in Railway

# 6. DELETE the local JSON key file (security!)
del gcp-sa-key.json
```

### Step 5: Railway Internal Networking

Railway services communicate via internal URLs:

```
http://<service-name>.railway.internal:<port>
```

Set `ML_SERVER_URL` in App service to point to ML service's internal URL.
Find the internal URL in Railway Dashboard → ML service → Settings → Networking.

### Step 6: Deploy

```bash
# Push to GitHub triggers auto-deploy
git push origin feat/workflow-integration

# Or manual deploy via CLI
railway up
```

## Pre-Demo Checklist

- [ ] All 4 Railway services are **Active** (green)
- [ ] App health check passes: `curl https://<app>.up.railway.app/health`
- [ ] ML health check passes: `curl https://<ml>.up.railway.app/health`
- [ ] Login flow works (admin / Admin1234)
- [ ] Dashboard loads price data from Supabase
- [ ] Dashboard shows ML predictions (or graceful "ML offline" fallback)
- [ ] RCA + Bowtie analysis works
- [ ] Prediksi page loads
- [ ] Admin page accessible (admin only)
- [ ] Swagger docs accessible: `https://<app>.up.railway.app/docs`
- [ ] Kestra UI accessible: `https://<kestra>.up.railway.app`
- [ ] Test on mobile browser
- [ ] Check Railway usage (stay within $5 credit)

## Demo Credentials

```
Admin:    admin / Admin1234
Analyst:  analyst / Analyst1234
Viewer:   viewer / Viewer1234
```

## Troubleshooting

### App won't start
- Check Railway logs for `RuntimeError: JWT_SECRET env var is required`
- Verify Supabase connection string is correct
- Check `ENABLE_DOCS=true` if Swagger needed

### ML Engine offline
- Check ML service logs in Railway dashboard
- Verify `ML_SERVER_URL` uses `.railway.internal` (not localhost)
- App works without ML (graceful degradation)

### BigQuery errors
- Check `GOOGLE_CREDENTIALS_BASE64` is valid base64
- Verify service account has `bigquery.dataViewer` + `bigquery.jobUser` roles
- Non-critical: app works without BigQuery (Gold layer is PostgreSQL)

### Kestra can't connect to its PostgreSQL
- Use Railway internal URL for the database connection
- Verify kestra-postgres service is healthy

### CORS errors in browser
- Add your Railway app URL to `CORS_ORIGINS` env var
- Format: `https://<app-name>.up.railway.app`

### Railway credit running low
- Check usage: Railway Dashboard → Usage
- Free trial: $5 credit
- Tip: scale down idle services after demo

## Security Notes

- Never commit `.env` files or GCP JSON keys
- Use Railway's encrypted environment variables
- JWT tokens expire after 8 hours
- HTTPS is automatic on Railway
- Delete GCP service account key file after base64 encoding
- Rotate JWT_SECRET if compromised
