# Multimodal Rich Media Translation Pipeline

The A.I.M. Calendar project acts as the extraction and mapping layer for the **Visual Translation Cache**, resolving the inherent limitation of text-only RAG databases (like LanceDB) being unable to semantically query raw media.

## The Problem
When extracting an Android XML backup (11GB+), roughly 99% of the file weight is composed of Base64 encoded payloads representing MMS attachments (such as group chat photos, videos, voice notes, vCards, or PDF documents). Discarding these attachments removes critical multimodal context from the user's timeline.

## The Solution: Offline Multimodal Ground Truth
Instead of relying on online cloud APIs, the architecture integrates directly with the user's `locomo-v2` architecture (Local Multimodal Conversational Memory).

### 1. Base64 Extraction
During Phase 3 (SMS Ingestion), the `iterparse` engine intercepts `<mms>` tags. Instead of dropping the data, it decodes the `data="..."` Base64 payload back into standard `.jpg`, `.mp4`, `.pdf`, or `.amr` files based on the `ct="mime/type"` attribute, saving them securely to the local `conversations/media/` directory.

### 2. Markdown Reference Mapping
The ingestion script embeds a standard Markdown link (e.g., `![Media](media/mms_1609360272000.jpg)` or `[Document](media/mms_1609360272000.pdf)`) into the Daily Note precisely at the chronological timestamp where the file was sent/received, alongside the `<part text="...">` caption.

### 3. Asynchronous Model Translation
The `locomo-v2` daemon (running completely offline models like LLaVA-7B, Whisper, or MiniCPM-V) asynchronously scans the Daily Notes for new media links. When found, it executes a deep OCR/VQA pass over images, or transcription over audio/video, generating a rich text caption.
This `llava_caption` (or transcript) is subsequently injected as a blockquote directly beneath the media in the Daily Note (e.g., `> [Visual Context: A video of a red sports car parked in front of a house.]`).

### 4. Mathematical Integration
When Phase 4 (LanceDB Injection) runs, it strictly ingests the generated text caption. This mathematically bridges the Multimodal gap, allowing the text-based RAG system to reliably retrieve images and visual memories based on semantic text queries.
