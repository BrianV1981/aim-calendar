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
*   Replaced all hardcoded Python `sys.path.append("/home/kingb/aim-memory")` calls with a dynamic `AIM_MEMORY_PATH` environment variable across `core/build_cartridge.py`, `core/ingest_to_lancedb.py`, and `core/test_retrieval.py`.
*   Appended `joshua_os/` to `.gitignore` to prevent leaking private operational workflows.
*   Renamed the repository root on the local filesystem from `aim-talkeracr` to `aim-calendar` to properly match the upstream GitHub origin.
*   Updated documentation (`HANDOFF.md`) and Systemd definitions (`core/systemd/aim-sync.*`) to reflect the new `aim-calendar` directory structure.
