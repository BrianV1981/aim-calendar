import os
import re
import requests
import lancedb
import pyarrow as pa
from typing import List, Dict

# Config
DB_PATH = "memory_lance_calls" # Keeping it isolated from A.I.M.'s OS memory
TABLE_NAME = "transcripts"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text:latest"
INPUT_DIR = "conversations"

# Chunking Config (RAG 5.21 Length-Constrained Accumulator)
MIN_CHUNK_SIZE = 500
MAX_CHUNK_SIZE = 1500

def get_embedding(text: str) -> List[float]:
    """Get vector embedding from local Ollama model."""
    try:
        response = requests.post(OLLAMA_EMBED_URL, json={
            "model": EMBED_MODEL,
            "prompt": text
        }, timeout=30)
        response.raise_for_status()
        return response.json().get("embedding")
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return []

def parse_markdown(filepath: str):
    """Parses the YAML frontmatter and transcript text."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # We only want golden calls
    if "status: garbage" in content:
        return None, None
        
    # Very basic YAML parser for our specific format
    metadata = {
        "filename": os.path.basename(filepath),
        "platform": "unknown",
        "date": "unknown",
        "contact": "unknown"
    }
    
    if "---\n" in content:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            transcript = parts[2].strip()
            # Clean up the transcript header
            if transcript.startswith("# Transcript"):
                transcript = transcript.replace("# Transcript", "", 1).strip()
                
            for line in frontmatter.split("\n"):
                if line.startswith("platform:"): metadata["platform"] = line.split(":", 1)[1].strip()
                if line.startswith("date:"): metadata["date"] = line.split(":", 1)[1].strip()
                if line.startswith("contact:"): metadata["contact"] = line.split(":", 1)[1].strip().replace('"', '')
                
            return metadata, transcript
            
    return None, None

def chunk_text(text: str, min_size: int = MIN_CHUNK_SIZE, max_size: int = MAX_CHUNK_SIZE) -> List[str]:
    """RAG 5.21 Speaker-Boundary Length-Constrained Accumulator."""
    chunks = []
    current_chunk = ""
    
    # Split by transcript blocks (e.g. lines starting with timestamp brackets '[')
    # This acts as a proxy for speaker boundaries/natural pauses.
    blocks = re.split(r'(?=\n\[)', text)
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        if len(current_chunk) + len(block) > max_size:
            if len(current_chunk) >= min_size:
                # Flush the optimal density chunk to database
                chunks.append(current_chunk.strip())
                current_chunk = block
            else:
                # Block is massive, force a hard split to prevent exceeding max
                if len(block) > max_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    start = 0
                    while start < len(block):
                        chunks.append(block[start:start+max_size].strip())
                        start += max_size
                    current_chunk = ""
                else:
                    current_chunk += "\n" + block
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
        else:
            if current_chunk:
                current_chunk += "\n" + block
            else:
                current_chunk = block
                
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def build_database():
    # Setup LanceDB Schema
    # Nomic-embed-text generates 768-dimensional vectors
    schema = pa.schema([
        pa.field("vector", pa.list_(pa.float32(), 768)),
        pa.field("filename", pa.string()),
        pa.field("platform", pa.string()),
        pa.field("date", pa.string()),
        pa.field("contact", pa.string()),
        pa.field("text", pa.string())
    ])
    
    db = lancedb.connect(DB_PATH)
    if TABLE_NAME in db.table_names():
        # Open existing table
        table = db.open_table(TABLE_NAME)
        # Check what files are already indexed
        try:
            existing_files = set([r['filename'] for r in table.search().select(["filename"]).limit(100000).to_list()])
        except:
            existing_files = set()
    else:
        table = db.create_table(TABLE_NAME, schema=schema)
        existing_files = set()
        
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.md')]
    total = len(files)
    print(f"Scanning {total} files for indexing...")
    
    for idx, filename in enumerate(files, 1):
        if filename in existing_files:
            continue
            
        filepath = os.path.join(INPUT_DIR, filename)
        metadata, transcript = parse_markdown(filepath)
        
        if not metadata or not transcript:
            continue # Skip garbage or malformed files
            
        print(f"[{idx}/{total}] Embedding {filename}...")
        chunks = chunk_text(transcript)
        
        data_to_insert = []
        for chunk in chunks:
            if len(chunk) < 10:
                continue
            vec = get_embedding(chunk)
            if vec and len(vec) == 768:
                data_to_insert.append({
                    "vector": vec,
                    "filename": metadata["filename"],
                    "platform": metadata["platform"],
                    "date": metadata["date"],
                    "contact": metadata["contact"],
                    "text": chunk
                })
                
        if data_to_insert:
            table.add(data_to_insert)
            
    print("\n=== INDEXING COMPLETE ===")
    # Run A.I.M. Compaction Protocol
    print("Running LanceDB optimization (compaction)...")
    table.compact_files()
    print("Database optimized and ready for query.")

if __name__ == "__main__":
    build_database()
