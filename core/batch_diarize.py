import os
import json
import traceback
import subprocess
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

# Configuration
SOURCE_DIR = "TalkerACR/All"
PROPS_DIR = os.path.join(SOURCE_DIR, ".props")
OUTPUT_DIR = "conversations_diarized"
ORIGINAL_MD_DIR = "conversations"
ERROR_LOG = "diarize_errors.log"
MODEL_SIZE = "large-v3"
HF_TOKEN = "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"

def setup_directories():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def get_speaker_for_segment(segment, diarization):
    segment_start = segment.start
    segment_end = segment.end
    speaker_overlaps = {}
    
    try:
        annotation = diarization.speaker_diarization
    except AttributeError:
        annotation = diarization
        
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        overlap_start = max(segment_start, turn.start)
        overlap_end = min(segment_end, turn.end)
        overlap_duration = overlap_end - overlap_start
        if overlap_duration > 0:
            if speaker not in speaker_overlaps:
                speaker_overlaps[speaker] = 0
            speaker_overlaps[speaker] += overlap_duration
            
    if not speaker_overlaps:
        return "Unknown"
    return max(speaker_overlaps, key=speaker_overlaps.get)

def log_error(filename, error_msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{filename}] ERROR: {error_msg}\n")

def process_all_files():
    setup_directories()
    
    print(f"Loading {MODEL_SIZE} Whisper model...")
    whisper_model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    
    print("Loading Pyannote Speaker Diarization model...")
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN
        )
    except Exception as e:
        print(f"Failed to load Pyannote: {e}")
        return
        
    amr_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".amr")]
    total_files = len(amr_files)
    print(f"Found {total_files} AMR files to process.")
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    for index, amr_file in enumerate(amr_files, 1):
        base_name = os.path.splitext(amr_file)[0]
        final_md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md")
        original_md_path = os.path.join(ORIGINAL_MD_DIR, f"{base_name}.md")
        tmp_md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md.tmp")
        wav_path = os.path.join(SOURCE_DIR, f"{base_name}_temp.wav")
        
        # Check if already diarized
        already_diarized = os.path.exists(final_md_path)
                
        if already_diarized:
            print(f"[{index}/{total_files}] Skipping {amr_file} - already diarized.")
            skipped_count += 1
            continue
            
        # Get existing metadata from original folder
        existing_content = ""
        is_golden = False
        if os.path.exists(original_md_path):
            with open(original_md_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
            if "status: golden" in existing_content:
                is_golden = True
                
        if not is_golden:
            print(f"[{index}/{total_files}] Skipping {amr_file} - not classified as golden.")
            skipped_count += 1
            continue
                
        print(f"[{index}/{total_files}] Diarizing and Transcribing {amr_file}...")
        
        try:
            # 1. Convert to wav to bypass pyannote amr chunk bug
            amr_path = os.path.join(SOURCE_DIR, amr_file)
            subprocess.run(['ffmpeg', '-y', '-i', amr_path, '-ar', '16000', '-ac', '1', wav_path, '-loglevel', 'quiet'], check=True)
            
            # 2. Pyannote
            diarization = pipeline(wav_path)
            
            # 3. Whisper Transcription
            segments, info = whisper_model.transcribe(
                amr_path,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            transcript_text = ""
            for segment in segments:
                speaker = get_speaker_for_segment(segment, diarization)
                transcript_text += f"[{speaker}] [{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text.strip()}\n"
                
            # 4. Inject into Markdown
            if existing_content:
                # Replace transcript portion
                parts = existing_content.split("# Transcript")
                if len(parts) == 2:
                    frontmatter = parts[0]
                    # Inject model tag if not present
                    if "model:" not in frontmatter:
                        frontmatter = frontmatter.replace("---\n\n", "model: large-v3 + pyannote\n---\n\n")
                    else:
                        import re
                        frontmatter = re.sub(r'model:.*', 'model: large-v3 + pyannote', frontmatter)
                        
                    markdown_content = frontmatter + "# Transcript\n\n" + transcript_text
                else:
                    # Fallback if structure is weird
                    markdown_content = existing_content + "\n\n# Transcript\n\n" + transcript_text
            else:
                # If .md doesn't exist for some reason, create a basic one
                markdown_content = f"---\nmodel: large-v3 + pyannote\n---\n\n# Transcript\n\n{transcript_text}"
                
            # 5. ATOMIC WRITE
            with open(tmp_md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
                
            os.replace(tmp_md_path, final_md_path)
            processed_count += 1
            print(f"  -> Saved to {final_md_path}")
            
        except Exception as e:
            error_msg = traceback.format_exc()
            print(f"  -> FAILED: {str(e)}")
            log_error(amr_file, error_msg)
            error_count += 1
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except:
                    pass
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
