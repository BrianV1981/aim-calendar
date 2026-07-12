import os
import json
import traceback
from faster_whisper import WhisperModel
import shutil

# Configuration
SOURCE_DIR = "TalkerACR/All"
PROPS_DIR = os.path.join(SOURCE_DIR, ".props")
OUTPUT_DIR = "conversations"
ERROR_LOG = "ingest_errors.log"

def setup_directories():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def get_metadata(amr_filename):
    """Attempt to find and parse the TalkerACR .json props file."""
    base_name = os.path.splitext(amr_filename)[0]
    json_path = os.path.join(PROPS_DIR, f"{base_name}.json")
    
    metadata = {
        "duration": "unknown",
        "callee": "unknown",
        "platform": "unknown",
        "date": "unknown"
    }
    
    # Parse basic details from filename (e.g., facebook_20231230-172824_5_28.amr)
    parts = base_name.split("_")
    if len(parts) >= 2:
        metadata["platform"] = parts[0]
        metadata["date"] = parts[1] # YYYYMMDD-HHMMSS
        
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                props = json.load(f)
                if "duration" in props:
                    # duration is usually in ms
                    dur_ms = int(props["duration"])
                    metadata["duration"] = f"{dur_ms / 1000:.2f}s"
                if "callee" in props:
                    metadata["callee"] = props["callee"]
        except Exception as e:
            print(f"Warning: Could not parse metadata for {amr_filename}: {e}")
            
    return metadata

def format_obsidian_markdown(metadata, transcript):
    """Creates the Markdown string with YAML frontmatter for Obsidian."""
    md = "---\n"
    md += f"platform: {metadata.get('platform')}\n"
    md += f"date: {metadata.get('date')}\n"
    md += f"contact: \"{metadata.get('callee')}\"\n"
    md += f"duration: {metadata.get('duration')}\n"
    md += "tags: [phone-call, talker-acr]\n"
    md += "---\n\n"
    md += "# Transcript\n\n"
    md += transcript
    return md

def log_error(filename, error_msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{filename}] ERROR: {error_msg}\n")

def process_all_files():
    setup_directories()
    
    print("Loading Whisper Model...")
    # Base model. Using int8 on CPU to be universally compatible.
    # We can bump this to 'small' or 'medium' if you want better accuracy later.
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    # Find all AMR files
    amr_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".amr")]
    total_files = len(amr_files)
    print(f"Found {total_files} AMR files to process.")
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    for index, amr_file in enumerate(amr_files, 1):
        base_name = os.path.splitext(amr_file)[0]
        final_md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md")
        tmp_md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md.tmp")
        
        # 1. CRASH PROOF CHECK: Skip if already fully processed
        if os.path.exists(final_md_path):
            print(f"[{index}/{total_files}] Skipping {amr_file} - already processed.")
            skipped_count += 1
            continue
            
        print(f"[{index}/{total_files}] Transcribing {amr_file}...")
        
        try:
            # 2. Extract Metadata
            metadata = get_metadata(amr_file)
            
            # 3. Transcribe
            amr_path = os.path.join(SOURCE_DIR, amr_file)
            segments, info = model.transcribe(amr_path, beam_size=5)
            
            transcript_text = ""
            for segment in segments:
                transcript_text += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}\n"
                
            # 4. Format Markdown
            markdown_content = format_obsidian_markdown(metadata, transcript_text)
            
            # 5. ATOMIC WRITE: Write to a .tmp file first
            with open(tmp_md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
                
            # Rename .tmp to final .md file (atomic on most filesystems)
            # This ensures if we crash during the write, we don't leave a half-written file
            os.replace(tmp_md_path, final_md_path)
            
            processed_count += 1
            print(f"  -> Saved to {final_md_path}")
            
        except Exception as e:
            error_msg = traceback.format_exc()
            print(f"  -> FAILED: {str(e)}")
            log_error(amr_file, error_msg)
            error_count += 1
            
            # Cleanup tmp file if it was created during a crash
            if os.path.exists(tmp_md_path):
                try:
                    os.remove(tmp_md_path)
                except:
                    pass
                    
    print("\n=== BATCH PROCESSING COMPLETE ===")
    print(f"Total processed newly: {processed_count}")
    print(f"Skipped (already done): {skipped_count}")
    print(f"Errors (see {ERROR_LOG}): {error_count}")

if __name__ == "__main__":
    process_all_files()
