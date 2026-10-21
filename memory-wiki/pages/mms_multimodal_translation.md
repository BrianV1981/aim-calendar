# Multimodal Rich Media Translation Pipeline (`locomo-v2`)

The A.I.M. Calendar project acts as the extraction and mapping layer for the **Visual Translation Cache**, resolving the inherent limitation of text-only RAG databases (like LanceDB) being unable to semantically query raw media.

## The Problem
When extracting an Android XML backup (11GB+), roughly 99% of the file weight is composed of Base64 encoded payloads representing MMS attachments (such as group chat photos, videos, voice notes, vCards, or PDF documents). Discarding these attachments removes critical multimodal context from the user's timeline.

## The Solution: Hybrid & Offline Multimodal Ground Truth
Implemented in **Issue #13** via `core/llm_provider.py` and `core/translate_media.py`, the architecture integrates the `locomo-v2` Visual Translation Cache directly into the Daily Notes and LanceDB pipeline.

### 1. Base64 Extraction (`core/ingest_sms.py`)
During Phase 3 (SMS Ingestion), the streaming `iterparse` engine intercepts `<mms>` tags. Instead of dropping the data, it decodes the `data="..."` Base64 payload back into standard `.jpg`, `.png`, `.gif`, `.webp`, `.mp4`, `.pdf`, `.vcf`, or `.amr` files based on the `ct="mime/type"` attribute, saving them with MD5 payload deduplication to `conversations/media/`.

### 2. Markdown Reference Mapping
`core/ingest_sms.py` embeds relative Markdown links (e.g., `![MMS Image](../media/mms_20260904_a1b2c3d4.jpg)` or `[MMS Video](../media/mms_20260904_e5f6g7h8.mp4)`) into the Daily Note (`conversations/daily_notes/YYYY-MM-DD.md`) at the exact chronological timestamp where the file was sent or received, alongside any text caption.

### 3. Unified Provider & Asynchronous Media Translation (`core/translate_media.py`)
`core/translate_media.py` scans `conversations/daily_notes/*.md` for media references and generates concise OCR/visual descriptions via `core/llm_provider.py` (`describe_media()`):
*   **Provider Resolution (`AIM_LLM_PROVIDER=auto|ollama|gemini`):** Uses `gemini-2.5-flash` when `GEMINI_API_KEY` is configured, or falls back to local air-gapped Ollama (`qwen2.5vl:3b` for vision and `qwen3.5:4b` for text, extracting representative frames via `ffmpeg` for video attachments).
*   **Persistent Cache (`conversations/media/.visual_translation_cache.json`):** Stores generated descriptions keyed by media filename and MD5/mtime so unchanged media files are never re-processed.
*   **Blockquote Injection:** Injects `> [Visual Context: <description>]` directly beneath the media link in the Daily Note idempotently.

### 4. Incremental LanceDB Re-Indexing (`core/ingest_to_lancedb.py`)
When `core/translate_media.py` modifies a Daily Note by injecting visual context, `core/ingest_to_lancedb.py` detects the updated file `mtime`/`size` against `.processed_lancedb_manifest.json`, deletes the stale fragments for that date, and re-embeds the enriched chunks into `talker_cartridge.lance`.
