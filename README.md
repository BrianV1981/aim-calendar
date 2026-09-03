# A.I.M. Calendar
> **Actual Intelligent Memory Calendar**

An Enterprise Chronological Exocortex and Multimodal RAG Pipeline.

**A.I.M. Calendar** is a zero-touch, background-syncing intelligence layer that automatically weaves disparite data streams—SMS messages, call logs, phone call audio transcripts, and visual MMS data—into a perfect chronological timeline (Daily Notes).

Designed for professionals (lawyers, real estate agents, sales teams), it replaces high-friction CRMs with a frictionless, visual calendar interface. Click a date, and instantly view the exact timeline of your digital life.

---

## 🚀 Features (The Exocortex)

1. **Streaming Android SMS & Call Ingestion:** Uses a custom `iterparse` engine capable of chewing through massive 10GB+ Android XML backups locally without OOM crashing.
2. **Audio Transcription & Diarization:** Automatically ingests `.amr` and `.mp3` call recordings, transcribes them via Whisper, separates speakers via Pyannote, and maps the audio context into the timeline.
3. **Visual Translation Cache (MMS):** Extracts Base64 MMS images, pairs them with `locomo-v2` offline vision models (LLaVA/MiniCPM), and injects deep OCR and contextual descriptions directly into the timeline.
4. **Chronological Daily Notes:** Outputs beautiful, Obsidian-compatible `YYYY-MM-DD.md` files where texts, call durations, images, and transcripts are interleaved in exact chronological order.
5. **LanceDB Vector RAG:** Natively built to ingest the output into the `aim-memory` Retrieval-Augmented Generation ecosystem, allowing users to execute semantic searches across years of timeline data (e.g., *"What did Ayrianna text me about on Election Day 2020?"*).

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