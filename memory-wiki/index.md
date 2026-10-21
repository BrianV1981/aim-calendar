# Project Wiki Index

Welcome to the **A.I.M. Calendar** Knowledge Base. This repository manages the lifecycle of processing, diarizing, transcribing, visually translating, and semantically indexing thousands of personal phone calls, SMS/MMS logs, and calendar events into a zero-touch, chronological Enterprise Exocortex timeline.

## Core Concepts
*   [Pipeline Architecture](pages/architecture.md) - The 7-phase strategy for audio classification, diarization, SMS/MMS streaming ingestion, LanceDB RAG, background cloud sync, Obsidian UI, and calendar synchronization.
*   [Multimodal MMS Translation Pipeline](pages/mms_multimodal_translation.md) - Hybrid/offline `locomo-v2` vision translation (`core/llm_provider.py` + `core/translate_media.py`), `.visual_translation_cache.json`, and `> [Visual Context: ...]` injection.
*   [Calendar Intelligence & Cloud Synchronization](pages/calendar_intelligence_sync.md) - Dual-track Retrospective Daily Dossiers (`A.I.M. Activity Log`) and Prospective Appointments (`A.I.M. Appointments`), `.ics` export, and deterministic Google Calendar API v3 upsert (`core/calendar_sync.py`).
*   [Obsidian Calendar UI & Vault Integration](pages/obsidian_calendar_integration.md) - Turnkey vault architecture, Calendar community plugin preconfiguration, and daily notes frontmatter tag standards.
*   [Antigravity UI & Media Guidelines](pages/antigravity_ui_guidelines.md) - Rules for sharing and rendering playable audio files in the Windows 11/Android UI.

## Data Processing Runbooks
*   [LanceDB Cartridge Generation](pages/lancedb_cartridge.md) - Explains how audio transcripts and Daily Notes are chunked, embedded, and compacted into the modular memory cartridge without disk bloat.
*   [Community & Open Source Migration](pages/community_migration.md) - Guidelines on environment variables (`AIM_MEMORY_PATH`, `.env`), backup pruning, and repository decoupling for external collaborators.
