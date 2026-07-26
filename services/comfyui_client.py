"""
services/comfyui_client.py — ComfyUI HTTP client for GlitrAI.

Full pipeline:
  1. Download reference image from URL
  2. Upload to ComfyUI /upload/image
  3. Load img2img_upscale_api.json, substitute __PROMPT__ / __IMAGE__, randomise seed
  4. POST workflow to /prompt → get prompt_id
  5. Poll /history/{prompt_id} until status.completed == True
  6. Find output image by scanning all output nodes for an "images" key
  7. Download via /view, save to static/results/{job_id}.jpg

IMPORTANT — COMFYUI_URL is the cloudflared tunnel URL printed by comfyui_setup.ipynb.
It changes every time the Colab runtime restarts. Update COMFYUI_URL in .env on each restart.
"""
import asyncio
import json
import logging
import os
import random
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_WORKFLOW_PATH = Path(__file__).parent.parent / "workflows" / "img2img_upscale_api.json"


# ---------------------------------------------------------------------------
# Step 1+2 — Upload reference image
# ---------------------------------------------------------------------------

async def _upload_image(
    client: httpx.AsyncClient,
    comfyui_url: str,
    image_url: str,
) -> str:
    """
    Download reference image bytes from image_url and upload to ComfyUI.
    Returns the filename ComfyUI assigned (used in LoadImage node).
    """
    logger.info("ComfyUI: fetching reference image from %s", image_url[:80])
    img_resp = await client.get(image_url)
    img_resp.raise_for_status()
    image_bytes = img_resp.content

    ext         = image_url.split("?")[0].rsplit(".", 1)[-1][:4].lower() or "jpg"
    upload_name = f"glitr_ref_{random.randint(10_000, 99_999)}.{ext}"

    logger.info("ComfyUI: uploading %s (%d bytes)", upload_name, len(image_bytes))
    up_resp = await client.post(
        f"{comfyui_url}/upload/image",
        files={"image": (upload_name, image_bytes, f"image/{ext}")},
        data={"overwrite": "true"},
    )
    up_resp.raise_for_status()
    filename = up_resp.json().get("name", upload_name)
    logger.info("ComfyUI: upload complete → %s", filename)
    return filename


# ---------------------------------------------------------------------------
# Step 3+4 — Build and submit workflow
# ---------------------------------------------------------------------------

async def _submit_workflow(
    client: httpx.AsyncClient,
    comfyui_url: str,
    prompt: str,
    image_filename: str,
) -> str:
    """
    Load API-format workflow, substitute __PROMPT__ and __IMAGE__,
    randomise the KSampler seed, POST to /prompt.
    Returns prompt_id.
    """
    if not _WORKFLOW_PATH.exists():
        raise FileNotFoundError(
            f"Workflow not found: {_WORKFLOW_PATH}. "
            "Make sure workflows/img2img_upscale_api.json is present."
        )

    # String-replace placeholders before JSON parsing to avoid escaping issues
    raw = _WORKFLOW_PATH.read_text(encoding="utf-8")
    # Escape the prompt for safe JSON embedding
    safe_prompt = prompt.replace("\\", "\\\\").replace('"', '\\"')
    raw = raw.replace('"__PROMPT__"', f'"{safe_prompt}"')
    raw = raw.replace('"__IMAGE__"',  f'"{image_filename}"')

    # Strip _comment keys (ComfyUI ignores them but cleaner to remove)
    workflow = json.loads(raw)
    for node in workflow.values():
        node.pop("_comment", None)

    # Randomise seed in KSampler (node "6")
    seed = random.randint(1, 2**31 - 1)
    workflow["6"]["inputs"]["seed"] = seed
    logger.info("ComfyUI: submitting workflow (seed=%d, image=%s)", seed, image_filename)

    payload  = {"prompt": workflow, "client_id": f"glitr_{random.randint(1000, 9999)}"}
    resp     = await client.post(f"{comfyui_url}/prompt", json=payload, timeout=30.0)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]
    logger.info("ComfyUI: workflow accepted → prompt_id=%s", prompt_id)
    return prompt_id


# ---------------------------------------------------------------------------
# Step 5 — Poll /history until completed
# ---------------------------------------------------------------------------

async def _poll_history(
    comfyui_url: str,
    prompt_id: str,
    timeout: int = 180,
    interval: float = 2.0,
) -> dict:
    """
    Poll GET /history/{prompt_id} until status.completed == True.
    Returns the history entry dict (contains "outputs" and "status").

    Verified response shape:
    {
      "<prompt_id>": {
        "outputs": {"<node_id>": {"images": [{"filename": "...", "subfolder": "", "type": "output"}]}},
        "status":  {"status_str": "success", "completed": true, "messages": [...]}
      }
    }
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        while loop.time() < deadline:
            resp = await client.get(f"{comfyui_url}/history/{prompt_id}")
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                entry  = history[prompt_id]
                status = entry.get("status", {})
                # Gate on completed flag — entry can appear before outputs are flushed
                if status.get("completed"):
                    if status.get("status_str") == "error":
                        messages = status.get("messages", [])
                        raise RuntimeError(f"ComfyUI job failed: {messages}")
                    logger.info("ComfyUI: job %s completed successfully", prompt_id)
                    return entry

            await asyncio.sleep(interval)

    raise TimeoutError(
        f"ComfyUI job {prompt_id} did not complete within {timeout}s. "
        "Check the ComfyUI console for errors."
    )


# ---------------------------------------------------------------------------
# Step 6+7 — Extract and download output image
# ---------------------------------------------------------------------------

def _find_output_images(outputs: dict) -> list[dict]:
    """
    Scan all output nodes for a key named 'images' (non-hardcoded node ID).
    Returns the images list from the first matching node.

    Robust against node ID renumbering — never hardcodes "10".
    """
    for node_id, node_output in outputs.items():
        if isinstance(node_output, dict) and "images" in node_output:
            images = node_output["images"]
            if images:
                logger.info("ComfyUI: found output images in node %s", node_id)
                return images
    raise RuntimeError(
        f"No 'images' key found in any ComfyUI output node. "
        f"Available output nodes: {list(outputs.keys())}"
    )


async def _download_output(
    client: httpx.AsyncClient,
    comfyui_url: str,
    history_entry: dict,
    job_id: str,
) -> str:
    """Download the first output image and save to static/results/{job_id}.jpg."""
    outputs = history_entry.get("outputs", {})
    images  = _find_output_images(outputs)

    img_info  = images[0]
    filename  = img_info["filename"]
    subfolder = img_info.get("subfolder", "")
    img_type  = img_info.get("type", "output")

    params = {"filename": filename, "type": img_type}
    if subfolder:
        params["subfolder"] = subfolder

    logger.info("ComfyUI: downloading output image '%s'", filename)
    resp = await client.get(f"{comfyui_url}/view", params=params, timeout=60.0)
    resp.raise_for_status()

    dest_dir = Path("static/results")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{job_id}.jpg"
    dest.write_bytes(resp.content)
    logger.info("ComfyUI: saved %d bytes → %s", len(resp.content), dest)
    return f"/static/results/{job_id}.jpg"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_and_save_comfyui(
    prompt: str,
    job_id: str,
    reference_image_url: str,
    comfyui_url: str,
) -> str:
    """
    Full ComfyUI img2img pipeline. Raises on any failure — caller handles it.

    Returns the static URL path: /static/results/{job_id}.jpg
    """
    comfyui_url = comfyui_url.rstrip("/")

    # Upload + submit (short-lived client, generous timeout for large images)
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        image_filename = await _upload_image(client, comfyui_url, reference_image_url)
        prompt_id      = await _submit_workflow(client, comfyui_url, prompt, image_filename)

    # Poll history (separate client — polling loop manages its own session)
    history_entry = await _poll_history(comfyui_url, prompt_id, timeout=180)

    # Download output
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        return await _download_output(client, comfyui_url, history_entry, job_id)
