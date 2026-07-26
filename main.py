"""
main.py — GlitrAI Mini Content Engine
FastAPI application with BackgroundTasks-based async job processing.
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, update

from db import AsyncSessionLocal, get_session, init_db
from models import Job, JobStatus
from services.imagegen import generate_and_save_image
from services.llm import generate_image_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
RESULTS_DIR = STATIC_DIR / "results"

try:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database…")
    try:
        await init_db()
        logger.info("Database ready.")
    except Exception as exc:
        logger.warning("Database startup init warning: %s", exc)
    yield
    logger.info("Shutting down.")


app = FastAPI(title="GlitrAI Mini Content Engine", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Global exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)}"}
    )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


from typing import Optional

class GenerateRequest(BaseModel):
    product_name: str
    description: str
    reference_image_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def run_generation_job(job_id: uuid.UUID) -> None:
    """
    End-to-end generation pipeline:
      1. Mark job processing
      2. Generate prompt via Groq LLM
      3. Generate image via Pollinations and save locally
      4. Mark job completed (or failed on any exception)
    """
    logger.info("Starting generation job %s", job_id)

    # Step 1 — status = processing
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=JobStatus.processing)
        )
        await session.commit()

    try:
        # Fetch job data
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one()
            product_name = job.product_name
            description = job.description
            ref_url = job.reference_image_url  # None when not supplied

        # Step 2 — generate prompt via Groq (vision if ref_url, else text-only)
        logger.info("Job %s: calling Groq LLM (ref_url=%s)…", job_id, bool(ref_url))
        prompt = await generate_image_prompt(product_name, description, ref_url)
        logger.info("Job %s: prompt generated (%d chars)", job_id, len(prompt))

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(generated_prompt=prompt)
            )
            await session.commit()

        # Step 3 — generate image via Pollinations
        logger.info("Job %s: calling Pollinations…", job_id)
        image_url = await generate_and_save_image(prompt, str(job_id), ref_url)
        logger.info("Job %s: image saved at %s", job_id, image_url)

        # Step 4 — mark completed
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.completed, result_image_url=image_url)
            )
            await session.commit()

        logger.info("Job %s: COMPLETED", job_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s FAILED: %s", job_id, exc)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.failed, error_message=str(exc))
            )
            await session.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate", status_code=202)
async def generate(payload: GenerateRequest, background_tasks: BackgroundTasks):
    """Create a generation job and kick it off in the background."""
    try:
        await init_db()
    except Exception as exc:
        logger.warning("init_db in /generate: %s", exc)

    async with get_session() as session:
        job = Job(
            product_name=payload.product_name,
            description=payload.description,
            reference_image_url=payload.reference_image_url,
            status=JobStatus.pending,
        )
        session.add(job)
        await session.flush()  # get the generated id before commit
        job_id = job.id

    if os.environ.get("VERCEL"):
        await run_generation_job(job_id)
    else:
        background_tasks.add_task(run_generation_job, job_id)

    logger.info("Enqueued job %s for '%s'", job_id, payload.product_name)
    return {"id": str(job_id)}


@app.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID):
    """Return the full job row as JSON."""
    try:
        await init_db()
    except Exception:
        pass

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(job.to_dict())


@app.get("/jobs")
async def list_jobs():
    """Return all jobs, newest first."""
    try:
        await init_db()
    except Exception:
        pass

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Job).order_by(Job.created_at.desc())
        )
        jobs = result.scalars().all()
    return JSONResponse([j.to_dict() for j in jobs])


# ---------------------------------------------------------------------------
# Static files (must be mounted AFTER route definitions)
# ---------------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

from fastapi.responses import FileResponse  # noqa: E402


@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "GlitrAI API Live", "health": "/health"}
