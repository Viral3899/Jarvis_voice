"""
Voice I/O — wake word detection, speech-to-text, text-to-speech.
"""

import os
import re
import sys
import tempfile
import threading
import wave
from pathlib import Path

import pyttsx3
import requests
import speech_recognition as sr
import winsound

WAKE_WORD = os.getenv("WAKE_WORD", "jarvis").lower()
GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_TRANSCRIPTION_MODEL = "whisper-large-v3"
GROQ_TRANSCRIPTION_PROMPT = (
    "Jarvis, WhatsApp, Gmail, Google Calendar, LinkedIn, Naukri, Indeed."
)
ASR_ARTIFACT_PHRASES = (
    "transcription by",
    "translation by",
    "transcribe spoken",
    "thanks for watching",
    "thank you for watching",
    "subscribe to my channel",
)
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_TTS_PROVIDER = "elevenlabs"
ELEVENLABS_TTS_MODEL = "eleven_v3"
LANGUAGE_CODES = {
    "en": ("en", "English"),
    "english": ("en", "English"),
    "hi": ("hi", "Hindi"),
    "hindi": ("hi", "Hindi"),
}
SPOKEN_URL_PATTERN = re.compile(
    r"""(?ix)
    (?<![\w@])
    (?:
        (?:https?://|www\.)[^\s<>"']+
        |
        (?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}
        (?::\d+)?
        (?:/[^\s<>"']*|\?[^\s<>"']*|\#[^\s<>"']*)?
    )
    """
)
SPOKEN_MEETING_DETAILS_PATTERN = re.compile(
    r"(?im)\b(?:join via audio|(?:or,\s*)?dial(?:-in)?|"
    r"webinar\s*(?:id|number|code)|meeting\s*(?:id|number|code|passcode)|"
    r"passcode|password|more international numbers)\b.*$"
)
SPOKEN_PHONE_PATTERN = re.compile(r"(?<!\w)\+\s?\d[\d(). -]{5,}\d(?!\w)")


def sanitize_speech_text(text: str, language_code: str | None = None) -> str:
    """Keep links and conference access details out of spoken responses."""
    language = (language_code or "").strip().lower()
    link_label = "एक लिंक" if language in {"hi", "hindi"} else "a link"
    details_label = (
        "मीटिंग में शामिल होने की जानकारी छोड़ी गई"
        if language in {"hi", "hindi"}
        else "meeting join details omitted"
    )

    text = SPOKEN_MEETING_DETAILS_PATTERN.sub("", text)
    text = SPOKEN_PHONE_PATTERN.sub(details_label, text)

    def replace_url(match: re.Match[str]) -> str:
        url = match.group()
        trailing = ""
        while url and url[-1] in ".,!?;:)]}":
            trailing = url[-1] + trailing
            url = url[:-1]
        return (link_label if url else match.group()) + trailing

    text = SPOKEN_URL_PATTERN.sub(replace_url, text)
    return re.sub(r"\s+", " ", text).strip()


def _print_safe(text: str):
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


class VoiceEngine:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 175)
        voices = self.engine.getProperty("voices")
        if len(voices) > 1:
            self.engine.setProperty("voice", voices[1].id)

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True

        self._speaking = False
        self._lock = threading.Lock()
        self._microphone_lock = threading.Lock()
        default_language = os.getenv("DEFAULT_LANGUAGE", "hi").strip().lower()
        if default_language not in LANGUAGE_CODES:
            raise ValueError(
                "DEFAULT_LANGUAGE must be Hindi (hi) or English (en)."
            )
        self.default_language_code = LANGUAGE_CODES[default_language][0]
        self.last_language_code, self.last_language = LANGUAGE_CODES[default_language]
        self.last_transcript = ""
        self._elevenlabs_warning_shown = False
        self._barge_lock = threading.Lock()
        self._barge_transcription_active = False
        self._barge_command: str | None = None
        self._barge_stop_listener = None
        self._speech_interrupted = threading.Event()
        self._current_speech_text = ""
        self.tts_provider = os.getenv(
            "TTS_PROVIDER", DEFAULT_TTS_PROVIDER
        ).strip().lower()
        if self.tts_provider not in {"elevenlabs", "local"}:
            raise ValueError(
                "TTS_PROVIDER must be either 'elevenlabs' or 'local'."
            )

    def speak(self, text: str, language_code: str | None = None):
        """Speak aloud with ElevenLabs when configured; otherwise use local TTS."""
        speech_language = language_code or self.last_language_code
        text = sanitize_speech_text(text, speech_language)
        if not text.strip():
            return

        with self._lock:
            self._speaking = True
            self._current_speech_text = text
            self._speech_interrupted.clear()
            stop_listener = self._start_barge_in_listener()
            try:
                _print_safe(f"Jarvis: {text}")
                if self.tts_provider == "elevenlabs":
                    spoke = self._speak_with_elevenlabs(text, language_code)
                else:
                    spoke = False
                if not spoke and not self._speech_interrupted.is_set():
                    self.engine.say(text)
                    self.engine.runAndWait()
            finally:
                if stop_listener:
                    try:
                        stop_listener(wait_for_stop=True)
                    finally:
                        self._microphone_lock.release()
                self._barge_stop_listener = None
                self._current_speech_text = ""
                self._speaking = False

    def _start_barge_in_listener(self):
        self._microphone_lock.acquire()
        try:
            microphone = sr.Microphone()
            stop_listener = self.recognizer.listen_in_background(
                microphone,
                self._on_barge_in_audio,
                phrase_time_limit=12,
            )
            self._barge_stop_listener = stop_listener
            return stop_listener
        except (OSError, AttributeError, AssertionError, RuntimeError) as e:
            self._microphone_lock.release()
            _print_safe(f"Warning: Could not start speech interruption listener: {e}")
            return None

    def _on_barge_in_audio(self, _, audio):
        with self._barge_lock:
            if (
                self._barge_transcription_active
                or not self._speaking
                or self._speech_interrupted.is_set()
            ):
                return
            self._barge_transcription_active = True

        threading.Thread(
            target=self._transcribe_barge_in,
            args=(audio,),
            daemon=True,
        ).start()

    def _transcribe_barge_in(self, audio):
        try:
            text = self._transcribe(audio)
            if not text:
                return

            wake_word = re.escape(WAKE_WORD)
            match = re.search(rf"(?<!\w){wake_word}(?!\w)", text, re.IGNORECASE)
            if not match:
                return
            _print_safe(f"You: {text}")

            heard = re.sub(
                rf"(?<!\w){wake_word}(?!\w)",
                "",
                text,
                count=1,
                flags=re.IGNORECASE,
            ).strip(" ,.!?;:")
            expected = re.sub(r"\s+", " ", self._current_speech_text.lower()).strip()
            normalized_heard = re.sub(r"\s+", " ", text.lower()).strip()
            if normalized_heard and normalized_heard in expected:
                return

            with self._barge_lock:
                self._barge_command = heard
            self._speech_interrupted.set()
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except RuntimeError as e:
                _print_safe(f"Warning: Could not stop current audio: {e}")
            try:
                self.engine.stop()
            except RuntimeError as e:
                _print_safe(f"Warning: Could not stop local speech: {e}")
            _print_safe("Wake word heard. Stopping speech and handling your request.")
        except Exception as e:
            _print_safe(f"Warning: Could not process speech interruption: {e}")
        finally:
            with self._barge_lock:
                self._barge_transcription_active = False

    def consume_interrupted_command(self) -> str | None:
        """Return a wake-word command detected while Jarvis was speaking."""
        with self._barge_lock:
            command = self._barge_command
            self._barge_command = None
            return command

    def _transcribe(self, audio) -> str | None:
        response = requests.post(
            GROQ_TRANSCRIPTION_URL,
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY', '')}"
            },
            files={
                "file": ("speech.wav", audio.get_wav_data(), "audio/wav")
            },
            data={
                "model": GROQ_TRANSCRIPTION_MODEL,
                "prompt": GROQ_TRANSCRIPTION_PROMPT,
                "temperature": 0,
                "response_format": "verbose_json",
            },
            timeout=15,
        )
        response.raise_for_status()
        transcription = response.json()
        text = str(transcription.get("text", "")).strip()
        normalized_text = " ".join(text.casefold().split())
        if not text or not any(character.isalnum() for character in text):
            return None
        if any(phrase in normalized_text for phrase in ASR_ARTIFACT_PHRASES):
            return None

        detected_language = str(
            transcription.get("language", self.default_language_code)
        ).strip().lower()
        language_code, language_name = LANGUAGE_CODES.get(
            detected_language,
            LANGUAGE_CODES[getattr(self, "default_language_code", "hi")],
        )
        self.last_language_code = language_code
        self.last_language = language_name
        self.last_transcript = text
        return text

    def _speak_with_elevenlabs(
        self, text: str, language_code: str | None = None
    ) -> bool:
        api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        voice_id = os.getenv(
            "ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"
        ).strip()
        if not api_key or not voice_id:
            if not self._elevenlabs_warning_shown:
                _print_safe(
                    "Warning: ElevenLabs is not configured; using local speech. "
                    "Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env."
                )
                self._elevenlabs_warning_shown = True
            return False

        audio_path = None
        try:
            request_done = threading.Event()
            result = {}

            def request_audio():
                try:
                    response = requests.post(
                        f"{ELEVENLABS_TTS_URL}/{voice_id}",
                        params={"output_format": "wav_22050"},
                        headers={
                            "xi-api-key": api_key,
                            "Accept": "audio/wav",
                            "Content-Type": "application/json",
                        },
                        json={
                            "text": text,
                            "model_id": ELEVENLABS_TTS_MODEL,
                            "language_code": language_code or self.last_language_code,
                            "voice_settings": {
                                "stability": 0.45,
                                "similarity_boost": 0.8,
                                "style": 0.25,
                                "use_speaker_boost": True,
                            },
                        },
                        timeout=45,
                    )
                    response.raise_for_status()
                    result["audio"] = response.content
                except requests.RequestException as e:
                    result["error"] = e
                finally:
                    request_done.set()

            threading.Thread(target=request_audio, daemon=True).start()
            while not request_done.wait(0.1):
                if self._speech_interrupted.is_set():
                    return True
            if self._speech_interrupted.is_set():
                return True
            if "error" in result:
                raise result["error"]

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
                audio_file.write(result["audio"])
                audio_path = audio_file.name

            if self._speech_interrupted.is_set():
                return True

            winsound.PlaySound(
                audio_path,
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
            with wave.open(audio_path, "rb") as wav_file:
                duration = wav_file.getnframes() / wav_file.getframerate()
            self._speech_interrupted.wait(duration)
            if self._speech_interrupted.is_set():
                winsound.PlaySound(None, winsound.SND_PURGE)
            return True
        except (requests.RequestException, OSError, RuntimeError, wave.Error) as e:
            _print_safe(f"Warning: ElevenLabs speech failed; using local speech instead: {e}")
            return False
        finally:
            if audio_path:
                try:
                    Path(audio_path).unlink()
                except OSError as e:
                    _print_safe(f"Warning: Could not remove temporary speech audio: {e}")

    def listen(
        self,
        timeout: int = 8,
        phrase_limit: int = 15,
        report_transcript: bool = True,
    ) -> str | None:
        """Transcribe speech with automatic multilingual language detection."""
        with self._microphone_lock:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                try:
                    audio = self.recognizer.listen(
                        source, timeout=timeout, phrase_time_limit=phrase_limit
                    )
                    text = self._transcribe(audio)
                    if text is None:
                        if report_transcript:
                            _print_safe(
                                "Warning: Speech recognition returned no transcript."
                            )
                    elif report_transcript:
                        _print_safe(f"You: {text}")
                    return text
                except (sr.WaitTimeoutError, sr.UnknownValueError):
                    return None
                except requests.RequestException as e:
                    _print_safe(f"Warning: Groq speech recognition error: {e}")
                    return None
                except (ValueError, KeyError) as e:
                    _print_safe(f"Warning: Invalid speech recognition response: {e}")
                    return None

    def wait_for_wake_word(self) -> str | None:
        """
        Continuously listen. When wake word is detected, return the
        rest of the phrase (or listen again for the command).
        """
        while True:
            interrupted_command = self.consume_interrupted_command()
            if interrupted_command is not None:
                return interrupted_command

            text = self.listen(
                timeout=1.5, phrase_limit=10, report_transcript=False
            )
            if text is None:
                continue

            wake_word = re.escape(WAKE_WORD)
            match = re.search(rf"(?<!\w){wake_word}(?!\w)", text, re.IGNORECASE)
            if not match:
                continue
            _print_safe(f"You: {text}")

            command = re.sub(
                rf"(?<!\w){wake_word}(?!\w)",
                "",
                text,
                count=1,
                flags=re.IGNORECASE,
            ).strip(" ,.!?;:")
            if command:
                return command
            # Let the orchestrator respond in the detected language before listening.
            return ""
