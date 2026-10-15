import os
import json
import base64
import mimetypes
import subprocess
import tempfile
from typing import Any, Dict, Optional, Union
import requests


def load_dotenv_defaults(dotenv_path: Optional[str] = None) -> None:
    """
    Loads key=value pairs from .env into os.environ without overwriting
    already-set environment variables. Supports git worktrees by checking
    the parent repository root if .env is not in the worktree root.
    """
    candidates = []
    if dotenv_path:
        candidates.append(dotenv_path)
    else:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        candidates.append(os.path.join(repo_root, ".env"))
        parent_root = os.path.abspath(os.path.join(repo_root, "..", ".."))
        candidates.append(os.path.join(parent_root, ".env"))

    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        # Handle simple bash default syntax ${VAR:-default}
                        if val.startswith("${") and ":-" in val and val.endswith("}"):
                            val = val.split(":-", 1)[1][:-1]
                        if key and key not in os.environ:
                            os.environ[key] = val
            except OSError:
                pass
            break


load_dotenv_defaults()

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_TEXT_MODEL = "qwen3.5:4b"
DEFAULT_OLLAMA_VISION_MODEL = "qwen2.5vl:3b"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def resolve_provider(override: Optional[str] = None) -> str:
    """
    Resolves the active LLM provider ('gemini' or 'ollama').
    - Explicit override or AIM_LLM_PROVIDER='gemini'|'ollama' is honored directly.
    - AIM_LLM_PROVIDER='auto' (default) selects 'gemini' when GEMINI_API_KEY is set,
      otherwise falls back to local 'ollama'.
    """
    mode = (override or os.environ.get("AIM_LLM_PROVIDER", "auto")).strip().lower()
    if mode in ("gemini", "ollama"):
        return mode
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        return "gemini"
    return "ollama"


def _parse_json_response(raw_text: str) -> Any:
    """Extracts and parses JSON from an LLM response string."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


def _call_gemini_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    response_schema: Any = None,
    json_mode: bool = False,
    temperature: float = 0.1,
) -> Union[str, Dict, list]:
    """Calls Google Gemini via google-genai SDK (or REST fallback)."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required for provider 'gemini'.")

    model_name = model or os.environ.get("AIM_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config_kwargs: Dict[str, Any] = {"temperature": temperature}
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if json_mode or response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
        if response_schema is not None:
            config_kwargs["response_schema"] = response_schema

        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        text = (resp.text or "").strip()
    except ImportError:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        r = requests.post(url, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    if json_mode:
        return _parse_json_response(text)
    return text


def _call_ollama_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    json_mode: bool = False,
    temperature: float = 0.1,
    timeout: int = 90,
) -> Union[str, Dict, list]:
    """Calls local Ollama /api/generate endpoint."""
    ollama_url = os.environ.get("AIM_OLLAMA_URL", DEFAULT_OLLAMA_URL)
    model_name = model or os.environ.get("AIM_OLLAMA_TEXT_MODEL", DEFAULT_OLLAMA_TEXT_MODEL)

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    payload: Dict[str, Any] = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"

    resp = requests.post(ollama_url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    text = (data.get("response") or "").strip()

    if json_mode:
        return _parse_json_response(text)
    return text


def generate_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    response_schema: Any = None,
    json_mode: bool = False,
    temperature: float = 0.1,
    timeout: int = 90,
) -> Union[str, Dict, list]:
    """
    Unified text & structured JSON generation entry point.
    Supports 'gemini' and 'ollama' with optional automatic fallback.
    """
    active = resolve_provider(provider)
    if active == "gemini":
        try:
            return _call_gemini_text(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                response_schema=response_schema,
                json_mode=json_mode,
                temperature=temperature,
            )
        except Exception:
            if provider == "gemini" or os.environ.get("AIM_LLM_FALLBACK", "1") == "0":
                raise
            return _call_ollama_text(
                prompt=prompt,
                system_prompt=system_prompt,
                model=None,
                json_mode=json_mode,
                temperature=temperature,
                timeout=timeout,
            )

    return _call_ollama_text(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        json_mode=json_mode,
        temperature=temperature,
        timeout=timeout,
    )


def _summarize_vcard(vcard_path: str) -> str:
    """Parses a .vcf contact card into a concise readable description."""
    fields = {}
    try:
        with open(vcard_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if line.upper().startswith("FN:"):
                    fields["name"] = line.split(":", 1)[1].strip()
                elif line.upper().startswith("ORG:"):
                    fields["org"] = line.split(":", 1)[1].strip().rstrip(";")
                elif line.upper().startswith("TEL"):
                     parts = line.split(":", 1)
                     if len(parts) == 2:
                         fields.setdefault("phones", []).append(parts[1].strip())
                elif line.upper().startswith("EMAIL"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        fields.setdefault("emails", []).append(parts[1].strip())
    except OSError:
        return "vCard contact attachment."

    summary_parts = []
    if fields.get("name"):
        summary_parts.append(f"Contact card for {fields['name']}")
    else:
        summary_parts.append("vCard contact card")
    if fields.get("org"):
        summary_parts.append(f"({fields['org']})")
    if fields.get("phones"):
        summary_parts.append(f"Phone: {', '.join(fields['phones'][:2])}")
    if fields.get("emails"):
        summary_parts.append(f"Email: {', '.join(fields['emails'][:2])}")
    return " - ".join(summary_parts)


def _extract_video_keyframe(video_path: str) -> Optional[bytes]:
    """Uses ffmpeg to extract a single JPEG frame from a video file for offline vision."""
    if not shutil_which("ffmpeg"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_jpg = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", "-q:v", "3", tmp_jpg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        if os.path.exists(tmp_jpg) and os.path.getsize(tmp_jpg) > 0:
            with open(tmp_jpg, "rb") as f:
                return f.read()
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_jpg):
            try:
                os.remove(tmp_jpg)
            except OSError:
                pass
    return None


def shutil_which(cmd: str) -> Optional[str]:
    import shutil
    return shutil.which(cmd)


def _normalize_caption(text: str) -> str:
    """Flattens multi-line LLM output into a clean single-line caption."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    joined = " ".join(lines)
    # Collapse excessive whitespace
    return " ".join(joined.split())


def describe_media(
    media_path: str,
    prompt: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """
    Generates a concise visual/OCR description of an MMS attachment
    (image, video, vCard, text, or PDF) using either Gemini 2.5 Flash
    or local Ollama vision (qwen2.5vl:3b).
    """
    if not os.path.isfile(media_path):
        raise FileNotFoundError(f"Media file not found: {media_path}")

    ext = os.path.splitext(media_path)[1].lower()
    if ext == ".vcf":
        return _summarize_vcard(media_path)

    if ext == ".txt":
        try:
            with open(media_path, "r", encoding="utf-8", errors="replace") as f:
                snippet = _normalize_caption(f.read(600))
            return f"Text attachment: {snippet}" if snippet else "Empty text attachment."
        except OSError:
            return "Text attachment."

    default_prompt = (
        prompt
        or "Provide a concise 1-2 sentence description of this media attachment for a personal daily log. "
        "Include any visible text, numbers, business names, dates, or invoice totals (OCR)."
    )

    active = resolve_provider(provider)
    mime_type, _ = mimetypes.guess_type(media_path)
    if not mime_type:
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".3gp": "video/3gpp",
            ".pdf": "application/pdf",
            ".amr": "audio/amr",
            ".mp3": "audio/mpeg",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

    if active == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required for provider 'gemini'.")
        model_name = model or os.environ.get("AIM_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        with open(media_path, "rb") as f:
            raw_bytes = f.read()

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            part = types.Part.from_bytes(data=raw_bytes, mime_type=mime_type)
            resp = client.models.generate_content(
                model=model_name,
                contents=[part, default_prompt],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            return _normalize_caption(resp.text or "")
        except ImportError:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            b64_data = base64.b64encode(raw_bytes).decode("ascii")
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                            {"text": default_prompt},
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.1},
            }
            r = requests.post(url, json=payload, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return _normalize_caption(data["candidates"][0]["content"]["parts"][0]["text"])

    # Local Ollama vision path
    image_bytes: Optional[bytes] = None
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        with open(media_path, "rb") as f:
            image_bytes = f.read()
    elif ext in (".mp4", ".3gp", ".mov"):
        image_bytes = _extract_video_keyframe(media_path)
        if not image_bytes:
            return f"Video attachment ({os.path.basename(media_path)})."
    else:
        return f"Media attachment ({os.path.basename(media_path)}, type: {mime_type})."

    ollama_url = os.environ.get("AIM_OLLAMA_URL", DEFAULT_OLLAMA_URL)
    vision_model = model or os.environ.get("AIM_OLLAMA_VISION_MODEL", DEFAULT_OLLAMA_VISION_MODEL)
    b64_img = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "model": vision_model,
        "prompt": default_prompt,
        "images": [b64_img],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    resp = requests.post(ollama_url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return _normalize_caption(data.get("response") or "")
