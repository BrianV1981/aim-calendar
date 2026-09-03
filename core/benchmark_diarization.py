import os
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

# Paths
BENCHMARK_DIR = "benchmark"
MODEL_SIZE = "large-v3"
HF_TOKEN = "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"

def get_speaker_for_segment(segment, diarization):
    """Finds the speaker who spoke the most during this whisper segment."""
    segment_start = segment.start
    segment_end = segment.end
    
    # Store overlaps: {speaker_label: overlap_duration}
    speaker_overlaps = {}
    
    try:
        annotation = diarization.speaker_diarization
    except AttributeError:
        annotation = diarization
        
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        # Calculate overlap
        overlap_start = max(segment_start, turn.start)
        overlap_end = min(segment_end, turn.end)
        overlap_duration = overlap_end - overlap_start
        
        if overlap_duration > 0:
            if speaker not in speaker_overlaps:
                speaker_overlaps[speaker] = 0
            speaker_overlaps[speaker] += overlap_duration
            
    if not speaker_overlaps:
        return "Unknown"
        
    # Return the speaker with the maximum overlap
    return max(speaker_overlaps, key=speaker_overlaps.get)

def run_diarization():
    folders = [f for f in os.listdir(BENCHMARK_DIR) if os.path.isdir(os.path.join(BENCHMARK_DIR, f))]
    
    if not folders:
        print("No benchmark folders found.")
        return
        
    print(f"Loading {MODEL_SIZE} Whisper model...")
    whisper_model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    
    print("Loading Pyannote Speaker Diarization model...")
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN
        )
    except Exception as e:
        print(f"Failed to load Pyannote. Check your HF_TOKEN or access rights: {e}")
        return
        
    total = len(folders)
    for idx, folder_name in enumerate(folders, 1):
        target_dir = os.path.join(BENCHMARK_DIR, folder_name)
        audio_path = os.path.join(target_dir, "audio.amr")
        diarized_md_path = os.path.join(target_dir, "transcript_diarized.md")
        
        if os.path.exists(diarized_md_path):
            print(f"[{idx}/{total}] Skipping {folder_name} (diarized transcript already exists)")
            continue
            
        print(f"[{idx}/{total}] Diarizing and Transcribing {folder_name}...")
        
        # Pyannote/Torchaudio has a bug with AMR chunk truncation. Convert to wav first.
        wav_path = os.path.join(target_dir, "temp_audio.wav")
        
        try:
            # Convert to 16kHz wav for stable torchaudio decoding
            os.system(f'ffmpeg -y -i "{audio_path}" -ar 16000 -ac 1 "{wav_path}" -loglevel quiet')
            
            # 1. Run Pyannote Diarization on the stable wav file
            diarization = pipeline(wav_path)
            
            # 2. Run Whisper Transcription
            segments, info = whisper_model.transcribe(
                audio_path,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # 3. Combine them
            transcript = ""
            for segment in segments:
                speaker = get_speaker_for_segment(segment, diarization)
                transcript += f"[{speaker}] [{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text.strip()}\n"
                
            with open(diarized_md_path, 'w', encoding='utf-8') as f:
                f.write(f"---\nmodel: {MODEL_SIZE} + pyannote\n---\n\n# Transcript\n")
                f.write(transcript)
                
            print(f"[{idx}/{total}] Finished {folder_name}")
            
        except Exception as e:
            print(f"[{idx}/{total}] Error processing {folder_name}: {e}")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

if __name__ == "__main__":
    run_diarization()
