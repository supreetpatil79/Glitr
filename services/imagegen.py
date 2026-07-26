"""
services/imagegen.py — Image generation backend with selectable provider.

IMAGE_BACKEND env var selects the provider:
  - "pollinations" (default): GET https://image.pollinations.ai/prompt/...
    No key required. Rate-limited to ~1 req/15s on anonymous tier.
  - "comfyui": POST to a live ComfyUI instance via its HTTP API.
    Requires COMFYUI_URL (the cloudflared tunnel URL from comfyui_setup.ipynb).
    Requires reference_image_url — this is an img2img workflow.
    Falls back to Pollinations with a warning if reference_image_url is absent.

Pollinations path is entirely unchanged and never removed.
"""
import logging
import os
import random
import urllib.parse
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

RESULTS_DIR    = Path("static/results")
IMAGE_BACKEND  = os.environ.get("IMAGE_BACKEND", "pollinations").lower().strip()


# ---------------------------------------------------------------------------
# Pollinations backend (original, unchanged)
# ---------------------------------------------------------------------------

async def _generate_pollinations(prompt: str, job_id: str) -> str:
    """Download from Pollinations.ai and save to static/results/{job_id}.jpg (or return URL on serverless)."""
    seed    = random.randint(1, 999_999)
    encoded = urllib.parse.quote(prompt, safe="")
    url     = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1024&nologo=true&seed={seed}"
    )

    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        dest = RESULTS_DIR / f"{job_id}.jpg"
        dest.write_bytes(response.content)
        return f"/static/results/{job_id}.jpg"
    except OSError:
        logger.info("Serverless filesystem detected (read-only); using direct Pollinations image URL.")
        return url


# ---------------------------------------------------------------------------
# Public entry point — IMAGE_BACKEND routing
# ---------------------------------------------------------------------------

async def generate_and_save_image(
    prompt: str,
    job_id: str,
    reference_image_url: str | None = None,
) -> str:
    """
    Generate and save a product image for the given job.

    Routes to ComfyUI if IMAGE_BACKEND=comfyui and reference_image_url is set.
    Falls back to Pollinations in all other cases.

    Returns the static URL path: /static/results/{job_id}.jpg
    """
    if IMAGE_BACKEND == "comfyui":
        if not reference_image_url:
            logger.warning(
                "IMAGE_BACKEND=comfyui requires reference_image_url for job %s — "
                "falling back to Pollinations (ComfyUI img2img needs a reference image).",
                job_id,
            )
        else:
            comfyui_url = os.environ.get("COMFYUI_URL", "").strip()
            if not comfyui_url:
                raise RuntimeError(
                    "IMAGE_BACKEND=comfyui but COMFYUI_URL is not set. "
                    "Run comfyui_setup.ipynb on Colab, copy the tunnel URL, "
                    "then set COMFYUI_URL in .env."
                )
            # Lazy import — keeps Pollinations path free of ComfyUI dependency
            from services.comfyui_client import generate_and_save_comfyui
            logger.info("Image backend: ComfyUI (%s)", comfyui_url[:50])
            return await generate_and_save_comfyui(
                prompt=prompt,
                job_id=job_id,
                reference_image_url=reference_image_url,
                comfyui_url=comfyui_url,
            )

    # Pollinations path — default and ComfyUI fallback
    logger.info("Image backend: Pollinations")
    return await _generate_pollinations(prompt, job_id)
