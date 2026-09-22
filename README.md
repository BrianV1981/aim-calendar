# A.I.M. Calendar
> **Actual Intelligent Memory Calendar**

An Enterprise Chronological Exocortex and Multimodal RAG Pipeline.

**A.I.M. Calendar** is a zero-touch, background-syncing intelligence layer that automatically weaves disparate data streams—SMS messages, call logs, phone call audio transcripts, and visual MMS data—into a perfect chronological timeline (Daily Notes).

Designed as a historical calendar of all communications, it acts as a personal exocortex. Click a date, and instantly view the exact timeline of your digital life, or utilize the native RAG system to perform semantic and lexical searches across years of timeline data.

---

## 🚀 Features (The Exocortex)

1. **Streaming Android SMS & Call Ingestion:** Uses a custom `iterparse` engine capable of chewing through massive 10GB+ Android XML backups locally without OOM crashing.
2. **Audio Transcription & Diarization:** Automatically ingests `.amr` call recordings from Talker ACR, transcribes them via Whisper, separates speakers via Pyannote, and maps the audio context into the timeline.
3. **Visual Translation Cache (MMS):** Extracts Base64 MMS payloads (images, videos, vCards, documents) and maps them natively into Markdown. 
4. **Chronological Daily Notes:** Outputs beautiful, generic Markdown (`YYYY-MM-DD.md`) files where texts, call durations, rich media, and transcripts are interleaved in exact chronological order.
5. **Background Sync Daemon:** Natively syncs data from Google Drive without manual intervention via `core/sync_daemon.sh` and Systemd timers.
6. **Obsidian Vault UI:** Generates a turnkey Obsidian vault with the official Calendar plugin preconfigured to beautifully visualize your timeline.
7. **LanceDB Vector RAG:** Injects the chronological timeline into `talker_cartridge.lance`, allowing agents and users to execute semantic queries across calls and texts simultaneously.

---

## 📱 Phone Configuration (Android)

To enable the zero-touch pipeline, configure your Android device to backup to Google Drive:

### 1. Audio Call Recording (Talker ACR)
1. Install **Talker ACR** on your Android device.
2. Open Settings -> **Cloud** -> Link your **Google Drive** account.
3. Talker ACR will automatically upload new `.amr` recordings to `gdrive:TalkerACR/All` after every call.
4. *Note: Restrict this to Wi-Fi if you have limited mobile data.*

### 2. SMS & Call Logs (SMS Backup & Restore)
1. Install **SMS Backup & Restore** on your Android device.
2. Go to **Settings -> Advanced Options** and turn ON **Archive (Zip) Backup**. *(Critical: This shrinks the 11GB backup file to under 1GB).*
3. Set up a **Daily Schedule** (e.g., 3:00 AM) to upload to **Google Drive** (`gdrive:SMS_Backups`).
4. Set **"Delete older backups"** to retain only the last 2-3 backups to prevent Google Drive bloat.
5. (Optional but recommended): Turn on **Incremental Backup** in Backup Settings to only upload new messages.

---

## 🛠️ Architecture & Pipeline

The backend engine resides in `/core/` and executes the pipeline iteratively:

*   **Phase 1: Background Cloud Sync** (`core/sync_daemon.sh`) - *Pulls new data from Google Drive.*
*   **Phase 2: Audio Pipeline** (`batch_diarize.py`) - *Pyannote & Whisper diarization.*
*   **Phase 3: Text & Log Pipeline** (`core/ingest_sms.py`) - *MMS extraction and Markdown linking.*
*   **Phase 4: Exocortex Timeline** (`core/obsidian_vault.py`) - *Chronological Daily Note generation.*
*   **Phase 5: LanceDB Vector Injection** (`core/ingest_to_lancedb.py`) - *Markdown RAG pipeline.*

---

## 📜 License & Privacy

**100% Local. Air-Gapped. Private.**
A.I.M. Calendar operates strictly on your local hardware. None of your private SMS messages, phone recordings, or images are ever sent to a cloud API.

*Built for the Joshua OS Ecosystem.*
