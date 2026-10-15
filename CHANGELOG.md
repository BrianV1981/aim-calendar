# Changelog

All notable changes to the **A.I.M. Calendar** (formerly TalkerACR Ingestion) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-10-14
### Added
- **Unified Hybrid LLM & Vision Provider Adapter (`core/llm_provider.py`):** Added unified `ollama` (`qwen2.5vl:3b` / `qwen3.5:4b`) and `gemini` (`gemini-2.5-flash`) provider switch (`AIM_LLM_PROVIDER=auto|ollama|gemini`) with automatic `.env` loading and offline fallback.
- **Multimodal Visual Translation Pipeline (Issue #13, `core/translate_media.py`):** Implemented the `locomo-v2` visual translation engine that scans `conversations/daily_notes/*.md` for MMS media links, generates OCR/visual descriptions via `core/llm_provider.py`, caches results in `conversations/media/.visual_translation_cache.json`, injects `> [Visual Context: ...]` blockquotes into Daily Notes, and triggers incremental LanceDB re-indexing of modified Daily Notes.

## [1.1.0] - 2026-10-14
### Added
- **Incremental XML Globbing & Manifest Ledger (`CAL-002`):** Upgraded `core/ingest_sms.py` with full CLI `argparse` flags (`--input-dir`, `--file`, `--force`, `--dry-run`, `--manifest`) and `.processed_xml_manifest.json` tracking so newly synced `calls-*.xml` and `sms-*.xml` files are ingested incrementally without re-parsing historical 11GB backups.
- **Automated Superseded Backup Pruning & Exclude Filter (`CAL-012`):** Added `prune_superseded_backups` to `core/ingest_sms.py` to automatically delete superseded cumulative `sms-*.xml`, `calls-*.xml`, unpacked `calls.xml`/`messages.xml`, and extracted `.zip` archives once recorded in `.processed_xml_manifest.json`, and updated `core/sync_daemon.sh` to pass `--exclude-from` generated from the manifest and `.zip.extracted` markers so pruned backups are never re-downloaded (~192GB disk reclaimed).
- **Audio Transcript Interleaving in Daily Notes (`CAL-005`):** Added `ingest_diarized_transcripts` to `core/ingest_sms.py` to chronologically link and interleave speaker-diarized call transcripts (`conversations_diarized/*.md`) directly into `conversations/daily_notes/YYYY-MM-DD.md`.
- **Full Audio Pipeline Chaining (`CAL-004`):** Wired `batch_ingest.py` -> `classify_calls.py` -> `batch_diarize.py` -> `build_cartridge.py` -> `ingest_sms.py` -> `ingest_to_lancedb.py` into `core/sync_daemon.sh` (`--run-diarize`).
- **MIT License & Dependency Manifest (`CAL-010`):** Added root `LICENSE` file and completed `requirements.txt`.

### Changed
- **Security & Git History Remediation (`CAL-001`):** Removed all hardcoded API keys (`OPENAI_API_KEY`, `HF_TOKEN`), scrubbed historical git commits across all refs, replaced the hardcoded personal Google Drive SMS path default with `gdrive:SMS_Backups` (moving host-specific overrides to untracked `.env`), and sanitized personal phone numbers/PII across scripts, tests, and documentation.
- **Systemd Single-Line Logging (`CAL-013`):** Updated `core/systemd/aim-sync.service` and `core/sync_daemon.sh` (`install_systemd` + inode deduplication in `log()`) so `sync_daemon.log` never records duplicate lines when triggered by systemd or cron.
- **Local-First Call Classification (`CAL-007`):** Switched `core/classify_calls.py` to use local Ollama (`qwen3.5:4b`) by default, preserving 100% local/air-gapped operation.
- **Git & Test Suite Hygiene (`CAL-003`, `CAL-006`, `CAL-009`, `CAL-011`):** Untracked `joshua_os/` from git index, guarded top-level execution in `core/test_fts.py` and `core/test_retrieval.py`, fixed `core/obsidian_vault.py --dry-run` side effects, and removed root clutter.

## [0.1.0-alpha] - 2026-09-03
### Added
- **Project Rebrand:** Officially transitioned architecture from proprietary TalkerACR ingestion script to the agnostic `A.I.M. Calendar` Exocortex ecosystem.
- **SMS Streaming Parser:** Implemented `core/ingest_sms.py` with `xml.etree.ElementTree.iterparse` to allow local environments to parse massive (10GB+) Android SMS/Call Log XML backups without OOM memory crashes.
- **Chronological Note Generation:** Pipeline now automatically groups unstructured texts and phone calls into Obsidian-compatible `YYYY-MM-DD.md` Daily Notes.
- **Background Sync Daemon (Issue #4):** Implemented `core/sync_daemon.sh` to automate rclone cloud synchronization from Google Drive into `TalkerACR/` and `conversations/sms_raw/` with systemd timer integration (`aim-sync.timer`) and downstream pipeline triggers.
- **Multimodal MMS Extraction Pipeline (Issue #1):** Refactored `core/ingest_sms.py` to stream and extract Base64 rich media payloads from `<mms>` tags into `conversations/media/` with MD5 hash deduplication, relative Markdown links (`![MMS Image](...)`), and multiline-preserving chronological sorting.
- **LanceDB Vector Injection for Daily Notes (Issue #2):** Implemented `core/ingest_to_lancedb.py` with sliding window temporal chunking, date anchoring (`[Date: YYYY-MM-DD]`), multiline bullet group preservation, idempotent session tracking against `talker_cartridge.lance` table `fragments` (`type: "daily_note"`), 768-dim `nomic-embed-text` embeddings, table optimization, and FTS indexing.
- **Obsidian Calendar UI & Vault Integration (Issue #3):** Implemented `core/obsidian_vault.py` to deploy formal Obsidian Vault configurations (`.obsidian/`), install Liam Cain's official Calendar community plugin preconfigured for Daily Notes timelines, and idempotently migrate frontmatter across 2,000+ Daily Notes with calendar tags (`daily-note`, `calendar`, `timeline`, `exocortex`).

### Changed
- Replaced the default Git branch from `master` to `main`.
- Cleaned up obsolete documentation (`TOOLS.md`).
- Integrated automated downstream LanceDB vector injection into `core/sync_daemon.sh`.
- Updated `core/ingest_sms.py` to automatically include Obsidian Calendar tags when generating new Daily Notes.

### Planned (Phase 5)
- Phase 5: Offline visual translation with locomo-v2 for OCR/captioning of extracted media.
