# Pipeline Architecture

The primary goal of this repository is to process raw communications data (Phone Calls, Text Messages) and cleanly map them into the `aim-memory` RAG 5.21 schema for the Joshua OS.

## The 4-Phase Ingestion Pipeline

### Phase 1: Classification (Complete)
**Objective:** Prevent wasted compute by separating real conversations from noise.
**Process:** Raw `.amr` audio files from Talker ACR (13,539 total) were passed through an OpenAI classifier which analyzed length and context metadata. 
**Result:** 3,121 files were identified as "Garbage" (spam/voicemails) and skipped. 10,418 were identified as "Golden" real conversations.

### Phase 2: Diarization & Cartridge Building (Complete)
**Objective:** Transcribe the audio and build an isolated LanceDB vector database.
**Process:**
1.  **Diarization/Transcription:** Ran all 10,418 Golden audio files through an idempotent `tmux` daemon executing Pyannote (Speaker Separation) and Whisper (Transcription). Produced raw Markdown transcripts in `conversations_diarized/`.
2.  **RAG Chunking:** Parsed the Markdown files, identified individual speaker turns, and merged them into a `[Turn N-1] + [Turn N] + [Turn N+1]` contextual sliding window.
3.  **Vectorization:** Vectorized via Ollama (`nomic-embed-text`) into a standalone `talker_cartridge.lance` database. *(See [LanceDB Cartridge Generation](lancedb_cartridge.md) for deeper technical notes on avoiding massive disk bloat during this step).*

### Phase 3: The Exocortex Lifelog (SMS, MMS & Call Ingestion) (Complete)
**Objective:** Parse Android XML backups (SMS, MMS & Call Logs) and stitch them together with the Phase 2 Audio Transcripts into chronological timelines.
**Process:** The system utilizes a streaming `iterparse` engine (`core/ingest_sms.py`) to process massive (10GB+) XML files without OOM crashes. It parses texts, calls, and decodes Base64 rich media attachments (images, videos, documents, audio) from `<mms>` tags into `conversations/media/` with MD5 payload deduplication. It interleaves all communications in exact chronological order into single `YYYY-MM-DD.md` generic Markdown Daily Notes in `conversations/daily_notes/` while preserving multi-line media references and captions.

### Phase 4: LanceDB Vector Injection (Markdown RAG) (Complete)
**Objective:** Inject the completely unified Daily Notes into the RAG vector database.
**Process:** The system utilizes `core/ingest_to_lancedb.py` to parse chronological Daily Notes (`YYYY-MM-DD.md`), apply sliding-window chunking anchored with `[Date: YYYY-MM-DD]`, preserve multi-line entry blocks, and generate 768-dim `nomic-embed-text` embeddings. Vectors are inserted into `talker_cartridge.lance` under table `fragments` (`type: "daily_note"`) with full idempotency tracking, table optimization, and FTS indexing. This allows semantic retrieval across dates, SMS, calls, and transcripts simultaneously.

### Phase 5: Background Sync Daemon (Complete)
**Objective:** Eliminate manual sync steps by continuously synchronizing cloud backups to the local filesystem.
**Process:** The background sync daemon (`core/sync_daemon.sh`) orchestrates `rclone` synchronization from Google Drive into `TalkerACR/` and `conversations/sms_raw/`. It features flock-based lock safety, auto-unzipping of new archive backups, user-level systemd timer integration (`aim-sync.timer`, running every 15 minutes), and automatic incremental downstream pipeline triggering (`core/ingest_sms.py` -> `core/ingest_to_lancedb.py`) when new communications records are detected.

### Phase 6: Obsidian Calendar UI & Vault Integration (Complete)
**Objective:** Provide a frictionless, beautiful graphical timeline for browsing communications logs.
**Process:** The vault integration engine (`core/obsidian_vault.py`) provisions a complete Obsidian Vault structure (`.obsidian/`), installs and activates Liam Cain's official Calendar community plugin preconfigured for daily notes (weeks starting on Sunday, 250 words per dot), configures native Markdown links and attachment folder mapping to `conversations/media/`, and standardizes YAML frontmatter across 2,000+ Daily Notes with tags (`daily-note`, `calendar`, `timeline`, `exocortex`).

---

## Temporal Data Boundaries & Sync Necessity

Agents relying on LanceDB (`talker_cartridge.lance`) for RAG retrieval must understand the **temporal horizon** of the dataset.

*   **The Horizon Limit:** A LanceDB query will only return results up to the date of the last successful Phase 2 execution. If a user asks about a conversation that occurred *after* the last sync date, the system is fundamentally blind to it.
*   **The Sync Daemon (Issue #4):** Resolved via `core/sync_daemon.sh` and `aim-sync.timer`. The daemon automatically pulls new raw audio and SMS files from Google Drive into local storage and triggers the ingestion pipeline without manual intervention.
*   **Continuous Integration:** With automatic background synchronization active, incremental calls and texts are converted to Daily Notes and ready for Phase 4 LanceDB vectorization, keeping the agent's memory aligned with real time.
