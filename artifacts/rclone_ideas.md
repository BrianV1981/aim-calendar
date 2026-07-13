# Future Enhancements: rclone Integrations

While the primary ingestion pipeline uses `aim-google` for surgical, stateless file retrieval, **`rclone`** remains a powerful, stateful sync engine. 

Below are potential future enhancements for the A.I.M. architecture that leverage `rclone`'s massive synchronization capabilities:

## 1. The "Second Brain" Offsite Backup
Once the pipeline converts calls and texts into lightweight Markdown files, the `conversations/` directory effectively becomes an Obsidian Vault (your "Second Brain"). 
*   **The Idea:** Use a daily `rclone sync` cron job to push an encrypted, one-way backup of the entire Markdown folder UP to Google Drive or AWS/Backblaze. 
*   **The Benefit:** If the local Linux server suffers catastrophic hardware failure, the entire indexed knowledge base is perfectly preserved offsite.

## 2. Obsidian Mobile Two-Way Sync
If the Operator uses the Obsidian mobile app on their phone to review transcripts while commuting, they may manually fix typos, add tags, or inject new context into the markdown.
*   **The Idea:** Implement `rclone bisync` (two-way sync) between the Linux server and the mobile device's Obsidian folder (via Google Drive or Syncthing).
*   **The Benefit:** The pipeline seamlessly pulls manual mobile edits back down to the Linux server, ensuring the LanceDB vector store ingests the most accurate, human-corrected context.

## 3. Massive Audio Archival (Cold Storage)
Currently, raw `.amr` audio files are marked for deletion post-transcription to prevent local storage bloat.
*   **The Idea:** Instead of deleting the audio, execute an `rclone move` command to ship the massive `.amr` files to a dirt-cheap "cold storage" bucket (e.g., Amazon Glacier Deep Archive or Backblaze B2).
*   **The Benefit:** The audio is preserved perpetually for pennies a month in case a better transcription model is released in the future, while keeping the local Linux SSD completely clean.
