# Changelog

All notable changes to the **A.I.M. Calendar** (formerly TalkerACR Ingestion) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha] - 2026-09-03
### Added
- **Project Rebrand:** Officially transitioned architecture from proprietary TalkerACR ingestion script to the agnostic `A.I.M. Calendar` Exocortex ecosystem.
- **SMS Streaming Parser:** Implemented `core/ingest_sms.py` with `xml.etree.ElementTree.iterparse` to allow local environments to parse massive (10GB+) Android SMS/Call Log XML backups without OOM memory crashes.
- **Chronological Note Generation:** Pipeline now automatically groups unstructured texts and phone calls into Obsidian-compatible `YYYY-MM-DD.md` Daily Notes.
- **Background Sync Daemon (Issue #4):** Implemented `core/sync_daemon.sh` to automate rclone cloud synchronization from Google Drive into `TalkerACR/` and `conversations/sms_raw/` with systemd timer integration (`aim-sync.timer`) and downstream pipeline triggers.
- **Multimodal MMS Extraction Pipeline (Issue #1):** Refactored `core/ingest_sms.py` to stream and extract Base64 rich media payloads from `<mms>` tags into `conversations/media/` with MD5 hash deduplication, relative Markdown links (`![MMS Image](...)`), and multiline-preserving chronological sorting.
- **LanceDB Vector Injection for Daily Notes (Issue #2):** Implemented `core/ingest_to_lancedb.py` with sliding window temporal chunking, date anchoring (`[Date: YYYY-MM-DD]`), multiline bullet group preservation, idempotent session tracking against `talker_cartridge.lance` table `fragments` (`type: "daily_note"`), 768-dim `nomic-embed-text` embeddings, table optimization, and FTS indexing.

### Changed
- Replaced the default Git branch from `master` to `main`.
- Cleaned up obsolete documentation (`TOOLS.md`).
- Integrated automated downstream LanceDB vector injection into `core/sync_daemon.sh`.

### Planned (Phase 4 & 5)
- Issue #3: Phase 4: Obsidian Calendar UI / Vault Integration.
- Phase 5: Offline visual translation with locomo-v2 for OCR/captioning of extracted media.
