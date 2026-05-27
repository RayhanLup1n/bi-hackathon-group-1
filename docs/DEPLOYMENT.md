# Deployment Guide - R.A.D.A.R Pangan

Panduan deployment untuk demo dan production.

## Exposed Ports

| Service | Port | Description | Profile |
|---------|------|-------------|---------|
| FastAPI App | 8000 | Backend API + Frontend | default |
| ML Engine | 8001 | ML Inference Server | `--profile ml` |
| Kestra UI | 8080 | ETL Orchestrator | `--profile etl` |

## Quick Start

### Development (Local)

```bash
# 1. Setup environment
cp .envs/.env.example .envs/.env
# Edit .envs/.env with your credentials

# 2. GCP Authentication (for BigQuery)
gcloud auth application-default login

# 3. Run app only
uv run uvicorn main:app --reload --port 8000
```

### Docker Deployment

```bash
# App only
docker compose up app

# App + ML Engine
docker compose --profile ml up

# App + ETL Pipeline
docker compose --profile etl up

# Everything
docker compose --profile ml --profile etl up
```

## Deployment Options ($0 Cost)

### Option 1: Railway (Recommended for Demo)

**Pros**: Free tier, easy setup, auto-deploy from GitHub
**Cons**: 500 hours/month limit, sleeps after inactivity

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login & deploy
railway login
railway init
railway up
```

**Environment Variables** (set in Railway dashboard):
- `SUPABASE_HOST`, `SUPABASE_PORT`, `SUPABASE_DB`, `SUPABASE_USER`, `SUPABASE_PASSWORD`
- `GCP_PROJECT`, `BQ_LOCATION`
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`

### Option 2: Render

**Pros**: Free tier, Docker support, auto-deploy
**Cons**: Sleeps after 15 min inactivity, cold start ~30s

1. Connect GitHub repo to Render
2. Create Web Service from `Dockerfile`
3. Set environment variables
4. Deploy

### Option 3: Fly.io

**Pros**: Free tier (3 shared VMs), global edge deployment
**Cons**: Requires credit card for verification

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Deploy
fly launch
fly deploy
```

### Option 4: Google Cloud Run (GCP Free Tier)

**Pros**: 2M requests/month free, auto-scaling, native GCP integration
**Cons**: Cold start, requires GCP account

```bash
# Build & push to Container Registry
gcloud builds submit --tag gcr.io/radar-pangan-hackathon/app

# Deploy
gcloud run deploy radar-pangan \
  --image gcr.io/radar-pangan-hackathon/app \
  --platform managed \
  --region asia-southeast2 \
  --allow-unauthenticated
```

## Demo Day Setup

### Recommended: Railway + Supabase

1. **Database**: Already on Supabase (free tier)
2. **App**: Deploy to Railway
3. **ML**: Include in same Railway deployment or skip for demo

### Pre-Demo Checklist

- [ ] Test login flow
- [ ] Verify dashboard loads data
- [ ] Check prediksi page works
- [ ] Confirm admin page accessible
- [ ] Test on mobile browser

### Demo Credentials

```
Admin:    admin / Admin1234
Analyst:  analyst / Analyst1234
Viewer:   viewer / Viewer1234
```

## Environment Variables

### Required

```env
# PostgreSQL (Supabase)
SUPABASE_HOST=db.xxx.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<password>

# GCP (BigQuery)
GCP_PROJECT=radar-pangan-hackathon
BQ_LOCATION=asia-southeast2
```

### Optional (ML Engine)

```env
# Groq LLM
LLM_API_KEY=gsk_xxx
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

## Troubleshooting

### App won't start
- Check `.envs/.env` exists and has correct values
- Verify Supabase connection: `psql $DATABASE_URL`

### ML Engine offline
- Run with `--profile ml`: `docker compose --profile ml up`
- Check `LLM_API_KEY` is set

### BigQuery errors
- Run `gcloud auth application-default login`
- Verify project: `gcloud config get-value project`

### Port conflicts
- Change port mapping in `docker-compose.yml`
- Or use different host ports: `"8080:8000"` instead of `"8000:8000"`

## Security Notes

- Never commit `.env` files
- Use environment variables for all secrets
- Enable HTTPS in production (Railway/Render handle this automatically)
- JWT tokens expire after 8 hours
