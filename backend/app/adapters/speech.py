import base64
from typing import Optional, Protocol, runtime_checkable
from pydantic import BaseModel

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
        # If text is directly passed or encoded
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
        # Calculate realistic speech duration: ~150 words per minute -> 2.5 words/sec
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
