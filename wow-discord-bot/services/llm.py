import logging
import httpx
from typing import AsyncGenerator

from config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are an expert World of Warcraft advisor for the Midnight expansion. "
    "You analyze patch notes and community resources to give concise, actionable "
    "advice tailored to a specific player's class, spec, role, and content focus. "
    "Always be direct and practical."
)


def _build_user_prompt(
    patch_text: str,
    wowhead_text: str,
    icy_veins_text: str,
    wow_class: str,
    spec: str,
    role: str,
    content_focus: str,
) -> str:
    return f"""The player is a {role.upper()} playing {spec} {wow_class}, focused on {content_focus}.

=== OFFICIAL PATCH NOTES ===
{patch_text[:3000]}

=== WOWHEAD ANALYSIS ===
{wowhead_text[:2000]}

=== ICY VEINS CLASS UPDATES ===
{icy_veins_text[:2000]}

Based on the above, answer the following for this specific player:
1. What changed that directly affects {spec} {wow_class}?
2. What should the player adjust (talents, rotation, gear priorities)?
3. List 3-5 concrete action items the player should do after this patch.

Keep your answer concise and practical. Use bullet points."""


async def analyze_patch_notes(
    patch_text: str,
    wowhead_text: str,
    icy_veins_text: str,
    wow_class: str,
    spec: str,
    role: str,
    content_focus: str,
) -> str:
    """Send patch note data to Ollama and return the full analysis."""
    prompt = _build_user_prompt(
        patch_text, wowhead_text, icy_veins_text,
        wow_class, spec, role, content_focus,
    )

    logger.info(
        f"[LLM] Calling {settings.ollama_model} for {spec} {wow_class} | "
        f"patch={len(patch_text)}c  wowhead={len(wowhead_text)}c  iv={len(icy_veins_text)}c"
    )
    logger.debug(
        f"[LLM] SYSTEM PROMPT:\n{SYSTEM_PROMPT}\n"
        f"\n[LLM] USER PROMPT:\n{prompt}"
    )

    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/v1/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()

    logger.info(f"[LLM] Response ({len(result)}c):\n{result}")
    return result


async def stream_response(prompt: str) -> AsyncGenerator[str, None]:
    """Stream a general response from Ollama (used for interactive queries)."""
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
        ) as resp:
            import json
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
                except Exception:
                    continue
