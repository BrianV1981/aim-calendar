import os
import shutil
import random
import re
from faster_whisper import WhisperModel

# Paths
MD_DIR = "conversations"
AUDIO_DIR = "TalkerACR/All"
BENCHMARK_DIR = "benchmark"
MODEL_SIZE = "large-v3"

def run_large_transcription():
    """Runs the heavy model on the isolated benchmark audio files."""
    folders = [f for f in os.listdir(BENCHMARK_DIR) if os.path.isdir(os.path.join(BENCHMARK_DIR, f))]
    
    if not folders:
        print("No benchmark folders found. Run setup first.")
        return
        
    print(f"Loading {MODEL_SIZE} model into memory (this takes a moment)...")
    # Using int8 for speed and memory efficiency on large models
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    print("Model loaded successfully.")
    
    total = len(folders)
    for idx, folder_name in enumerate(folders, 1):
        target_dir = os.path.join(BENCHMARK_DIR, folder_name)
        audio_path = os.path.join(target_dir, "audio.amr")
        full_large_md_path = os.path.join(target_dir, "transcript_full_large.md")
        
        if os.path.exists(full_large_md_path):
            print(f"[{idx}/{total}] Skipping {folder_name} (full large transcript already exists)")
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
                
            # Write the exact same format out, but for the full large model
            with open(full_large_md_path, 'w', encoding='utf-8') as f:
                f.write(f"---\nmodel: {MODEL_SIZE}\n---\n\n# Transcript\n")
                f.write(transcript)
                
            print(f"[{idx}/{total}] Finished {folder_name}")
            
        except Exception as e:
            print(f"[{idx}/{total}] Error processing {folder_name}: {e}")

if __name__ == "__main__":
    run_large_transcription()
