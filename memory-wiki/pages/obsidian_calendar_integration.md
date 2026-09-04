# Obsidian Calendar UI & Vault Integration

## Overview
The **A.I.M. Calendar** vault integration engine (`core/obsidian_vault.py`) transforms generic chronological Daily Notes (`conversations/daily_notes/YYYY-MM-DD.md`) and extracted multimodal media (`conversations/media/`) into a turnkey, production-ready **Obsidian Vault**.

When opened in Obsidian, users have immediate access to a graphical calendar view rendered by Liam Cain's official Calendar plugin, deep search via tags, and chronological timeline navigation.

---

## Vault Architecture

Obsidian configuration is initialized in two standard locations:
1. **Direct Vault (`conversations/.obsidian/`):** For operators who open the `conversations/` directory directly as an Obsidian Vault.
2. **Workspace Vault (`.obsidian/`):** For operators who open the repository root as their master Obsidian workspace.

### Core Configuration Files

* **`app.json`**:
  * Configures `attachmentFolderPath` to point to `media` (or `conversations/media`).
  * Sets `newFileFolderPath` to `daily_notes`.
  * Enables `useMarkdownLinks: true` to prevent proprietary wiki-link lock-in.
  * Adds ignore filters for `sms_raw/`, `TalkerACR/`, and `*.lance/`.
* **`core-plugins.json`**:
  * Activates `daily-notes`, `tag-pane`, `graph`, `file-explorer`, `global-search`, `backlink`, `properties`, and `page-preview`.
* **`daily-notes.json`**:
  * Maps daily note format `YYYY-MM-DD` directly to the `daily_notes` folder without template prompts.
* **`community-plugins.json`**:
  * Registers `["calendar"]` in the active community plugin list.
* **`plugins/calendar/`**:
  * Contains `manifest.json`, `data.json`, and `main.js`.
  * Preconfigured with:
    * `weekStart: "sunday"`
    * `wordsPerDot: 250` (dots reflect communications volume)
    * `shouldConfirmBeforeCreate: false`

---

## Frontmatter Standardization

Daily Notes follow strict YAML frontmatter standards so that Obsidian's tag pane, graph view, and calendar dot counters function out-of-the-box:

```yaml
---
date: 2026-09-02
type: daily_exocortex
tags:
  - daily-note
  - calendar
  - timeline
  - exocortex
---
# Daily Log: 2026-09-02

- **[07:22 AM] Received Text** (+13238701595): "Message content..."
- **[08:41 AM] Incoming Call** with +13015200724 (Duration: 76s)
```

### Automation & Idempotency
1. **Automatic Tagging on Ingestion:** `core/ingest_sms.py` emits the complete frontmatter block whenever a new Daily Note is spawned.
2. **Batch Migration Tool:** `python3 core/obsidian_vault.py --migrate-tags` parses all existing notes and idempotently injects the tags without duplicating pre-existing tags or modifying the underlying body content.

---

## Operations & CLI Usage

### Initialize Vault & Migrate Tags
```bash
python3 core/obsidian_vault.py --migrate-tags
```

### Dry Run Migration
```bash
python3 core/obsidian_vault.py --migrate-tags --dry-run
```

### Custom Vault Directory
```bash
python3 core/obsidian_vault.py --vault-dir /path/to/vault --migrate-tags
```
