"""Voice System — Nexus speaks and listens.

Architecture (mirrors OpenClaw's voice-call plugin):
  Microphone → STT → LLM → TTS → Speaker

Providers:
  TTS: FreeTTS (no key), OpenAI, ElevenLabs, System (espeak/pico)
  STT: AssemblyAI (free tier), Deepgram, Whisper (local), FreeTTS STT

The voice engine orchestrates the pipeline and exposes:
  - /voice slash command in REPL
  - voice_mode() async context manager for full-duplex conversation
"""

import asyncio
import io
import os
import tempfile
import wave as wavelib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from .errors import NexusError
from .utils import format_error


@dataclass
class VoiceConfig:
    tts_provider: str = "freetts"
    stt_provider: str = "freetts"
    voice: str = "en-US-JennyNeural"
    sample_rate: int = 16000
    channels: int = 1
    stt_api_key: str | None = None
    tts_api_key: str | None = None
    wake_word: str = "hey nexus"
    silence_threshold: float = 500
    silence_duration: float = 1.5
    barge_in: bool = True
    stream_tts: bool = True


# ─────────────────────────────────────────────────────────────
# TTS Providers
# ─────────────────────────────────────────────────────────────


class TTSProvider(ABC):
    @abstractmethod
    async def speak(self, text: str, config: VoiceConfig) -> bytes:
        """Convert text to audio. Returns WAV/MP3 bytes."""
        raise NexusError("TTS functionality not implemented.")

    @abstractmethod
    async def stream_speak(self, text: str, config: VoiceConfig) -> AsyncIterator[bytes]:
        """Stream audio chunks as they're generated."""
        raise NexusError("TTS streaming not implemented.")

    @abstractmethod
    async def play_audio(self, audio: bytes, config: VoiceConfig) -> None:
        """Play audio bytes through speakers."""
        raise NexusError("Audio playback not implemented.")


class FreeTTSProvider(TTSProvider):
    """Microsoft Neural voices via FreeTTS API. No API key needed."""

    BASE_URL = "https://freetts.org/api"
    VOICES = [
        "en-US-JennyNeural",
        "en-US-GuyNeural",
        "en-US-AriaNeural",
        "en-GB-SoniaNeural",
        "en-GB-RyanNeural",
        "en-AU-NatashaNeural",
        "en-AU-WilliamNeural",
        "de-DE-KatjaNeural",
        "fr-FR-DeniseNeural",
        "es-ES-ElviraNeural",
        "it-IT-ElsaNeural",
        "pt-BR-FranciscaNeural",
        "ja-JP-NanamiNeural",
        "ko-KR-SunHiNeural",
        "zh-CN-XiaoxiaoNeural",
    ]

    async def speak(self, text: str, config: VoiceConfig) -> bytes:
        import httpx

        max_retries = 3
        async with httpx.AsyncClient() as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(
                        f"{self.BASE_URL}/tts",
                        json={
                            "text": text,
                            "voice": config.voice,
                            "rate": "+0%",
                            "pitch": "+0Hz",
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()
                    file_id = data.get("file_id")
                    if not file_id:
                        raise ValueError(f"FreeTTS returned no file_id: {data}")

                    audio_resp = await client.get(f"{self.BASE_URL}/audio/{file_id}", timeout=30)
                    audio_resp.raise_for_status()
                    return audio_resp.content
                except Exception as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    raise NexusError(f"FreeTTS failed after {max_retries} attempts: {e}")

    async def stream_speak(self, text: str, config: VoiceConfig) -> AsyncIterator[bytes]:
        audio = await self.speak(text, config)
        yield audio

    async def play_audio(self, audio: bytes, config: VoiceConfig) -> None:
        try:
            try:
                import pyaudio
            except ImportError:
                from .utils.dependencies import ensure_dependency

                if not ensure_dependency("pyaudio"):
                    print("[TTS] Audio playback skipped (PyAudio not installed)")
                    return
                import pyaudio

            wav_data = self._convert_to_wav(audio)
            pa = pyaudio.PyAudio()
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=config.channels,
                    rate=config.sample_rate,
                    output=True,
                )
                stream.write(wav_data)
                stream.stop_stream()
                stream.close()
            finally:
                pa.terminate()
        except Exception as e:
            print(f"[TTS] Audio playback skipped (error): {e}")

    def _convert_to_wav(self, audio: bytes) -> bytes:
        audio_io = io.BytesIO(audio)
        try:
            with wavelib.open(audio_io, "rb") as wf:
                return wf.read()
        except Exception:
            return audio


class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS API (gpt-4o-mini-tts or tts-1)."""

    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    async def speak(self, text: str, config: VoiceConfig) -> bytes:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=config.tts_api_key)
        response = await client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=config.voice if config.voice in self.VOICES else "nova",
            input=text,
            response_format="mp3",
        )
        return await response.astream_to_bytes()

    async def stream_speak(self, text: str, config: VoiceConfig) -> AsyncIterator[bytes]:
        audio = await self.speak(text, config)
        yield audio

    async def play_audio(self, audio: bytes, config: VoiceConfig) -> None:
        try:
            import pyaudio

            wav = self._mp3_to_wav(audio)
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
            stream.write(wav)
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception as e:
            print(f"[TTS] Audio playback skipped: {e}")

    def _mp3_to_wav(self, mp3_data: bytes) -> bytes:
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            buf = io.BytesIO()
            audio.export(buf, format="wav")
            return buf.getvalue()
        except Exception:
            return mp3_data


class SystemTTSProvider(TTSProvider):
    """System TTS via espeak-ng or pico2wave (no network needed)."""

    async def speak(self, text: str, config: VoiceConfig) -> bytes:
        import subprocess

        try:
            result = subprocess.run(
                ["espeak", "-w", "/dev/stdout", "-s", "160", text],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
            subprocess.run(
                ["pico2wave", "-w", wav_path, text],
                capture_output=True,
                timeout=10,
            )
            with open(wav_path, "rb") as f:
                data = f.read()
            os.unlink(wav_path)
            return data
        except Exception as e:
            raise RuntimeError(f"No system TTS available: {e}")

    async def stream_speak(self, text: str, config: VoiceConfig) -> AsyncIterator[bytes]:
        audio = await self.speak(text, config)
        yield audio

    async def play_audio(self, audio: bytes, config: VoiceConfig) -> None:
        try:
            import pyaudio

            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=22050, output=True)
            stream.write(audio)
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception as e:
            print(f"[TTS] Audio playback skipped: {e}")


# ─────────────────────────────────────────────────────────────
# STT Providers
# ─────────────────────────────────────────────────────────────


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, config: VoiceConfig) -> str:
        """Convert audio bytes to text."""
        raise NotImplementedError

    async def listen(self, config: VoiceConfig, timeout: float = 10.0) -> tuple[bytes, float]:
        """Record audio from microphone. Returns (audio_bytes, duration)."""
        try:
            import pyaudio
        except ImportError:
            from .utils.dependencies import ensure_dependency

            if not ensure_dependency("pyaudio"):
                raise NexusError("PyAudio is required for voice listening but is not installed.")
            import pyaudio

            p = pyaudio.PyAudio()

        frames = []
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=config.channels,
                rate=config.sample_rate,
                input=True,
                frames_per_buffer=1024,
            )
        except Exception as e:
            p.terminate()
            raise NexusError(f"Failed to open microphone: {e}")

        silence_start = None
        silence_threshold = int(config.silence_threshold)
        is_speaking = False
        start_time = asyncio.get_event_loop().time()

        try:
            while True:
                data = stream.read(1024, exception_on_overflow=False)
                amplitude = max(abs(int.from_bytes(data[i : i + 2], "little", signed=True)) for i in range(0, len(data) - 1, 2))
                frames.append(data)

                now = asyncio.get_event_loop().time()

                if amplitude > silence_threshold:
                    is_speaking = True
                    silence_start = None
                elif is_speaking and silence_start is None:
                    silence_start = now
                elif is_speaking and silence_start and (now - silence_start) > config.silence_duration:
                    break
                elif now > start_time + timeout:
                    break

        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        buf = io.BytesIO()
        with wavelib.open(buf, "wb") as wf:
            wf.setnchannels(config.channels)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(config.sample_rate)
            wf.writeframes(b"".join(frames))
        return buf.getvalue(), len(frames) * 1024 / config.sample_rate

    async def listen_until_speech(self, config: VoiceConfig, timeout: float = 30.0) -> tuple[bytes, float]:
        """Wait for speech, then record until silence."""
        try:
            import pyaudio
        except ImportError:
            from .utils.dependencies import ensure_dependency

            if not ensure_dependency("pyaudio"):
                raise NexusError("PyAudio is required for voice listening but is not installed.")
            import pyaudio

            p = pyaudio.PyAudio()

        frames = []
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=config.channels,
                rate=config.sample_rate,
                input=True,
                frames_per_buffer=512,
            )
        except Exception as e:
            p.terminate()
            raise NexusError(f"Failed to open microphone: {e}")

        speech_started = False
        silence_start = None
        speech_start_time = None
        threshold = int(config.silence_threshold)

        try:
            while True:
                data = stream.read(512, exception_on_overflow=False)
                amplitude = max(abs(int.from_bytes(data[i : i + 2], "little", signed=True)) for i in range(0, len(data) - 1, 2)) if len(data) >= 2 else 0

                now = asyncio.get_event_loop().time()

                if amplitude > threshold:
                    if not speech_started:
                        speech_started = True
                        speech_start_time = now
                    silence_start = None
                    if len(frames) > 5:
                        frames = frames[-5:]
                    frames.append(data)
                elif speech_started:
                    frames.append(data)
                    if silence_start is None:
                        silence_start = now
                    elif now - silence_start > config.silence_duration:
                        break
                    if timeout and now - speech_start_time > timeout:
                        break

        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        if not frames:
            return b"", 0.0

        buf = io.BytesIO()
        with wavelib.open(buf, "wb") as wf:
            wf.setnchannels(config.channels)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(config.sample_rate)
            wf.writeframes(b"".join(frames))
        duration = len(frames) * 512 / config.sample_rate
        return buf.getvalue(), duration


class AssemblyAISTTProvider(STTProvider):
    """AssemblyAI STT — $50 free credits, no key needed for free tier."""

    BASE_URL = "https://api.assemblyai.com/v2"

    async def transcribe(self, audio: bytes, config: VoiceConfig) -> str:
        import httpx

        api_key = config.stt_api_key or os.environ.get("ASSEMBLYAI_API_KEY", "")
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY required for AssemblyAI STT")

        async with httpx.AsyncClient() as client:
            upload_resp = await client.post(
                f"{self.BASE_URL}/upload",
                headers={"authorization": api_key},
                content=audio,
                timeout=60,
            )
            upload_resp.raise_for_status()
            audio_url = upload_resp.json()["upload_url"]

            headers = {"authorization": api_key, "content-type": "application/json"}
            resp = await client.post(
                f"{self.BASE_URL}/transcript",
                headers=headers,
                json={"audio_url": audio_url},
                timeout=30,
            )
            resp.raise_for_status()
            transcript_id = resp.json()["id"]

            while True:
                status_resp = await client.get(
                    f"{self.BASE_URL}/transcript/{transcript_id}",
                    headers=headers,
                    timeout=30,
                )
                status = status_resp.json()
                if status["status"] == "completed":
                    return status["text"]
                elif status["status"] == "error":
                    raise RuntimeError(f"AssemblyAI error: {status.get('error')}")
                await asyncio.sleep(2)


class DeepgramSTTProvider(STTProvider):
    """Deepgram STT — free tier available."""

    async def transcribe(self, audio: bytes, config: VoiceConfig) -> str:
        import httpx

        api_key = config.stt_api_key or os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY required for Deepgram STT")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen",
                headers={"Authorization": f"Token {api_key}"},
                content=audio,
                params={"model": "nova-2", "smart_format": "true"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["results"]["channels"][0]["alternatives"][0]["transcript"]


class WhisperSTTProvider(STTProvider):
    """Local Whisper STT via faster-whisper or openai-whisper."""

    def __init__(self):
        self._model = None

    async def transcribe(self, audio: bytes, config: VoiceConfig) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            import whisper

            model = whisper.load_model("base")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio)
                wav_path = f.name
            try:
                result = model.transcribe(wav_path)
                return result["text"].strip()
            finally:
                os.unlink(wav_path)

        if self._model is None:
            self._model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = self._model.transcribe(audio)
        return " ".join(seg.text for seg in segments).strip()


class FreeTTSSTTProvider(STTProvider):
    """FreeTTS transcription (limited but no key needed)."""

    async def transcribe(self, audio: bytes, config: VoiceConfig) -> str:
        import httpx

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio)
            wav_path = f.name
        try:
            async with httpx.AsyncClient() as client:
                with open(wav_path, "rb") as f:
                    resp = await client.post(
                        "https://freetts.org/api/stt",
                        files={"file": f},
                        timeout=30,
                    )
            resp.raise_for_status()
            data = resp.json()
            return data.get("text", "")
        finally:
            os.unlink(wav_path)


# ─────────────────────────────────────────────────────────────
# Voice Engine
# ─────────────────────────────────────────────────────────────


class VoiceEngine:
    """
    Orchestrates the full voice pipeline:
      listen() → transcribe() → LLM response → speak()

    Usage:
        engine = VoiceEngine(config)
        async with engine.voice_mode():
            # Audio loop runs — Ctrl+C to exit
            await asyncio.Future()  # run forever
    """

    TTS_PROVIDERS: dict[str, type[TTSProvider]] = {
        "freetts": FreeTTSProvider,
        "openai": OpenAITTSProvider,
        "system": SystemTTSProvider,
    }

    STT_PROVIDERS: dict[str, type[STTProvider]] = {
        "assemblyai": AssemblyAISTTProvider,
        "deepgram": DeepgramSTTProvider,
        "whisper": WhisperSTTProvider,
        "freetts": FreeTTSSTTProvider,
    }

    def __init__(self, config: VoiceConfig | None = None, llm_callback=None):
        self.config = config or VoiceConfig()
        self.llm_callback = llm_callback
        self._running = False
        self._tts: TTSProvider | None = None
        self._stt: STTProvider | None = None

    @property
    def tts(self) -> TTSProvider:
        if self._tts is None:
            cls = self.TTS_PROVIDERS.get(self.config.tts_provider, FreeTTSProvider)
            self._tts = cls()
        return self._tts

    @property
    def stt(self) -> STTProvider:
        if self._stt is None:
            cls = self.STT_PROVIDERS.get(self.config.stt_provider, WhisperSTTProvider)
            self._stt = cls()
        return self._stt

    async def speak(self, text: str) -> None:
        """Convert text to speech and play it."""
        print(f"\n[Nexus]: {text}")
        try:
            audio = await self.tts.speak(text, self.config)
            await self.tts.play_audio(audio, self.config)
        except Exception as e:
            print(f"\n[Nexus] Speech Error: {format_error(e)}")

    async def transcribe_audio(self, audio: bytes) -> str:
        """Convert audio to text."""
        return await self.stt.transcribe(audio, self.config)

    async def listen_and_transcribe(self) -> str | None:
        """Record from mic and transcribe. Returns None if no speech detected."""
        try:
            audio, duration = await self.stt.listen_until_speech(self.config, timeout=30.0)
            if duration < 0.3:
                return None
            if audio:
                text = await self.transcribe_audio(audio)
                return text.strip() if text else None
        except Exception as e:
            print(f"\n[Nexus] Listen Error: {format_error(e)}")
        return None

    async def respond_and_speak(self, text: str) -> str:
        """Send text to LLM and speak the response."""
        if self.llm_callback:
            response = await self.llm_callback(text)
        else:
            response = text

        if response:
            await self.speak(response)
        return response

    async def voice_mode(self) -> AsyncIterator[None]:
        """Async context manager for full voice conversation loop."""
        self._running = True
        print(f"""
╔══════════════════════════════════════════════════════════╗
║              NEXUS VOICE MODE                           ║
║                                                           ║
║  Nexus is listening... Speak to chat.                    ║
║  Say 'exit' or press Ctrl+C to return to text mode.      ║
║  Provider: TTS={self.config.tts_provider}, STT={self.config.stt_provider}                             ║
╚══════════════════════════════════════════════════════════╝
""")

        await self.speak("Voice mode activated. I'm listening. What would you like to work on?")

        try:
            while self._running:
                try:
                    text = await asyncio.wait_for(
                        self.listen_and_transcribe(),
                        timeout=60.0,
                    )
                except asyncio.TimeoutError:
                    continue

                if not text:
                    continue

                print(f"\n[You]: {text}")

                if text.lower() in ("exit", "quit", "stop", "goodbye", "bye"):
                    await self.speak("Switching back to text mode. Catch you later!")
                    self._running = False
                    break

                await self.respond_and_speak(text)

        except KeyboardInterrupt:
            print("\n[Voice] Interrupted.")
            await self.speak("Returning to text mode.")
        finally:
            self._running = False
            yield

    def stop(self) -> None:
        """Stop the voice loop."""
        self._running = False


# ─────────────────────────────────────────────────────────────
# Provider registry (like OpenClaw's provider system)
# ─────────────────────────────────────────────────────────────

VOICE_CONFIG_DEFAULTS: dict[str, Any] = {
    "tts_provider": os.environ.get("NEXUS_TTS_PROVIDER", "freetts"),
    "stt_provider": os.environ.get("NEXUS_STT_PROVIDER", "whisper"),
    "voice": os.environ.get("NEXUS_VOICE", "en-US-JennyNeural"),
    "stt_api_key": os.environ.get("ASSEMBLYAI_API_KEY") or os.environ.get("DEEPGRAM_API_KEY"),
    "tts_api_key": os.environ.get("OPENAI_API_KEY"),
    "wake_word": os.environ.get("NEXUS_WAKE_WORD", "hey nexus"),
    "stream_tts": os.environ.get("NEXUS_STREAM_TTS", "true").lower() == "true",
}


def get_voice_engine(llm_callback=None, **overrides) -> VoiceEngine:
    """Factory: build a configured VoiceEngine."""
    defaults = {k: v for k, v in VOICE_CONFIG_DEFAULTS.items() if v is not None}
    defaults.update(overrides)
    cfg = VoiceConfig(**defaults)
    return VoiceEngine(config=cfg, llm_callback=llm_callback)


def list_tts_voices() -> list[str]:
    """List available TTS voices for the configured provider."""
    return FreeTTSProvider.VOICES
