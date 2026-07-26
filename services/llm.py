"""
services/llm.py — Generate a detailed text-to-image prompt using Groq.

Two paths:
  - reference_image_url is None  → text-only call, model: llama-3.1-8b-instant
  - reference_image_url is set   → multimodal/vision call,
                                   model: meta-llama/llama-4-scout-17b-16e-instruct
    If the vision call fails for any reason (bad URL, unsupported format, model
    error), it logs a warning and falls back to the text-only path so the job
    doesn't fail just because of a bad reference image.
"""
import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Models
_TEXT_MODEL   = "llama-3.1-8b-instant"
_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY", "")
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


SYSTEM_PROMPT = """You are an expert product photography art director specialising in \
UGC (user-generated content) and lifestyle product shots.

When given a product name and description (and optionally a reference image), produce \
exactly ONE detailed, comma-separated text-to-image prompt (no prose, no preamble, \
no markdown, just the prompt itself) that describes:
- Subject: the exact product, prominently featured
- Composition: rule of thirds, flatlay OR over-the-shoulder lifestyle
- Lighting: soft natural window light or golden-hour glow, minimal shadows
- Background: clean, contextually relevant lifestyle setting
- Mood/Aesthetic: aspirational, editorial, premium
- Technical style: shot on Sony A7IV, 85mm f/1.8, shallow depth of field, \
  photo-realistic, ultra-detailed, 8K

If a reference image is provided, incorporate the product's visual characteristics \
(colour, shape, packaging, textures) accurately into the prompt.

Output ONLY the prompt string. Do not include explanations."""


async def _call_text_only(product_name: str, description: str) -> str:
    """Text-only Groq call using llama-3.1-8b-instant."""
    client = _get_client()
    response = await client.chat.completions.create(
        model=_TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Product Name: {product_name}\n"
                    f"Description: {description}\n\n"
                    "Generate the image prompt."
                ),
            },
        ],
        temperature=0.7,
        max_tokens=400,
    )
    return (response.choices[0].message.content or "").strip()


async def _call_vision(
    product_name: str, description: str, reference_image_url: str
) -> str:
    """
    Multimodal Groq call using llama-4-scout.
    Passes the reference image as an image_url content block (OpenAI format).
    """
    client = _get_client()
    response = await client.chat.completions.create(
        model=_VISION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": reference_image_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Product Name: {product_name}\n"
                            f"Description: {description}\n\n"
                            "The image above is a reference photo of this product. "
                            "Use its visual characteristics (colour, shape, packaging, "
                            "textures, branding) to generate the image prompt."
                        ),
                    },
                ],
            },
        ],
        temperature=0.7,
        max_tokens=400,
    )
    return (response.choices[0].message.content or "").strip()


async def generate_image_prompt(
    product_name: str,
    description: str,
    reference_image_url: str | None = None,
) -> str:
    """
    Main entry point.

    If reference_image_url is provided, attempts a vision call first.
    Falls back to text-only on any exception (bad URL, model error, etc.).
    """
    if reference_image_url:
        try:
            logger.info(
                "LLM: vision call (%s) with reference image: %s",
                _VISION_MODEL,
                reference_image_url[:80],
            )
            prompt = await _call_vision(product_name, description, reference_image_url)
            logger.info("LLM: vision call succeeded (%d chars)", len(prompt))
            return prompt
        except Exception as exc:
            logger.warning(
                "LLM: vision call failed (%s) — falling back to text-only. Error: %s",
                _VISION_MODEL,
                exc,
            )

    # Text-only path (default, or vision fallback)
    logger.info("LLM: text-only call (%s)", _TEXT_MODEL)
    prompt = await _call_text_only(product_name, description)
    logger.info("LLM: text-only call succeeded (%d chars)", len(prompt))
    return prompt
