# A.I.M. Calendar
> **Actual Intelligent Memory Calendar**

An Enterprise Chronological Exocortex and Multimodal RAG Pipeline.

**A.I.M. Calendar** is a zero-touch, background-syncing intelligence layer that automatically weaves disparite data streams—SMS messages, call logs, phone call audio transcripts, and visual MMS data—into a perfect chronological timeline (Daily Notes).

Designed for professionals (lawyers, real estate agents, sales teams), it replaces high-friction CRMs with a frictionless, visual calendar interface. Click a date, and instantly view the exact timeline of your digital life.

---

## 🚀 Features (The Exocortex)

1. **Streaming Android SMS & Call Ingestion:** Uses a custom `iterparse` engine capable of chewing through massive 10GB+ Android XML backups locally without OOM crashing.
2. **Audio Transcription & Diarization:** Automatically ingests `.amr` and `.mp3` call recordings, transcribes them via Whisper, separates speakers via Pyannote, and maps the audio context into the timeline.
3. **Visual Translation Cache (MMS):** Extracts Base64 MMS payloads (images, videos, vCards, documents), pairs them with `locomo-v2` offline vision models (LLaVA/MiniCPM), and injects deep OCR and contextual descriptions directly into the timeline.
4. **Chronological Daily Notes:** Outputs beautiful, generic Markdown (`YYYY-MM-DD.md`) files where texts, call durations, rich media, and transcripts are interleaved in exact chronological order. These can be ingested by any MIT-licensed knowledge graph or custom UI to surpass standard bidirectional linking.
5. **Google Calendar Sync (V1 Goal):** While local-first by design, V1 will fully integrate with Google Calendar as the primary UI. Users can opt to back up their structured data to Google Drive, making the entire Exocortex instantly retrievable and visually accessible via their cloud calendar.
6. **LanceDB Vector RAG:** Natively built to ingest the output into the `aim-memory` Retrieval-Augmented Generation ecosystem, allowing users to execute semantic searches across years of timeline data.

---

## 🛠️ Architecture & Pipeline

The backend engine resides in `/core/` and executes the pipeline in 4 phases:

*   **Phase 1: Database Initialization** (`build_cartridge.py`, `compact_db.py`)
*   **Phase 2: Audio Pipeline** (`batch_diarize.py`, `batch_ingest.py`)
*   **Phase 3: Text & Log Pipeline** (`ingest_sms.py`)
*   **Phase 4: Exocortex Timeline** (Chronological Generation via Obsidian formats)

---

## 📜 License & Privacy

**100% Local. Air-Gapped. Private.**
A.I.M. Calendar operates strictly on your local hardware. None of your private SMS messages, phone recordings, or images are ever sent to a cloud API.

*Built for the Joshua OS Ecosystem.*