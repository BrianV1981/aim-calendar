import os
import re
import glob
import json
import argparse
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
from core.llm_provider import describe_media, resolve_provider

MEDIA_LINK_RE = re.compile(
    r"^(\s*)(?:!\[MMS Image\]|\[MMS Video\]|\[MMS Audio\]|\[MMS Attachment\]|!\[Media\]|\[Document\])\(([^)]+)\)\s*$"
)
VISUAL_CONTEXT_PREFIX = "> [Visual Context:"


def load_translation_cache(cache_path: str) -> Dict[str, Dict]:
    """Loads the persistent visual translation cache from disk."""
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_translation_cache(cache_path: str, cache_data: Dict[str, Dict]) -> None:
    """Saves the persistent visual translation cache to disk."""
    if not cache_path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, sort_keys=True)


def resolve_media_path(note_dir: str, media_dir: str, rel_link: str) -> str:
    """Resolves a relative Markdown media link to an existing filesystem path."""
    candidate = os.path.normpath(os.path.join(note_dir, rel_link))
    if os.path.isfile(candidate):
        return candidate
    fallback = os.path.join(media_dir, os.path.basename(rel_link))
    return fallback


def translate_daily_notes_media(
    notes_dir: str = "conversations/daily_notes",
    media_dir: str = "conversations/media",
    cache_path: Optional[str] = None,
    single_file: Optional[str] = None,
    recent: int = 0,
    limit: int = 0,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    describe_fn: Optional[Callable[[str], str]] = None,
) -> Dict[str, object]:
    """
    Scans Daily Notes for MMS media references, generates OCR/visual descriptions
    via the active LLM provider (or cache), and injects `> [Visual Context: ...]`
    blockquotes directly beneath each media reference.
    """
    if cache_path is None:
        cache_path = os.path.join(media_dir, ".visual_translation_cache.json")

    cache = load_translation_cache(cache_path)
    active_provider = resolve_provider(provider)

    if single_file:
        note_files = [single_file] if os.path.isfile(single_file) else []
    elif os.path.isdir(notes_dir):
        note_files = sorted(glob.glob(os.path.join(notes_dir, "*.md")))
    else:
        note_files = []

    if recent > 0 and not single_file:
        note_files = note_files[-recent:]

    notes_updated = 0
    media_translated = 0
    cache_hits = 0
    modified_files: List[str] = []
    cache_dirty = False

    for note_path in note_files:
        if limit > 0 and media_translated >= limit:
            break

        try:
            with open(note_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue

        note_dir = os.path.dirname(os.path.abspath(note_path))
        new_lines: List[str] = []
        note_modified = False
        idx = 0
        total_lines = len(lines)

        while idx < total_lines:
            line = lines[idx]
            new_lines.append(line)
            match = MEDIA_LINK_RE.match(line.rstrip("\r\n"))

            if not match:
                idx += 1
                continue

            indent, rel_link = match.group(1), match.group(2)
            # Check if the next line(s) in this entry already contain a Visual Context blockquote
            has_existing_context = False
            existing_context_idx = -1
            lookahead = idx + 1
            while lookahead < total_lines:
                next_stripped = lines[lookahead].strip()
                if next_stripped.startswith("- **[") or MEDIA_LINK_RE.match(lines[lookahead].rstrip("\r\n")):
                    break
                if next_stripped.startswith(VISUAL_CONTEXT_PREFIX):
                    has_existing_context = True
                    existing_context_idx = lookahead
                    break
                lookahead += 1

            if has_existing_context and not force:
                idx += 1
                continue

            if limit > 0 and media_translated >= limit:
                idx += 1
                continue

            media_path = resolve_media_path(note_dir, media_dir, rel_link)
            if not os.path.isfile(media_path):
                idx += 1
                continue

            media_key = os.path.basename(media_path)
            caption = None

            if not force and media_key in cache and cache[media_key].get("caption"):
                caption = cache[media_key]["caption"]
                cache_hits += 1
            else:
                if dry_run:
                    print(f"[DRY-RUN] Would translate media: {media_key} in {os.path.basename(note_path)}")
                    media_translated += 1
                    idx += 1
                    continue

                try:
                    if describe_fn is not None:
                        caption = describe_fn(media_path)
                    else:
                        caption = describe_media(
                            media_path,
                            provider=provider,
                            model=model,
                        )
                except Exception as e:
                    print(f"[WARN] Visual translation failed for {media_key}: {e}")
                    idx += 1
                    continue

                if caption:
                    cache[media_key] = {
                        "caption": caption,
                        "provider": active_provider,
                        "model": model or "default",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    cache_dirty = True

            if caption:
                clean_caption = " ".join(caption.strip().splitlines()).strip()
                context_line = f"{indent or '  '}{VISUAL_CONTEXT_PREFIX} {clean_caption}]\n"

                if has_existing_context and force and existing_context_idx == idx + 1:
                    # Replace the existing visual context line right after media link
                    new_lines.append(context_line)
                    idx += 2
                    note_modified = True
                    media_translated += 1
                    continue
                else:
                    new_lines.append(context_line)
                    note_modified = True
                    media_translated += 1

            idx += 1

        if note_modified and not dry_run:
            with open(note_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            notes_updated += 1
            modified_files.append(note_path)

    if cache_dirty and not dry_run:
        save_translation_cache(cache_path, cache)

    return {
        "notes_updated": notes_updated,
        "media_translated": media_translated,
        "cache_hits": cache_hits,
        "modified_files": modified_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="locomo-v2 Multimodal Visual Translation Pipeline for A.I.M. Calendar Daily Notes."
    )
    parser.add_argument("--notes-dir", default="conversations/daily_notes", help="Directory containing Daily Notes.")
    parser.add_argument("--media-dir", default="conversations/media", help="Directory containing extracted MMS media.")
    parser.add_argument("--cache", default=None, help="Path to .visual_translation_cache.json.")
    parser.add_argument("--file", default=None, help="Translate media in a single Daily Note file.")
    parser.add_argument("--recent", type=int, default=0, help="Only scan the N most recent Daily Notes.")
    parser.add_argument("--limit", type=int, default=0, help="Max number of media items to translate in this run.")
    parser.add_argument("--provider", choices=["auto", "ollama", "gemini"], default=None, help="LLM provider override.")
    parser.add_argument("--model", default=None, help="Specific vision model override.")
    parser.add_argument("--force", action="store_true", help="Re-translate media even if cached or already annotated.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without calling models or modifying files.")
    args = parser.parse_args()

    stats = translate_daily_notes_media(
        notes_dir=args.notes_dir,
        media_dir=args.media_dir,
        cache_path=args.cache,
        single_file=args.file,
        recent=args.recent,
        limit=args.limit,
        provider=args.provider,
        model=args.model,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(
        f"[LOCOMO-V2] Complete | Notes updated: {stats['notes_updated']} | "
        f"Media annotated: {stats['media_translated']} (Cache hits: {stats['cache_hits']})"
    )


if __name__ == "__main__":
    main()
