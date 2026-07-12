# Fully Automated Knowledge Pipeline (Android -> A.I.M.)

This pipeline creates a "set it and forget it" workflow. The moment you hang up a phone call, it is automatically uploaded, transcribed, classified as golden/garbage, and indexed into your semantic database without you touching a single button.

## Step 1: The Phone (Android -> Google Drive)
You need a background app on your Android phone to watch the Talker ACR folder and silently push files to the cloud.

*   **The App:** Download **"Autosync for Google Drive" (DriveSync)** or **"FolderSync"** from the Google Play Store.
*   **The Setup:** 
    *   Set the **Local Folder** to your Talker ACR recordings folder.
    *   Set the **Remote Folder** to a new folder in your Google Drive (e.g., `TalkerACR_Ingest`).
    *   **Sync Method:** Set it to `Upload Only` (or `Two-way` if you want them deleted off your phone once processed).
    *   **Automation:** Tell the app to sync automatically on Wi-Fi (or mobile data if you have unlimited).

## Step 2: The Server (Google Drive -> Linux Machine)
On your Linux machine, we will use **`rclone`**, the industry standard for syncing with cloud storage via the terminal.

*   **Setup:** You run `rclone config` to link your Google Drive account.
*   **The Pull:** We create a bash command: `rclone move gdrive:TalkerACR_Ingest /home/kingb/aim-talkeracr/TalkerACR/All/`. 
    *   *(Note: Using `rclone move` instead of `sync` will automatically delete the file from Google Drive once it safely reaches your Linux machine, preventing cloud storage bloat/fees).*

## Step 3: The Autonomous Pipeline Daemon (Cron Job)
We wrap our three Python scripts into a single master shell script (`core/daemon_pipeline.sh`) and schedule it to run every hour (or every night at 2:00 AM) via `cron`.

The daemon will execute perfectly in order:
1.  **The Fetch:** `rclone move` pulls new `.amr` files from Google Drive.
2.  **Phase 1 (Transcription):** Runs `batch_ingest.py`. Because it's idempotent, it skips the 13k old files instantly and only transcribes the new ones into `.md` files.
3.  **Phase 2 (Classification):** Runs `classify_calls.py`. The local LLM reads the new `.md` transcripts and tags them as `status: golden` or `status: garbage`.
4.  **Phase 3 (Semantic RAG):** Runs `ingest_to_lancedb.py`. It ignores the garbage files, slices the golden calls using our Sliding Window chunker, and mathematically embeds them into LanceDB.

## Step 4: Bloat Prevention & Garbage Collection
To prevent your Linux hard drive from filling up with massive `.amr` audio files over the years:
*   Once Phase 3 successfully completes, the master script can execute a cleanup command.
*   It deletes the raw `.amr` audio files that are older than 7 days (or immediately deletes them), leaving behind **only** the lightweight Markdown transcript in your Obsidian vault. 
*   This drops the storage cost of a 45-minute phone call from ~10MB to ~15KB.

---

### Implementation Plan
If you like this architecture:
1. You can install **DriveSync** on your phone.
2. I can install **`rclone`** on your Linux machine and write the master `core/daemon_pipeline.sh` script to tie everything together.
