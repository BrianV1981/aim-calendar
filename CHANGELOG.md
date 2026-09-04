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

### Changed
- Replaced the default Git branch from `master` to `main`.
- Cleaned up obsolete documentation (`TOOLS.md`).

### Planned (Phase 3 & 4)
- Issue #2: Injecting compiled Daily Notes into LanceDB vector database.
- Phase 5: Offline visual translation with locomo-v2 for OCR/captioning of extracted media.
