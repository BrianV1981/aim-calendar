# Memory Log

## [2026-09-02] ingest | Initial Pipeline Wiki Bootstrap
*   Bootstrapped the `memory-wiki` directory to comply with the `aim-memory-wiki` mandate.
*   Documented the completion of **Phase 1** (Audio Classification) and **Phase 2** (Diarization, Transcription, and RAG Vectorization).
*   Captured deep architectural learnings regarding LanceDB fragmentation and FTS indexing during massive batch insertions.
*   Created `index.md`, `pages/architecture.md`, and `pages/lancedb_cartridge.md`.

## [2026-09-03] ingest | Antigravity Audio Playback Capabilities
*   Discovered how the Antigravity UI parses media files on Windows 11 vs Android.
*   Documented that direct markdown links (Method 3) are the universal standard for UI audio playback.
*   Noted that HTML \<audio>\ tags are stripped and \.amr\ files require \fmpeg\ conversion to \.mp3\.
*   Created \pages/antigravity_ui_guidelines.md\ and updated \index.md\.

## [2026-09-03] ingest | A.I.M. Calendar Rebrand and 11GB Pipeline 
*   Officially rebranded the architecture from a proprietary TalkerACR script to the agnostic **A.I.M. Calendar** Enterprise Exocortex.
*   Processed an 11.2GB SMS Android backup. Implemented `xml.etree.ElementTree.iterparse` to stream the data, preventing OOM crashes, resulting in the successful extraction of 32,000+ texts and the generation of 2,031 Chronological Daily Notes.
*   Documented the Multimodal MMS Architecture linking the timeline to the `locomo-v2` Visual Translation Cache.
*   Updated `index.md`, `pages/architecture.md`, and created `pages/mms_multimodal_translation.md`.

## [2026-09-04] ingest | Data Blindspots & Sync Daemon Necessity
*   Confirmed that LanceDB queries are strictly limited to the date of the last diarized batch (currently July 10, 2026).
*   Identified that new data (e.g., August 18th calls) cannot be retrieved by agents until Issue #4 (Background Sync Daemon) pulls the raw files locally, and Phase 2 (Diarization) processes them.
*   Verified that the 11GB XML backup explicitly contains non-image rich media (`video/mp4`, `audio/amr`, `application/pdf`, `text/vcard`), mathematically validating the necessity of the MMS Multimodal Pipeline (Issue #1).
*   Updated `pages/architecture.md` to explicitly state the boundaries of the RAG retrieval window based on sync status.

## [2026-09-10] ingest | Open Source / Community Migration Readiness
*   Prepared the repository for open source and community sharing by thoroughly decoupling environment-specific paths.
*   Replaced all hardcoded Python `sys.path.append(...)` host paths with a dynamic `AIM_MEMORY_PATH` environment variable across `core/build_cartridge.py`, `core/ingest_to_lancedb.py`, and `core/test_retrieval.py`.
*   Appended `joshua_os/` to `.gitignore` to prevent leaking private operational workflows.
*   Renamed the repository root on the local filesystem from `aim-talkeracr` to `aim-calendar` to properly match the upstream GitHub origin.
*   Updated documentation (`HANDOFF.md`) and Systemd definitions (`core/systemd/aim-sync.*`) to reflect the new `aim-calendar` directory structure.

## [2026-10-14] ingest | Audit Pass 1 Remediation (Issue #18: CAL-001 through CAL-011)
*   **Secret & PII Remediation (`CAL-001`):** Stripped hardcoded `OPENAI_API_KEY` and `HF_TOKEN` credentials from `core/classify_calls.py`, `core/batch_diarize.py`, `core/benchmark_diarization.py`, and `core/test_pyannote.py`, and sanitized personal phone numbers/names across docs and tests.
*   **Incremental XML Globbing & Manifest (`CAL-002`):** Upgraded `core/ingest_sms.py` with `argparse` CLI flags and `.processed_xml_manifest.json` tracking so newly synced `calls-*.xml` and `sms-*.xml` files are ingested incrementally without re-parsing the 11GB base backup.
*   **Git & Open-Source Hygiene (`CAL-003`, `CAL-010`, `CAL-011`):** Executed `git rm -r --cached joshua_os` to untrack 106 `joshua_os/` files, removed root clutter (`test_pyannote.py`, `wiki_issue.txt`), added MIT `LICENSE`, updated `requirements.txt`, and synchronized `CHANGELOG.md` with `VERSION` (`v1.1.0`).
*   **Pipeline Chaining, Transcript Interleaving & Local-First Classification (`CAL-004`, `CAL-005`, `CAL-007`):** Wired full audio pipeline chaining in `core/sync_daemon.sh`, implemented `ingest_diarized_transcripts` to interleave `conversations_diarized/*.md` into `conversations/daily_notes/YYYY-MM-DD.md`, and switched `core/classify_calls.py` to local Ollama by default.
*   **Test Discovery & Dry-Run Integrity (`CAL-006`, `CAL-009`):** Guarded top-level execution in `core/test_fts.py` and `core/test_retrieval.py`, converted `core/test_classifier.py` to fast offline unit tests, and fixed `core/obsidian_vault.py --dry-run` side effects.

## [2026-10-14] ingest | Audit Pass 2 Delta Remediation (Issue #19: CAL-001, CAL-012, CAL-013)
*   **Full Git History Scrub & Generic Remote Default (`CAL-001`):** Replaced the hardcoded personal Google Drive SMS path default with `gdrive:SMS_Backups` in `core/sync_daemon.sh` and `README.md`, added `.env` support for local host overrides, scrubbed historical commits across all refs, and pruned remote `archive-*` branches.
*   **Superseded XML/ZIP Pruning & Manifest Exclude Filter (`CAL-012`):** Implemented `prune_superseded_backups()` in `core/ingest_sms.py` and `--exclude-from` manifest filtering in `core/sync_daemon.sh`, reclaiming ~192 GB of redundant cumulative backups in `conversations/sms_raw/` without triggering rclone re-downloads.
*   **Systemd Log Deduplication (`CAL-013`):** Updated `core/systemd/aim-sync.service` and `install_systemd()` to use `StandardOutput=journal` / `StandardError=journal` and added inode deduplication in `log()` so `sync_daemon.log` never writes duplicate lines.
