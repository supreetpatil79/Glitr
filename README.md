# GlitrAI — Mini Content Engine

An enterprise-grade, full-stack product content & image generation platform. Built with FastAPI, SQLAlchemy (AsyncPG), PostgreSQL, Groq Vision/LLM prompt engineering, and a pluggable image generation backend supporting both Pollinations.ai and ComfyUI (Stable Diffusion 1.5 + 4x-UltraSharp upscale pipeline).

---

## 🏛️ System Architecture

```text
                               +-----------------------------+
                               |     Web Client / SPA        |
                               |    (Static HTML/JS SPA)     |
                               +--------------+--------------+
                                              | REST API
                                              v
                               +--------------+--------------+
                               |    FastAPI Application      |
                               | (Local Uvicorn / Serverless)|
                               +-------+--------------+------+
                                       |              |
                      Async DB Session |              | BackgroundTasks
                                       v              v
                        +--------------+---+    +-----+-----------------------+
                        |   PostgreSQL     |    |   Pipeline Execution Engine |
                        | (AsyncPG / Neon) |    |   services/                 |
                        +------------------+    +--+---------------------+----+
                                                   |                     |
                                                   v                     v
                                      +------------+-------+ +-----------+-----------+
                                      |  Groq LLM Service  | | Image Backend Switch  |
                                      |  (Vision & Text)   | | (IMAGE_BACKEND)       |
                                      +--------------------+ +-----+-----------+-----+
                                                                   |           |
                                                                   v           v
                                                        +----------+--+     +--+----------+
                                                        | Pollinations|     |  ComfyUI    |
                                                        |   Engine    |     |  Colab GPU  |
                                                        +-------------+     +-------------+
```

---

## ⚡ Key Capabilities

- **Automated Prompt Engineering**: Converts raw product names and target audience descriptions into professional, multi-parameter photography prompts (lighting, composition, camera specs, UGC aesthetics) via **Groq LLM** (`llama-3.1-8b-instant`).
- **Multimodal Vision Integration**: Accepts optional reference image URLs, utilizing **Groq Vision** (`meta-llama/llama-4-scout-17b-16e-instruct`) to preserve brand color, packaging, and texture fidelity, with seamless fallback to text-only generation.
- **Dual Pluggable Image Backends**:
  - `pollinations` (Default): Instant zero-key image generation.
  - `comfyui`: Advanced Stable Diffusion 1.5 `img2img` (`denoise=0.6`) + `4x-UltraSharp` upscaling pipeline running on GPU (Google Colab T4) exposed via Cloudflare Tunnel.
- **Asynchronous Non-Blocking Pipeline**: FastAPI `BackgroundTasks` handle compute-heavy operations without blocking HTTP request threads.
- **Robust State Machine**: Strict job status tracking (`pending` → `processing` → `completed` | `failed`) with isolated database session management.
- **Deployment Flexibility**: Designed for Docker Compose local orchestration, serverless hosting on **Vercel**, and cloud deployment on **Render** with **Neon.tech** PostgreSQL.

---

## 📊 Job State Machine & Schema

### State Transitions

```text
[POST /generate] ──► PENDING ──► PROCESSING ──┬──► COMPLETED (Result Image URL set)
                                              └──► FAILED    (Error Message set)
```

### PostgreSQL `jobs` Table Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | Primary Key | Generated in Python (`uuid.uuid4`) |
| `product_name` | `VARCHAR/TEXT` | NOT NULL | Name of the product |
| `description` | `TEXT` | NOT NULL | Product details & target aesthetic |
| `reference_image_url` | `TEXT` | NULLABLE | Input product reference image URL |
| `generated_prompt` | `TEXT` | NULLABLE | Groq LLM engineered prompt |
| `status` | `ENUM` | NOT NULL | `pending`, `processing`, `completed`, `failed` |
| `result_image_url` | `TEXT` | NULLABLE | Path or URL to output image |
| `error_message` | `TEXT` | NULLABLE | Exception traceback summary on failure |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | Auto-generated UTC timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | Auto-updated UTC timestamp |

---

## 📡 API Specification

### 1. System Health Check
`GET /health`

**Response (`200 OK`)**:
```json
{
  "status": "ok"
}
```

---

### 2. Submit Generation Job
`POST /generate`

**Request Header**: `Content-Type: application/json`

**Request Payload**:
```json
{
  "product_name": "Cold Brew Coffee",
  "description": "Smooth cold brew concentrate in a matte black bottle for urban professionals.",
  "reference_image_url": "https://example.com/reference.jpg"
}
```

**Response (`202 Accepted`)**:
```json
{
  "id": "17b42fa8-91a9-453b-a4ce-c4af789c7a12"
}
```

---

### 3. Fetch Job by ID
`GET /jobs/{job_id}`

**Response (`200 OK`)**:
```json
{
  "id": "17b42fa8-91a9-453b-a4ce-c4af789c7a12",
  "product_name": "Cold Brew Coffee",
  "description": "Smooth cold brew concentrate in a matte black bottle for urban professionals.",
  "reference_image_url": "https://example.com/reference.jpg",
  "generated_prompt": "Subject: a sleek, matte black bottle of Cold Brew Coffee... Technical style: shot on Sony A7IV, 85mm f/1.8...",
  "status": "completed",
  "result_image_url": "/static/results/17b42fa8-91a9-453b-a4ce-c4af789c7a12.jpg",
  "error_message": null,
  "created_at": "2026-07-24T15:23:51.987002+00:00",
  "updated_at": "2026-07-24T15:23:59.820359+00:00"
}
```

---

### 4. List All Jobs
`GET /jobs`

**Response (`200 OK`)**: Array of job objects sorted newest first (`created_at DESC`).

---

## 🛠️ Environment Configuration

Copy `.env.example` to `.env` and populate the required parameters:

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://glitr:glitr@db:5432/glitrdb

# Groq API Configuration (https://console.groq.com)
GROQ_API_KEY=gsk_your_groq_api_key_here

# Pluggable Image Generation Backend ("pollinations" | "comfyui")
IMAGE_BACKEND=pollinations

# ComfyUI Tunnel URL (Required only if IMAGE_BACKEND=comfyui)
COMFYUI_URL=https://your-cloudflared-tunnel.trycloudflare.com
```

---

## 🚀 Deployment & Local Setup Runbook

### Option A: Docker Compose Orchestration (Recommended for Local Dev)

```bash
# 1. Clone repository
git clone https://github.com/your-org/GlitrAi.git
cd GlitrAi

# 2. Configure environment
cp .env.example .env

# 3. Build & start containers
docker compose up --build -d

# 4. Verify deployment
curl -s http://localhost:8000/health
```

Access Web UI at `http://localhost:8000`.

---

### Option B: Serverless Deployment on Vercel

The application is pre-configured for Vercel Serverless execution via `vercel.json` and `api/index.py`.

1. Create a free PostgreSQL database at **[Neon.tech](https://neon.tech)**.
2. Set `DATABASE_URL` in Vercel project settings using `postgresql+asyncpg://` format.
3. Add `GROQ_API_KEY` in Vercel environment variables.
4. Deploy:
   ```bash
   vercel --prod
   ```
For complete details, see **[`VERCEL_DEPLOYMENT_GUIDE.md`](VERCEL_DEPLOYMENT_GUIDE.md)**.

---

### Option C: Bare-Metal Local Python Execution

```bash
# 1. Initialize Python environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Export environment variables
export DATABASE_URL="postgresql+asyncpg://glitr:glitr@localhost:5432/glitrdb"
export GROQ_API_KEY="gsk_..."

# 4. Launch Uvicorn server
uvicorn main:app --reload --port 8000
```

---

## 🎨 ComfyUI GPU Workflow Engine (Assignment 2)

For advanced photorealistic generation using Stable Diffusion 1.5:

1. Open [`comfyui_setup.ipynb`](comfyui_setup.ipynb) in **Google Colab** with a **T4 GPU** runtime.
2. Execute all notebook cells to:
   - Load `ComfyUI` engine.
   - Download `Realistic_Vision_V5.1_fp16-no-ema` checkpoint.
   - Download dedicated `vae-ft-mse-840000-ema-pruned` VAE.
   - Download `4x-UltraSharp` model.
   - Launch Cloudflare Tunnel (`cloudflared`).
3. Copy the output `trycloudflare.com` URL into `.env`:
   ```bash
   IMAGE_BACKEND=comfyui
   COMFYUI_URL=https://xxxx.trycloudflare.com
   ```
4. Load workflow templates:
   - UI Interactive Graph: [`workflows/img2img_upscale.json`](workflows/img2img_upscale.json)
   - API JSON Format: [`workflows/img2img_upscale_api.json`](workflows/img2img_upscale_api.json)

---

## 📁 Repository Structure

```text
GlitrAi/
├── api/
│   └── index.py                 # Vercel Serverless entrypoint
├── services/
│   ├── llm.py                   # Groq Vision & Text prompt engineering
│   ├── imagegen.py              # Pluggable backend router
│   └── comfyui_client.py        # ComfyUI HTTP client & workflow runner
├── static/
│   ├── index.html               # Production Single Page Application (UI)
│   └── results/                 # Output image storage
├── workflows/
│   ├── img2img_upscale.json     # ComfyUI UI graph template
│   └── img2img_upscale_api.json # ComfyUI API execution schema
├── comfyui_setup.ipynb          # Google Colab GPU provisioner & tunnel script
├── db.py                        # Async SQLAlchemy engine & session manager
├── models.py                    # SQLAlchemy ORM models
├── main.py                      # FastAPI application & BackgroundTask engine
├── Dockerfile                   # Application container definition
├── docker-compose.yml           # Local multi-container stack
├── vercel.json                  # Vercel Serverless routing schema
├── VERCEL_DEPLOYMENT_GUIDE.md   # Production Vercel deployment manual
└── requirements.txt             # Dependency declarations
```

---

## 📄 License & Maintainers

Maintained under MIT License. Standard production architecture designed for performance, modularity, and seamless cloud scalability.
