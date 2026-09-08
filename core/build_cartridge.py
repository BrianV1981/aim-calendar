import os
import sys
import glob
import yaml
import re
import json
import argparse
import traceback

aim_memory_path = os.environ.get("AIM_MEMORY_PATH", "../aim-memory")
sys.path.append(os.path.abspath(aim_memory_path))
try:
    from aim_memory import MemoryClient
    from aim_memory.embeddings import get_embedding
    import lancedb
except ImportError:
    print("Error: Could not import aim_memory. Ensure the path is correct.")
    sys.exit(1)

def parse_transcript(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    yaml_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    metadata = {}
    if yaml_match:
        try:
            metadata = yaml.safe_load(yaml_match.group(1))
        except Exception:
            pass
            
    transcript_section = content.split('# Transcript')[-1].strip()
    lines = transcript_section.split('\n')
    
    turns = []
    current_speaker = None
    current_text = []
    current_start = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        match = re.match(r'\[(.*?)\] \[(.*?)\] (.*)', line)
        if match:
            speaker = match.group(1)
            time_range = match.group(2)
            text = match.group(3)
            
            if speaker == current_speaker:
                current_text.append(text)
            else:
                if current_speaker is not None:
                    turns.append({
                        'speaker': current_speaker,
                        'text': ' '.join(current_text),
                        'timestamp': current_start
                    })
                current_speaker = speaker
                current_text = [text]
                current_start = time_range.split(' -> ')[0]
                
    if current_speaker is not None:
        turns.append({
            'speaker': current_speaker,
            'text': ' '.join(current_text),
            'timestamp': current_start
        })
        
    return metadata, turns

def main():
    parser = argparse.ArgumentParser(description="Build LanceDB Cartridge from transcripts.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files for testing (0 = no limit).")
    args = parser.parse_args()

    print("Initializing isolated Parquet Cartridge...")
    
    # Use MemoryClient to load the backend and table schema correctly
    mem = MemoryClient(db_path="./talker_cartridge.lance")
    table = mem.table
    
    completed_files = set()
    try:
        df = table.search().select(["session_id"]).to_pandas()
        if not df.empty and "session_id" in df.columns:
            completed_files = set(df["session_id"].unique())
            print(f"Found {len(completed_files)} already processed files in LanceDB.")
    except Exception as e:
        print("Idempotency check failed (database might be new). Proceeding...", e)

    transcript_files = glob.glob("conversations_diarized/*.md")
    if args.limit > 0:
        transcript_files = transcript_files[:args.limit]
        print(f"TEST MODE: Limiting to {args.limit} files.")
        
    total_files = len(transcript_files)
    print(f"Found {total_files} transcripts to process.")
    
    success_count = 0
    error_count = 0
    
    # Get current max fragment_id
    try:
        df = table.to_pandas()
        current_id = int(df['fragment_id'].max()) + 1
    except:
        current_id = 1

    batch_records = []
    
    for i, file_path in enumerate(transcript_files, 1):
        try:
            filename = os.path.basename(file_path)
            
            if filename in completed_files:
                continue
                
            metadata, turns = parse_transcript(file_path)
            
            contact = metadata.get('contact', 'Unknown')
            date_str = metadata.get('date', 'Unknown')
            
            if len(turns) == 0:
                continue
                
            for j in range(len(turns)):
                chunk_text = ""
                if j > 0:
                    chunk_text += f"{turns[j-1]['speaker']}: {turns[j-1]['text']}\n"
                chunk_text += f"{turns[j]['speaker']}: {turns[j]['text']}\n"
                if j < len(turns) - 1:
                    chunk_text += f"{turns[j+1]['speaker']}: {turns[j+1]['text']}\n"
                    
                chunk_text = chunk_text.strip()
                payload_metadata = {
                    "source_file": filename,
                    "contact": str(contact),
                    "date": str(date_str),
                    "turn_index": str(j),
                    "timestamp": str(turns[j]['timestamp'])
                }
                
                # Fetch embedding natively
                vec = get_embedding(chunk_text, task_type="RETRIEVAL_DOCUMENT")
                if vec:
                    batch_records.append({
                        "fragment_id": current_id,
                        "session_id": filename,
                        "type": "modular_ingest",
                        "content": chunk_text,
                        "timestamp": "",
                        "metadata": json.dumps(payload_metadata),
                        "parent_id": 0,
                        "source_db": "aim_memory",
                        "vector": vec
                    })
                    current_id += 1
                
            success_count += 1
            
            # Flush batch every 50 files
            if len(batch_records) >= 500:
                table.add(batch_records)
                batch_records = []
                print(f"Flushed batch to disk... Processed {i}/{total_files} total files.")
                
        except Exception as e:
            error_count += 1
            print(f"Error processing {file_path}: {e}")
            traceback.print_exc()
            
    # Flush remaining
    if batch_records:
        table.add(batch_records)
        
    print(f"=== BATCH COMPLETE ===")
    print(f"Successfully chunked: {success_count} new files")
    print(f"Errors: {error_count} files")
    
    print("Rebuilding final FTS index (this may take a minute)...")
    table.create_fts_index("content", replace=True)
    print("Done!")

if __name__ == "__main__":
    main()
