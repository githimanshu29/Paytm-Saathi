import base64
import logging
from typing import Optional, Protocol, runtime_checkable
import httpx
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger("paytm_saathi.speech")


class SpeechTranscriptionResult(BaseModel):
    text: str
    confidence: float = 0.98
    language_detected: str = "hi-IN"
    provider: str = "MOCK"


class SpeechSynthesisResult(BaseModel):
    audio_base64: str
    duration_seconds: float
    mime_type: str = "audio/wav"
    language: str = "hi-IN"
    provider: str = "MOCK"


@runtime_checkable
class ISpeechAdapter(Protocol):
    """
    Swappable Speech-to-Text and Text-to-Speech interface.
    Allows easy plug-in of Indian Indic voice providers (Sarvam AI, Bhashini, Google Speech).
    """

    def transcribe(self, audio_data: bytes, language_hint: str = "hi-IN") -> SpeechTranscriptionResult:
        ...

    def synthesize(self, text: str, language: str = "hi-IN", voice: str = "female") -> SpeechSynthesisResult:
        ...


class MockSpeechAdapter:
    """
    High-fidelity mock speech provider for local development, tests, and prototype demos.
    Generates realistic speech audio payloads and transcribes conversational speech.
    """

    def __init__(self, provider_name: str = "MOCK"):
        self.provider_name = provider_name

    def transcribe(self, audio_data: bytes, language_hint: str = "hi-IN") -> SpeechTranscriptionResult:
        try:
            decoded = audio_data.decode("utf-8")
            return SpeechTranscriptionResult(
                text=decoded,
                confidence=0.97,
                language_detected=language_hint,
                provider=self.provider_name,
            )
        except Exception:
            return SpeechTranscriptionResult(
                text="Soundbox light is red and not speaking",
                confidence=0.92,
                language_detected=language_hint,
                provider=self.provider_name,
            )

    def synthesize(self, text: str, language: str = "hi-IN", voice: str = "female") -> SpeechSynthesisResult:
        words = len(text.split())
        est_duration = max(1.2, round(words / 2.5, 1))

        # Minimal valid 44-byte WAV header stub encoded in base64
        wav_stub = (
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
            b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        audio_b64 = base64.b64encode(wav_stub).decode("ascii")

        return SpeechSynthesisResult(
            audio_base64=audio_b64,
            duration_seconds=est_duration,
            mime_type="audio/wav",
            language=language,
            provider=self.provider_name,
        )


class SarvamSpeechAdapter:
    """
    Sarvam AI Indic Speech Adapter.
    - Bulbul v1: Realistic Indic Text-to-Speech (Hindi, English, etc.)
    - Saaras v1: Indic Speech-to-Text Transcription
    With automatic fallback to MockSpeechAdapter if key is missing or call fails.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = (api_key or settings.SARVAM_API_KEY or "").strip()
        self.base_url = (base_url or settings.SARVAM_BASE_URL or "https://api.sarvam.ai").rstrip("/")
        self.mock_adapter = MockSpeechAdapter(provider_name="MOCK_FALLBACK")

    def _normalize_lang(self, lang: str) -> str:
        lang_map = {
            "hi": "hi-IN",
            "en": "en-IN",
            "bn": "bn-IN",
            "kn": "kn-IN",
            "ml": "ml-IN",
            "mr": "mr-IN",
            "od": "od-IN",
            "pa": "pa-IN",
            "ta": "ta-IN",
            "te": "te-IN",
            "gu": "gu-IN",
        }
        return lang_map.get(lang.lower(), lang if "-" in lang else "hi-IN")

    def synthesize(self, text: str, language: str = "hi-IN", voice: str = "meera") -> SpeechSynthesisResult:
        if not self.api_key:
            logger.debug("Sarvam API key not set. Using mock speech synthesis.")
            return self.mock_adapter.synthesize(text, language=language, voice=voice)

        norm_lang = self._normalize_lang(language)
        # Sarvam Bulbul expects inputs as a list of strings (max 500 characters recommended per item)
        clean_text = text.strip()[:480]

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        speaker = "meera" if voice in ("female", "meera") else ("arvind" if voice in ("male", "arvind") else "meera")
        payload = {
            "inputs": [clean_text],
            "target_language_code": norm_lang,
            "speaker": speaker,
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v1",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(f"{self.base_url}/text-to-speech", headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    audios = data.get("audios", [])
                    if audios and len(audios) > 0 and audios[0]:
                        audio_b64 = audios[0]
                        # Estimate audio duration from base64 length or word count
                        try:
                            raw_bytes = base64.b64decode(audio_b64)
                            # 8000 Hz, 16-bit mono = 16000 bytes/sec
                            est_dur = round(max(1.0, len(raw_bytes) / 16000.0), 1)
                        except Exception:
                            est_dur = max(1.2, round(len(text.split()) / 2.5, 1))

                        return SpeechSynthesisResult(
                            audio_base64=audio_b64,
                            duration_seconds=est_dur,
                            mime_type="audio/wav",
                            language=norm_lang,
                            provider="SARVAM_AI",
                        )
                logger.warning(
                    f"Sarvam AI TTS returned HTTP {res.status_code}: {res.text}. Falling back to mock synthesis."
                )
        except Exception as e:
            logger.warning(f"Failed to call Sarvam AI TTS ({e}). Falling back to mock speech.")

        return self.mock_adapter.synthesize(text, language=language, voice=voice)

    def transcribe(self, audio_data: bytes, language_hint: str = "hi-IN") -> SpeechTranscriptionResult:
        if not self.api_key:
            logger.debug("Sarvam API key not set. Using mock speech transcription.")
            return self.mock_adapter.transcribe(audio_data, language_hint=language_hint)

        norm_lang = self._normalize_lang(language_hint)
        headers = {
            "api-subscription-key": self.api_key,
        }

        try:
            files = {
                "file": ("audio.wav", audio_data, "audio/wav"),
            }
            data = {
                "model": "saaras:v1",
                "language_code": norm_lang,
            }
            with httpx.Client(timeout=15.0) as client:
                res = client.post(
                    f"{self.base_url}/speech-to-text",
                    headers=headers,
                    files=files,
                    data=data,
                )
                if res.status_code == 200:
                    result = res.json()
                    transcript = result.get("transcript", "").strip()
                    if transcript:
                        return SpeechTranscriptionResult(
                            text=transcript,
                            confidence=0.98,
                            language_detected=result.get("language_code", norm_lang),
                            provider="SARVAM_AI",
                        )
                logger.warning(
                    f"Sarvam AI STT returned HTTP {res.status_code}: {res.text}. Falling back to mock transcription."
                )
        except Exception as e:
            logger.warning(f"Failed to call Sarvam AI STT ({e}). Falling back to mock speech.")

        return self.mock_adapter.transcribe(audio_data, language_hint=language_hint)


def get_speech_adapter() -> ISpeechAdapter:
    """
    Factory function returning SarvamSpeechAdapter if SARVAM_API_KEY is configured,
    or MockSpeechAdapter otherwise.
    """
    if settings.SARVAM_API_KEY and settings.SARVAM_API_KEY.strip():
        return SarvamSpeechAdapter()
    return MockSpeechAdapter()
