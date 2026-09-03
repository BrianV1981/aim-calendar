# Multimodal MMS Translation Pipeline

The A.I.M. Calendar project acts as the extraction and mapping layer for the **Visual Translation Cache**, resolving the inherent limitation of text-only RAG databases (like LanceDB) being unable to semantically query raw images.

## The Problem
When extracting an Android XML backup (11GB+), roughly 99% of the file weight is composed of Base64 encoded payloads representing MMS image attachments (such as group chat photos or camera pictures). Discarding these attachments removes critical visual context from the user's timeline.

## The Solution: Offline Visual Ground Truth
Instead of relying on online cloud Vision APIs, the architecture integrates directly with the user's `locomo-v2` architecture (Local Multimodal Conversational Memory).

### 1. Base64 Extraction
During Phase 3 (SMS Ingestion), the `iterparse` engine intercepts `<mms>` tags. Instead of dropping the data, it decodes the `data="..."` Base64 payload back into standard `.jpg` or `.png` image files, saving them securely to the local `conversations/media/` directory.

### 2. Markdown Reference Mapping
The ingestion script embeds a standard Markdown image link (e.g., `![Image](media/mms_1609360272000.jpg)`) into the Daily Note precisely at the chronological timestamp where the image was sent/received, alongside the `<part text="...">` caption.

### 3. Asynchronous Model Translation
The `locomo-v2` daemon (running completely offline models like LLaVA-7B or MiniCPM-V) asynchronously scans the Daily Notes for new media links. When found, it executes a deep OCR/Visual Question Answering pass over the local image, generating a rich text caption.
This `llava_caption` is subsequently injected as a blockquote directly beneath the image in the Daily Note (e.g., `> [Visual Context: A photo of a red sports car parked in front of a house.]`).

### 4. Mathematical Integration
When Phase 4 (LanceDB Injection) runs, it strictly ingests the generated text caption. This mathematically bridges the Multimodal gap, allowing the text-based RAG system to reliably retrieve images and visual memories based on semantic text queries.
