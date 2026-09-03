import os
from pyannote.audio import Pipeline
HF_TOKEN = "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"
pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=HF_TOKEN)
audio_path = $(find benchmark -name "audio.amr" | head -n 1)
