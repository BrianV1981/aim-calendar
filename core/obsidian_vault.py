#!/usr/bin/env python3
"""
Obsidian Vault & Calendar UI Integration Engine.
Initializes a formal Obsidian Vault structure (.obsidian/) and ensures
Daily Notes contain YAML frontmatter tags for native Obsidian Calendar rendering.
"""

import os
import sys
import glob
import json
import re
import shutil
import argparse
import subprocess
from typing import List, Dict, Tuple, Optional

DEFAULT_TAGS = ["daily-note", "calendar", "timeline", "exocortex"]

# Built-in fallback manifest for Liam Cain's calendar plugin
CALENDAR_MANIFEST = {
    "id": "calendar",
    "name": "Calendar",
    "version": "1.5.10",
    "minAppVersion": "0.9.11",
    "description": "Calendar view of your daily notes",
    "author": "Liam Cain",
    "authorUrl": "https://github.com/liamcain/",
    "isDesktopOnly": False
}

# Default Calendar configuration (weeks start on Sunday, 250 words per dot)
CALENDAR_DATA = {
    "shouldConfirmBeforeCreate": False,
    "weekStart": "sunday",
    "wordsPerDot": 250,
    "showWeeklyNote": False
}

CORE_PLUGINS_CONFIG = {
    "file-explorer": True,
    "global-search": True,
    "switcher": True,
    "graph": True,
    "backlink": True,
    "canvas": True,
    "outgoing-link": True,
    "tag-pane": True,
    "properties": True,
    "page-preview": True,
    "daily-notes": True,
    "templates": True,
    "note-composer": True,
    "command-palette": True,
    "editor-status": True,
    "bookmarks": True,
    "outline": True,
    "word-count": True,
    "file-recovery": True
}


def resolve_repo_path(p: str) -> str:
    """Resolve path relative to git common root directory or current working dir."""
    if os.path.isabs(p):
        return p
    try:
        common_git = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        common_root = os.path.dirname(os.path.abspath(common_git))
        candidate = os.path.join(common_root, p)
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    if os.path.exists(p):
        return p
    return p


def get_plugin_asset_dir() -> str:
    """Locate local assets directory for the calendar plugin."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(module_dir, "assets", "obsidian_calendar")
    return asset_dir


def setup_vault(
    vault_dir: str,
    daily_notes_folder: str = "daily_notes",
    media_folder: str = "media",
    install_plugin: bool = True
) -> Dict[str, str]:
    """
    Initializes a formal Obsidian Vault structure within `vault_dir`.
    Creates .obsidian/, app.json, core-plugins.json, daily-notes.json,
    and installs the Calendar community plugin.
    """
    vault_dir = os.path.abspath(vault_dir)
    obsidian_dir = os.path.join(vault_dir, ".obsidian")
    os.makedirs(obsidian_dir, exist_ok=True)

    created_files = {}

    # 1. app.json
    app_config = {
        "attachmentFolderPath": media_folder,
        "newFileLocation": "folder",
        "newFileFolderPath": daily_notes_folder,
        "useMarkdownLinks": True,
        "userIgnoreFilters": [
            "sms_raw/",
            ".git/",
            "TalkerACR/",
            "*.lance/"
        ]
    }
    app_json_path = os.path.join(obsidian_dir, "app.json")
    with open(app_json_path, "w", encoding="utf-8") as f:
        json.dump(app_config, f, indent=2)
    created_files["app.json"] = app_json_path

    # 2. core-plugins.json
    core_plugins_path = os.path.join(obsidian_dir, "core-plugins.json")
    with open(core_plugins_path, "w", encoding="utf-8") as f:
        json.dump(CORE_PLUGINS_CONFIG, f, indent=2)
    created_files["core-plugins.json"] = core_plugins_path

    # 3. daily-notes.json
    daily_notes_config = {
        "format": "YYYY-MM-DD",
        "folder": daily_notes_folder,
        "template": ""
    }
    daily_notes_path = os.path.join(obsidian_dir, "daily-notes.json")
    with open(daily_notes_path, "w", encoding="utf-8") as f:
        json.dump(daily_notes_config, f, indent=2)
    created_files["daily-notes.json"] = daily_notes_path

    # 4. community-plugins.json
    comm_plugins_path = os.path.join(obsidian_dir, "community-plugins.json")
    enabled_plugins = ["calendar"]
    if os.path.exists(comm_plugins_path):
        try:
            with open(comm_plugins_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    for ep in existing:
                        if ep not in enabled_plugins:
                            enabled_plugins.append(ep)
        except Exception:
            pass
    with open(comm_plugins_path, "w", encoding="utf-8") as f:
        json.dump(enabled_plugins, f, indent=2)
    created_files["community-plugins.json"] = comm_plugins_path

    # 5. plugins/calendar/
    if install_plugin:
        plugin_dir = os.path.join(obsidian_dir, "plugins", "calendar")
        os.makedirs(plugin_dir, exist_ok=True)

        manifest_path = os.path.join(plugin_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(CALENDAR_MANIFEST, f, indent=2)
        created_files["manifest.json"] = manifest_path

        data_path = os.path.join(plugin_dir, "data.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(CALENDAR_DATA, f, indent=2)
        created_files["data.json"] = data_path

        # Copy or deploy main.js
        main_js_dest = os.path.join(plugin_dir, "main.js")
        asset_dir = get_plugin_asset_dir()
        asset_main_js = os.path.join(asset_dir, "main.js")

        if os.path.exists(asset_main_js):
            shutil.copyfile(asset_main_js, main_js_dest)
            created_files["main.js"] = main_js_dest
        else:
            # Fallback placeholder if asset not present
            if not os.path.exists(main_js_dest):
                with open(main_js_dest, "w", encoding="utf-8") as f:
                    f.write("/* Liam Cain Calendar Plugin bundle placeholder */\n")
                created_files["main.js"] = main_js_dest

    return created_files


def parse_frontmatter_tags(frontmatter_text: str) -> Tuple[List[str], Dict[str, str]]:
    """
    Parses YAML frontmatter block into a list of tags and a dictionary of other key-value pairs.
    """
    tags = []
    other_fields = {}
    lines = frontmatter_text.splitlines()

    in_tag_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("tags:"):
            # Check inline list: tags: [foo, bar]
            match = re.match(r"tags:\s*\[(.*?)\]", stripped)
            if match:
                inline_tags = [t.strip().strip("'\"#") for t in match.group(1).split(",") if t.strip()]
                tags.extend(inline_tags)
                in_tag_list = False
            else:
                in_tag_list = True
            continue

        if in_tag_list:
            if stripped.startswith("-"):
                tag_val = stripped.lstrip("-").strip().strip("'\"#")
                if tag_val:
                    tags.append(tag_val)
                continue
            else:
                in_tag_list = False

        # Other key-values
        if ":" in line and not in_tag_list:
            parts = line.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            other_fields[key] = val

    return tags, other_fields


def build_frontmatter(date_val: str, type_val: str, tags: List[str], extra_fields: Dict[str, str] = None) -> str:
    """Generates standard YAML frontmatter string."""
    lines = ["---", f"date: {date_val}"]
    if type_val:
        lines.append(f"type: {type_val}")

    if extra_fields:
        for k, v in extra_fields.items():
            if k not in ("date", "type", "tags"):
                lines.append(f"{k}: {v}")

    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {tag}")

    lines.append("---")
    return "\n".join(lines)


def update_daily_note_frontmatter(
    file_path: str,
    required_tags: List[str] = DEFAULT_TAGS,
    dry_run: bool = False
) -> bool:
    """
    Inspects a Daily Note markdown file and updates its YAML frontmatter
    to ensure it contains the required calendar tags.
    Returns True if the file was modified, False if no change was necessary.
    """
    if not os.path.exists(file_path):
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match existing frontmatter
    fm_pattern = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
    match = fm_pattern.match(content)

    filename = os.path.basename(file_path)
    base_name = os.path.splitext(filename)[0]

    # Inferred date
    inferred_date = base_name if re.match(r"^\d{4}-\d{2}-\d{2}$", base_name) else "unknown"

    if match:
        fm_raw = match.group(1)
        body = content[match.end():]
        existing_tags, other_fields = parse_frontmatter_tags(fm_raw)

        # Check if all required tags are already present
        missing_tags = [t for t in required_tags if t not in existing_tags]
        if not missing_tags and "date" in other_fields:
            return False  # Up to date

        # Combine tags preserving order
        combined_tags = list(existing_tags)
        for t in required_tags:
            if t not in combined_tags:
                combined_tags.append(t)

        date_val = other_fields.get("date", inferred_date)
        type_val = other_fields.get("type", "daily_exocortex")

        new_fm = build_frontmatter(date_val, type_val, combined_tags, other_fields)
        new_content = f"{new_fm}\n{body}"
    else:
        # No existing frontmatter
        new_fm = build_frontmatter(inferred_date, "daily_exocortex", required_tags)
        new_content = f"{new_fm}\n{content}"

    if dry_run:
        return True

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def migrate_daily_notes_tags(
    notes_dir: str,
    required_tags: List[str] = DEFAULT_TAGS,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Iterates over all markdown files in notes_dir and applies update_daily_note_frontmatter.
    Returns (updated_count, total_count).
    """
    if not os.path.exists(notes_dir):
        print(f"[WARN] Daily notes directory {notes_dir} does not exist.")
        return 0, 0

    files = sorted(glob.glob(os.path.join(notes_dir, "*.md")))
    total_count = len(files)
    updated_count = 0

    for idx, filepath in enumerate(files, 1):
        modified = update_daily_note_frontmatter(filepath, required_tags=required_tags, dry_run=dry_run)
        if modified:
            updated_count += 1

    return updated_count, total_count


def main():
    parser = argparse.ArgumentParser(description="Initialize Obsidian Vault & Calendar UI integration.")
    parser.add_argument("--vault-dir", default=None, help="Directory to initialize as Obsidian Vault.")
    parser.add_argument("--daily-notes-dir", default="conversations/daily_notes", help="Directory containing Daily Notes.")
    parser.add_argument("--media-dir", default="media", help="Attachment folder path relative to vault.")
    parser.add_argument("--migrate-tags", action="store_true", help="Migrate existing Daily Notes frontmatter with calendar tags.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate tag migration without writing changes to disk.")
    parser.add_argument("--no-plugin", action="store_true", help="Skip installing the Calendar community plugin bundle.")
    args = parser.parse_args()

    notes_dir = resolve_repo_path(args.daily_notes_dir)

    # If vault-dir not explicitly specified, initialize at conversations/ and repo root
    vault_targets = []
    if args.vault_dir:
        vault_targets.append(resolve_repo_path(args.vault_dir))
    else:
        # Default: initialize both conversations/ (direct vault) and repo root (workspace vault)
        conv_dir = resolve_repo_path("conversations")
        if os.path.exists(conv_dir):
            vault_targets.append(conv_dir)
        try:
            common_git = subprocess.check_output(
                ["git", "rev-parse", "--git-common-dir"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            common_root = os.path.dirname(os.path.abspath(common_git))
            if common_root not in vault_targets:
                vault_targets.append(common_root)
        except Exception:
            pass

    print("=== OBSIDIAN VAULT INTEGRATION ===")
    for vt in vault_targets:
        is_root = (vt == os.path.abspath("."))
        daily_folder = "conversations/daily_notes" if is_root else "daily_notes"
        media_folder = "conversations/media" if is_root else "media"

        print(f"\nInitializing Obsidian Vault at: {vt}")
        res = setup_vault(
            vault_dir=vt,
            daily_notes_folder=daily_folder,
            media_folder=media_folder,
            install_plugin=(not args.no_plugin)
        )
        print(f"  [OK] Configured {len(res)} files (.obsidian/ config & Calendar plugin).")

    if args.migrate_tags:
        print(f"\nScanning Daily Notes in {notes_dir} for Calendar tags...")
        up_count, total_count = migrate_daily_notes_tags(notes_dir, dry_run=args.dry_run)
        mode_str = "[DRY-RUN] Would update" if args.dry_run else "Successfully updated"
        print(f"  {mode_str} {up_count} of {total_count} Daily Notes with tags: {DEFAULT_TAGS}")

    print("\n[SUCCESS] Obsidian Vault & Calendar UI integration ready.")


if __name__ == "__main__":
    main()
