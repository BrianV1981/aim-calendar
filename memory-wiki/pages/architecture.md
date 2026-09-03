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

### Phase 3: The Exocortex Lifelog (SMS & Call Ingestion)
**Objective:** Parse Android XML backups (SMS & Call Logs) and stitch them together with the Phase 2 Audio Transcripts into chronological timelines.
**Process:** The system utilizes a streaming `iterparse` engine to process massive (10GB+) XML files without OOM crashes. It parses texts, calls, and MMS image attachments, interleaving them in exact chronological order into single `YYYY-MM-DD.md` Obsidian-compatible Daily Notes in the `conversations/daily_notes/` directory.

### Phase 4: LanceDB Vector Injection (Markdown RAG)
**Objective:** Inject the completely unified Daily Notes into the RAG vector database.
**Process:** The system parses the compiled `YYYY-MM-DD.md` Daily Notes, chunks them appropriately, and embeds them into the `talker_cartridge.lance` database. This ensures the RAG agent has full semantic context across audio, texts, and dates simultaneously.
