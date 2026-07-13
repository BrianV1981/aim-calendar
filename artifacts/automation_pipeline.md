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

## Step 2: Secure Server Retrieval (Cloud to Linux)
On your Linux machine, we will completely bypass third-party sync apps and use the native `aim-google` CLI to pull files directly from your workspace.

*   **The Check:** The daemon runs `aim-google drive ls --agent` to locate any new files in the `TalkerACR_Ingest` Google Drive folder.
*   **The Pull:** The daemon executes `aim-google drive get <file_id> --agent` to download the audio directly into your `/home/kingb/aim-talkeracr/TalkerACR/All/` directory.

## Step 3: The Autonomous Pipeline Daemon (Cron Job)
We wrap our Python and Go scripts into a single master shell script (`core/daemon_pipeline.sh`) and schedule it to run every hour via `cron`.

The daemon will execute perfectly in order:
1.  **The Fetch:** `aim-google` natively pulls new `.amr` files from Google Drive.
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
2. I can write the master `core/daemon_pipeline.sh` script to tie everything together natively using your `aim-google` CLI.
