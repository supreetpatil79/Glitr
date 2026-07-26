# Vercel Serverless Production Deployment Guide

This guide provides technical specifications and step-by-step operational instructions for deploying the **GlitrAI Mini Content Engine** to **Vercel** serverless architecture integrated with **Neon.tech Managed PostgreSQL**.

---

## 🏗️ Architecture & Serverless Adaptation

Vercel executes Python backend endpoints within ephemeral Serverless Functions (`@vercel/python`). The codebase includes the following production adaptations for serverless runtime compatibility:

1. **WSGI/ASGI Entrypoint (`api/index.py`)**: Exposes the root FastAPI application instance for Vercel's Serverless Function router.
2. **Routing Specification (`vercel.json`)**: Directs all incoming traffic (`/*`) to the ASGI entrypoint using rule rewrites.
3. **Read-Only Filesystem Resilience**: `main.py` and `services/imagegen.py` automatically detect read-only filesystems in serverless execution containers, gracefully serving external image URLs without filesystem write failures.

---

## 1. Managed Database Provisioning (Neon.tech)

Vercel functions do not maintain persistent local disk storage or local database processes. A managed PostgreSQL instance is required.

1. Create a project at **[Neon.tech](https://neon.tech)** (Free Tier).
2. Retrieve the PostgreSQL connection string from the Neon dashboard.
3. **Driver Format**: Ensure the connection string uses the `postgresql+asyncpg://` scheme required by SQLAlchemy's async engine:
   ```text
   postgresql+asyncpg://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require
   ```

---

## 2. Environment Configuration

The following environment variables must be declared in Vercel Project Settings:

| Parameter | Required | Description | Example / Format |
|---|---|---|---|
| `DATABASE_URL` | Yes | Async PostgreSQL connection string | `postgresql+asyncpg://user:pass@ep-xxx.neon.tech/neondb?sslmode=require` |
| `GROQ_API_KEY` | Yes | Groq API Key for LLM & Vision prompt generation | `gsk_your_groq_api_key_here` |
| `IMAGE_BACKEND` | No | Pluggable backend selector (`pollinations` \| `comfyui`) | `pollinations` (Default) |
| `COMFYUI_URL` | Optional | Live Cloudflare Tunnel URL for ComfyUI GPU worker | `https://xxxx.trycloudflare.com` |

---

## 3. Deployment Runbook

### Method A: Web Console (Recommended)

1. Push your repository to GitHub:
   ```bash
   git add -A
   git commit -m "chore: production release build"
   git push origin main
   ```
2. Navigate to **[Vercel Dashboard](https://vercel.com/new)** and click **Import Project**.
3. Select your repository.
4. Expand **Environment Variables** and input `DATABASE_URL` and `GROQ_API_KEY`.
5. Click **Deploy**. Vercel will automatically compile dependencies and launch the endpoint.

---

### Method B: Vercel CLI Execution

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. Authenticate and link project
vercel login

# 3. Configure environment variables
vercel env add DATABASE_URL production
vercel env add GROQ_API_KEY production

# 4. Execute production deployment
vercel --prod
```

---

## 🔬 Deployment Verification

Verify the live serverless deployment using `curl`:

```bash
# 1. System Health Check
curl -s https://<your-vercel-domain>.vercel.app/health
# Expected Output: {"status":"ok"}

# 2. Submit Generation Request
curl -s -X POST https://<your-vercel-domain>.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"product_name": "Matcha Tea", "description": "Ceremonial grade matcha"}'
# Expected Output: {"id":"<uuid>"}

# 3. Query Job Status
curl -s https://<your-vercel-domain>.vercel.app/jobs/<uuid>
```
