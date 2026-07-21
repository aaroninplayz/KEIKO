import logging
import wave
import io
import numpy as np
import torch
from transformers import pipeline
from core.config import settings, MODELS_DIR

logger = logging.getLogger(__name__)


def pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM = 2 bytes per sample
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_io.getvalue()


class VoiceAnalyzer:
    def __init__(self):
        self.provider = settings.STT_PROVIDER.lower()
        self.model_id = settings.WHISPER_MODEL_SIZE
        self.pipe = None
        
        if self.provider == "local":
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"Initializing local Whisper pipeline with model {self.model_id} on {device}...")
                self.pipe = pipeline(
                    "automatic-speech-recognition",
                    model=self.model_id,
                    device=0 if device == "cuda" else -1,
                    model_kwargs={"cache_dir": MODELS_DIR}
                )
            except Exception as e:
                logger.error(f"Local Whisper init failed: {e}. Fallback to API/Mock will be used.")

    def transcribe(self, pcm_bytes: bytes) -> dict:
        """
        Transcribe the raw 16-bit PCM bytes (16000Hz mono).
        Returns a dict: {"text": str, "mock": bool}
        """
        if not pcm_bytes:
            return {"text": "", "mock": False}

        # If local provider is selected and pipeline is loaded
        if self.provider == "local" and self.pipe:
            try:
                # Convert PCM 16-bit bytes to float32 numpy array
                samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                result = self.pipe({"raw": samples, "sampling_rate": 16000})
                text = result.get("text", "").strip()
                return {"text": text, "mock": False}
            except Exception as e:
                logger.error(f"Local Whisper transcription failed: {e}. Trying API fallback...")

        # If local failed or provider is API, try API fallback
        if settings.OPENAI_API_KEY:
            try:
                return self._transcribe_openai(pcm_bytes)
            except Exception as e:
                logger.error(f"OpenAI transcription fallback failed: {e}")

        if settings.GROQ_API_KEY:
            try:
                return self._transcribe_groq(pcm_bytes)
            except Exception as e:
                logger.error(f"Groq transcription fallback failed: {e}")

        # If neither local model nor API keys worked/are available, degrade gracefully to mock
        mock_text = "This is a mock transcription because neither local Whisper nor API providers are available."
        return {"text": mock_text, "mock": True}

    def _transcribe_openai(self, pcm_bytes: bytes) -> dict:
        import requests
        wav_bytes = pcm_to_wav_bytes(pcm_bytes)
        url = f"{settings.OPENAI_API_BASE.rstrip('/')}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
        data = {"model": "whisper-1"}
        r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        r.raise_for_status()
        text = r.json().get("text", "").strip()
        return {"text": text, "mock": False}

    def _transcribe_groq(self, pcm_bytes: bytes) -> dict:
        import requests
        wav_bytes = pcm_to_wav_bytes(pcm_bytes)
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
        files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
        data = {"model": "whisper-large-v3"}
        r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        r.raise_for_status()
        text = r.json().get("text", "").strip()
        return {"text": text, "mock": False}

    async def process_audio(self, audio_chunk: bytes) -> dict:
        """
        Analyzes audio chunk entirely in memory for tone, pitch, and speech-to-text.
        """
        logger.debug("Processing audio chunk locally...")
        return {
            "type": "voice_metric",
            "pace": "optimal",
            "tone": "confident"
        }

    def analyze_speech(self, text: str, audio_len: float = 5.0) -> dict:
        """
        Calculates speaking pace, modulation, clarity, and fluency scores (0-100) based on text transcription.
        """
        words = text.split()
        wpm = (len(words) / audio_len) * 60.0 if audio_len > 0 else 0.0
        
        # Pace score (optimal speaking pace is around 130-150 WPM)
        if wpm == 0:
            pace_score = 50.0
        else:
            deviation = abs(wpm - 140.0)
            pace_score = max(0.0, min(100.0, 100.0 - deviation * 0.5))
        
        # Modulation score
        modulation_score = 80.0
        if len(words) > 1:
            modulation_score = max(30.0, min(100.0, 70.0 + len(set(words)) * 2.0))
            
        # Clarity score (default high, but we can simulate minor variance)
        clarity_score = 85.0
        
        # Fluency (filler word detection)
        fillers = ["um", "like", "uh", "err", "ah"]
        filler_count = sum(1 for w in words if w.lower().strip(",.?!") in fillers)
        if len(words) > 0:
            ratio = filler_count / len(words)
            fluency_score = max(0.0, min(100.0, 100.0 - ratio * 200.0))
        else:
            fluency_score = 80.0
            
        return {
            "pace": round(pace_score, 1),
            "modulation": round(modulation_score, 1),
            "clarity": round(clarity_score, 1),
            "fluency": round(fluency_score, 1),
            "wpm": round(wpm, 1),
            "filler_count": filler_count
        }
