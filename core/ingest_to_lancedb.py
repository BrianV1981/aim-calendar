import os
import sys
import subprocess
import glob
import json
import re
import argparse
import traceback
from typing import List, Dict, Tuple, Optional, Callable
import pyarrow as pa
import lancedb

# Schema for talker_cartridge.lance fragments table
LANCEDB_SCHEMA = pa.schema([
    pa.field("fragment_id", pa.int64()),
    pa.field("session_id", pa.string()),
    pa.field("type", pa.string()),
    pa.field("content", pa.string()),
    pa.field("timestamp", pa.string()),
    pa.field("metadata", pa.string()),
    pa.field("parent_id", pa.int64()),
    pa.field("source_db", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), 768))
])

# Attempt import of aim_memory embeddings
try:
    sys.path.append("/home/kingb/aim-memory")
    from aim_memory.embeddings import get_embedding as aim_get_embedding
except ImportError:
    aim_get_embedding = None


def default_get_embedding(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
    """Retrieves 768-dim vector embedding via aim_memory or local Ollama."""
    if aim_get_embedding is not None:
        try:
            vec = aim_get_embedding(text, task_type=task_type)
            if vec and len(vec) == 768:
                return vec
        except Exception:
            pass

    # Direct fallback to local Ollama instance
    try:
        import requests
        response = requests.post("http://127.0.0.1:11434/api/embeddings", json={
            "model": "nomic-embed-text:latest",
            "prompt": text
        }, timeout=30)
        if response.status_code == 200:
            vec = response.json().get("embedding", [])
            if len(vec) == 768:
                return vec
    except Exception as e:
        print(f"Error fetching embedding from Ollama: {e}")

    return []


def parse_daily_note(filepath: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Parses YAML frontmatter and extracts chronological entry blocks
    (including multi-line media links and captions) from a Daily Note.
    """
    if not os.path.exists(filepath):
        return {}, []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    metadata = {
        "filename": os.path.basename(filepath),
        "date": "unknown",
        "type": "daily_exocortex"
    }

    in_frontmatter = False
    in_header = True
    entries = []
    current_entry = []

    for line in lines:
        stripped = line.strip()

        # Parse YAML frontmatter
        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            else:
                in_frontmatter = False
                continue

        if in_frontmatter:
            if ":" in line:
                key, val = line.split(":", 1)
                metadata[key.strip()] = val.strip().replace('"', '').replace("'", "")
            continue

        # Skip header lines before the first log bullet
        if in_header:
            if line.startswith("# Daily Log:"):
                in_header = False
            continue

        # Group log blocks by `- **[` bullet points
        if line.startswith("- **["):
            if current_entry:
                entries.append("".join(current_entry).strip())
                current_entry = []
            current_entry.append(line)
        elif current_entry:
            # Continuation line (indented attachment, markdown image, or caption)
            current_entry.append(line)

    if current_entry:
        entries.append("".join(current_entry).strip())

    # Fallback to date in filename if missing in frontmatter
    if metadata["date"] == "unknown":
        match = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(filepath))
        if match:
            metadata["date"] = match.group(1)

    return metadata, entries


def chunk_daily_note(
    entries: List[str],
    date_str: str,
    target_chunk_chars: int = 1200,
    overlap_entries: int = 1
) -> List[Tuple[str, Dict]]:
    """
    Groups chronological daily note entries into overlapping semantic windows.
    Prefixes each chunk with a temporal anchor [Date: YYYY-MM-DD].
    """
    if not entries:
        return []

    chunks = []
    total_entries = len(entries)
    i = 0
    chunk_index = 0

    while i < total_entries:
        current_chunk_entries = []
        char_count = 0
        j = i

        while j < total_entries:
            entry = entries[j]
            entry_len = len(entry)

            # If adding this entry exceeds target and we already have entries, break
            if char_count + entry_len > target_chunk_chars and current_chunk_entries:
                break

            current_chunk_entries.append(entry)
            char_count += entry_len
            j += 1

        if not current_chunk_entries:
            # Entry itself is larger than target_chunk_chars; include it alone
            current_chunk_entries.append(entries[i])
            j = i + 1

        # Build chunk text with temporal date anchor
        chunk_body = "\n".join(current_chunk_entries)
        chunk_text = f"[Date: {date_str}]\n{chunk_body}".strip()

        # Extract contacts mentioned in this chunk
        contacts = list(set(re.findall(r"\(([^)]+)\)", chunk_body)))

        chunk_meta = {
            "date": date_str,
            "chunk_index": chunk_index,
            "entry_count": len(current_chunk_entries),
            "contacts": contacts
        }

        chunks.append((chunk_text, chunk_meta))
        chunk_index += 1

        # Advance window by stepping forward (minus overlap)
        step = max(1, len(current_chunk_entries) - overlap_entries)
        if j >= total_entries:
            break
        i += step

    return chunks


def ingest_daily_notes(
    db_path: str = "talker_cartridge.lance",
    input_dir: str = "conversations/daily_notes",
    limit: int = 0,
    recent: int = 0,
    single_file: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 200,
    embed_fn: Optional[Callable[[str], List[float]]] = None
) -> int:
    """
    Scans Daily Notes, chunks them chronologically, and injects them
    into the LanceDB fragments table with 768-dim embeddings.
    """
    if embed_fn is None:
        embed_fn = default_get_embedding

    if not os.path.exists(input_dir):
        print(f"[WARN] Input directory {input_dir} does not exist.")
        return 0

    print(f"Connecting to LanceDB at {db_path}...")
    db = lancedb.connect(db_path)

    # Open or create fragments table
    try:
        table = db.open_table("fragments")
    except Exception:
        table = db.create_table("fragments", schema=LANCEDB_SCHEMA)

    # Idempotency check: Find files already indexed under type 'daily_note'
    completed_files = set()
    if not force:
        try:
            df = table.search().where("type = 'daily_note'").select(["session_id"]).to_pandas()
            if not df.empty and "session_id" in df.columns:
                completed_files = set(df["session_id"].unique())
                print(f"Found {len(completed_files)} already processed Daily Notes in LanceDB.")
        except Exception as e:
            print(f"Idempotency check note: {e}")

    # Determine current max fragment_id
    current_id = 1
    try:
        df_id = table.search().select(["fragment_id"]).limit(1000000).to_pandas()
        if not df_id.empty and "fragment_id" in df_id.columns:
            max_id = df_id["fragment_id"].max()
            if max_id is not None and not (isinstance(max_id, float) and max_id != max_id):
                current_id = int(max_id) + 1
    except Exception:
        pass

    # Collect markdown files
    if single_file:
        files = [single_file]
    else:
        files = sorted(glob.glob(os.path.join(input_dir, "*.md")))

    if recent > 0:
        files = files[-recent:]
        print(f"Filtering to the most recent {recent} Daily Notes.")
    elif limit > 0:
        files = files[:limit]
        print(f"Filtering to {limit} Daily Notes.")

    total_files = len(files)
    print(f"Found {total_files} Daily Notes to process.")

    total_chunks_inserted = 0
    batch_records = []
    processed_files = 0
    skipped_files = 0

    for idx, filepath in enumerate(files, 1):
        filename = os.path.basename(filepath)

        if filename in completed_files and not force:
            skipped_files += 1
            continue

        metadata, entries = parse_daily_note(filepath)
        date_str = metadata.get("date", "unknown")

        if not entries:
            continue

        # If force re-indexing, remove prior entries for this file
        if force and not dry_run and filename in completed_files:
            try:
                table.delete(f"session_id = '{filename}'")
            except Exception:
                pass

        chunks = chunk_daily_note(entries, date_str=date_str)

        if dry_run:
            print(f"[DRY-RUN] {filename} -> {len(chunks)} chunks planned.")
            total_chunks_inserted += len(chunks)
            processed_files += 1
            continue

        for chunk_text, chunk_meta in chunks:
            if len(chunk_text) < 10:
                continue

            vec = embed_fn(chunk_text)
            if not vec or len(vec) != 768:
                print(f"[WARN] Failed to generate 768-dim embedding for chunk in {filename}. Skipping chunk.")
                continue

            payload_meta = {
                "source_file": filename,
                "date": date_str,
                "chunk_index": str(chunk_meta.get("chunk_index", 0)),
                "contacts": chunk_meta.get("contacts", [])
            }

            batch_records.append({
                "fragment_id": current_id,
                "session_id": filename,
                "type": "daily_note",
                "content": chunk_text,
                "timestamp": date_str,
                "metadata": json.dumps(payload_meta),
                "parent_id": 0,
                "source_db": "aim_memory",
                "vector": vec
            })
            current_id += 1
            total_chunks_inserted += 1

        processed_files += 1

        # Flush batch periodically
        if len(batch_records) >= batch_size:
            table.add(batch_records)
            print(f"  ...flushed {len(batch_records)} chunks to LanceDB (Files: {idx}/{total_files})")
            batch_records = []

    # Flush remaining
    if batch_records and not dry_run:
        table.add(batch_records)
        print(f"  ...flushed final {len(batch_records)} chunks to LanceDB.")

    print(f"\n=== DAILY NOTE INGESTION COMPLETE ===")
    print(f"Files processed: {processed_files} (Skipped already indexed: {skipped_files})")
    print(f"Total chunks injected: {total_chunks_inserted}")

    if not dry_run and total_chunks_inserted > 0:
        print("Optimizing LanceDB fragments table...")
        try:
            if hasattr(table, "optimize"):
                table.optimize()
            elif hasattr(table, "compact_files"):
                table.compact_files()
            print("Optimization complete.")
        except Exception as e:
            print(f"Optimization note: {e}")

        print("Rebuilding FTS index on 'content'...")
        try:
            try:
                from lancedb.index import FTS
                table.create_index("content", config=FTS(), replace=True)
            except Exception:
                table.create_fts_index("content", replace=True)
            print("FTS index ready.")
        except Exception as e:
            print(f"FTS index note: {e}")

    return total_chunks_inserted


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


def main():
    parser = argparse.ArgumentParser(description="Inject chronological Daily Notes into LanceDB.")
    parser.add_argument("--db-path", default="talker_cartridge.lance", help="Path to LanceDB store.")
    parser.add_argument("--input-dir", default="conversations/daily_notes", help="Directory of Daily Notes.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files to process.")
    parser.add_argument("--recent", type=int, default=0, help="Process the N most recent Daily Notes.")
    parser.add_argument("--file", default=None, help="Process a single specific file.")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of already processed files.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate parsing and chunking without embedding.")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for LanceDB writes.")
    args = parser.parse_args()

    db_path = resolve_repo_path(args.db_path)
    input_dir = resolve_repo_path(args.input_dir)

    ingest_daily_notes(
        db_path=db_path,
        input_dir=input_dir,
        limit=args.limit,
        recent=args.recent,
        single_file=args.file,
        force=args.force,
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()
