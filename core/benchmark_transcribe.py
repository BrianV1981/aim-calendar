import os
import shutil
import random
import re
from faster_whisper import WhisperModel

# Paths
MD_DIR = "conversations"
AUDIO_DIR = "TalkerACR/All"
BENCHMARK_DIR = "benchmark"
MODEL_SIZE = "distil-large-v3"

def setup_benchmark_folders(sample_size=100):
    """Isolates 100 golden calls and sets up the strict folder structure."""
    if not os.path.exists(BENCHMARK_DIR):
        os.makedirs(BENCHMARK_DIR)
        
    # If we already set it up, don't re-pick random files
    existing_folders = [f for f in os.listdir(BENCHMARK_DIR) if os.path.isdir(os.path.join(BENCHMARK_DIR, f))]
    if len(existing_folders) >= sample_size:
        print(f"Benchmark directory already contains {len(existing_folders)} folders. Skipping setup.")
        return existing_folders
        
    print(f"Scanning for {sample_size} random golden transcripts...")
    golden_files = []
    
    # Scan for golden files
    for filename in os.listdir(MD_DIR):
        if not filename.endswith('.md'):
            continue
            
        filepath = os.path.join(MD_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(500) # only read the top for the status
                if "status: golden" in content:
                    golden_files.append(filename)
        except Exception as e:
            continue
            
    if len(golden_files) < sample_size:
        print(f"Warning: Only found {len(golden_files)} golden files, less than the requested {sample_size}.")
        sample_size = len(golden_files)
        
    # Pick random files
    selected = random.sample(golden_files, sample_size)
    print(f"Selected {len(selected)} files. Building folder structures...")
    
    folder_names = []
    
    for md_filename in selected:
        base_name = md_filename.replace('.md', '')
        audio_filename = base_name + '.amr'
        
        audio_src = os.path.join(AUDIO_DIR, audio_filename)
        md_src = os.path.join(MD_DIR, md_filename)
        
        if not os.path.exists(audio_src):
            print(f"Warning: Audio file not found for {base_name}. Skipping.")
            continue
            
        # Create the dedicated isolated folder
        target_dir = os.path.join(BENCHMARK_DIR, base_name)
        os.makedirs(target_dir, exist_ok=True)
        
        # Copy the files over and rename them explicitly for side-by-side comparison
        shutil.copy2(audio_src, os.path.join(target_dir, "audio.amr"))
        shutil.copy2(md_src, os.path.join(target_dir, "transcript_base.md"))
        
        folder_names.append(base_name)
        
    print("Folder setup complete!")
    return folder_names

def run_large_transcription():
    """Runs the heavy model on the isolated benchmark audio files."""
    folders = [f for f in os.listdir(BENCHMARK_DIR) if os.path.isdir(os.path.join(BENCHMARK_DIR, f))]
    
    if not folders:
        print("No benchmark folders found. Run setup first.")
        return
        
    print(f"Loading {MODEL_SIZE} model into memory (this takes a moment)...")
    # Using float16 for speed and memory efficiency on large models
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    print("Model loaded successfully.")
    
    total = len(folders)
    for idx, folder_name in enumerate(folders, 1):
        target_dir = os.path.join(BENCHMARK_DIR, folder_name)
        audio_path = os.path.join(target_dir, "audio.amr")
        large_md_path = os.path.join(target_dir, "transcript_large.md")
        
        if os.path.exists(large_md_path):
            print(f"[{idx}/{total}] Skipping {folder_name} (large transcript already exists)")
            continue
            
        print(f"[{idx}/{total}] Transcribing {folder_name} with {MODEL_SIZE}...")
        
        try:
            segments, info = model.transcribe(
                audio_path,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            transcript = ""
            for segment in segments:
                transcript += f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text.strip()}\n"
                
            # Write the exact same format out, but for the large model
            with open(large_md_path, 'w', encoding='utf-8') as f:
                f.write(f"---\nmodel: {MODEL_SIZE}\n---\n\n# Transcript\n")
                f.write(transcript)
                
            print(f"[{idx}/{total}] Finished {folder_name}")
            
        except Exception as e:
            print(f"[{idx}/{total}] Error processing {folder_name}: {e}")

if __name__ == "__main__":
    setup_benchmark_folders(100)
    run_large_transcription()
