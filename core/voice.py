"""
Voice I/O — wake word detection, speech-to-text, text-to-speech.
"""

import os
import re
import sys
import tempfile
import threading
import time
from difflib import SequenceMatcher
import wave
from pathlib import Path

import pyttsx3
import requests
import speech_recognition as sr
import winsound

WAKE_WORD = os.getenv("WAKE_WORD", "jarvis").lower()
GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_TRANSCRIPTION_MODEL = "whisper-large-v3"
GROQ_TRANSCRIPTION_TIMEOUT = 6
GROQ_RETRY_COOLDOWN = 300
FALLBACK_SPEECH_TIMEOUT = 5
DEFAULT_GOOGLE_FALLBACK_LOCALES = (
    "gu-IN,hi-IN,en-IN"
)
GROQ_TRANSCRIPTION_PROMPT = (
    "Jarvis (जार्विस, જાર્વિસ), WhatsApp, Gmail, Google Calendar, "
    "LinkedIn, Naukri, Indeed. Multilingual speech, including code-switching."
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
    "af": ("af", "Afrikaans"), "afrikaans": ("af", "Afrikaans"),
    "am": ("am", "Amharic"), "amharic": ("am", "Amharic"),
    "ar": ("ar", "Arabic"), "arabic": ("ar", "Arabic"),
    "az": ("az", "Azerbaijani"), "azeri": ("az", "Azerbaijani"),
    "be": ("be", "Belarusian"), "belarusian": ("be", "Belarusian"),
    "bn": ("bn", "Bengali"), "bengali": ("bn", "Bengali"),
    "bg": ("bg", "Bulgarian"), "bulgarian": ("bg", "Bulgarian"),
    "bs": ("bs", "Bosnian"), "bosnian": ("bs", "Bosnian"),
    "ca": ("ca", "Catalan"), "catalan": ("ca", "Catalan"),
    "ceb": ("ceb", "Cebuano"), "cebuano": ("ceb", "Cebuano"),
    "cs": ("cs", "Czech"), "czech": ("cs", "Czech"),
    "da": ("da", "Danish"), "danish": ("da", "Danish"),
    "de": ("de", "German"), "german": ("de", "German"),
    "en": ("en", "English"), "english": ("en", "English"),
    "es": ("es", "Spanish"), "spanish": ("es", "Spanish"),
    "et": ("et", "Estonian"), "estonian": ("et", "Estonian"),
    "eu": ("eu", "Basque"), "basque": ("eu", "Basque"),
    "fa": ("fa", "Persian"), "persian": ("fa", "Persian"),
    "fi": ("fi", "Finnish"), "finnish": ("fi", "Finnish"),
    "fr": ("fr", "French"), "french": ("fr", "French"),
    "gl": ("gl", "Galician"), "galician": ("gl", "Galician"),
    "el": ("el", "Greek"), "greek": ("el", "Greek"),
    "gu": ("gu", "Gujarati"), "gujarati": ("gu", "Gujarati"),
    "ha": ("ha", "Hausa"), "hausa": ("ha", "Hausa"),
    "he": ("he", "Hebrew"), "hebrew": ("he", "Hebrew"),
    "hi": ("hi", "Hindi"), "hindi": ("hi", "Hindi"),
    "hr": ("hr", "Croatian"), "croatian": ("hr", "Croatian"),
    "hu": ("hu", "Hungarian"), "hungarian": ("hu", "Hungarian"),
    "hy": ("hy", "Armenian"), "armenian": ("hy", "Armenian"),
    "id": ("id", "Indonesian"), "indonesian": ("id", "Indonesian"),
    "is": ("is", "Icelandic"), "icelandic": ("is", "Icelandic"),
    "it": ("it", "Italian"), "italian": ("it", "Italian"),
    "ja": ("ja", "Japanese"), "japanese": ("ja", "Japanese"),
    "jv": ("jv", "Javanese"), "javanese": ("jv", "Javanese"),
    "ka": ("ka", "Georgian"), "georgian": ("ka", "Georgian"),
    "kk": ("kk", "Kazakh"), "kazakh": ("kk", "Kazakh"),
    "km": ("km", "Khmer"), "khmer": ("km", "Khmer"),
    "ky": ("ky", "Kyrgyz"), "kyrgyz": ("ky", "Kyrgyz"),
    "la": ("la", "Latin"), "latin": ("la", "Latin"),
    "lb": ("lb", "Luxembourgish"), "luxembourgish": ("lb", "Luxembourgish"),
    "kn": ("kn", "Kannada"), "kannada": ("kn", "Kannada"),
    "ko": ("ko", "Korean"), "korean": ("ko", "Korean"),
    "lo": ("lo", "Lao"), "lao": ("lo", "Lao"),
    "lt": ("lt", "Lithuanian"), "lithuanian": ("lt", "Lithuanian"),
    "lv": ("lv", "Latvian"), "latvian": ("lv", "Latvian"),
    "ml": ("ml", "Malayalam"), "malayalam": ("ml", "Malayalam"),
    "mk": ("mk", "Macedonian"), "macedonian": ("mk", "Macedonian"),
    "mg": ("mg", "Malagasy"), "malagasy": ("mg", "Malagasy"),
    "mi": ("mi", "Maori"), "maori": ("mi", "Maori"),
    "mn": ("mn", "Mongolian"), "mongolian": ("mn", "Mongolian"),
    "mr": ("mr", "Marathi"), "marathi": ("mr", "Marathi"),
    "ms": ("ms", "Malay"), "malay": ("ms", "Malay"),
    "mt": ("mt", "Maltese"), "maltese": ("mt", "Maltese"),
    "my": ("my", "Burmese"), "burmese": ("my", "Burmese"),
    "ne": ("ne", "Nepali"), "nepali": ("ne", "Nepali"),
    "nl": ("nl", "Dutch"), "dutch": ("nl", "Dutch"),
    "no": ("no", "Norwegian"), "norwegian": ("no", "Norwegian"),
    "oc": ("oc", "Occitan"), "occitan": ("oc", "Occitan"),
    "pl": ("pl", "Polish"), "polish": ("pl", "Polish"),
    "ps": ("ps", "Pashto"), "pashto": ("ps", "Pashto"),
    "pa": ("pa", "Punjabi"), "punjabi": ("pa", "Punjabi"),
    "pt": ("pt", "Portuguese"), "portuguese": ("pt", "Portuguese"),
    "ro": ("ro", "Romanian"), "romanian": ("ro", "Romanian"),
    "ru": ("ru", "Russian"), "russian": ("ru", "Russian"),
    "sa": ("sa", "Sanskrit"), "sanskrit": ("sa", "Sanskrit"),
    "sd": ("sd", "Sindhi"), "sindhi": ("sd", "Sindhi"),
    "si": ("si", "Sinhala"), "sinhala": ("si", "Sinhala"),
    "sn": ("sn", "Shona"), "shona": ("sn", "Shona"),
    "sk": ("sk", "Slovak"), "slovak": ("sk", "Slovak"),
    "sl": ("sl", "Slovenian"), "slovenian": ("sl", "Slovenian"),
    "sq": ("sq", "Albanian"), "albanian": ("sq", "Albanian"),
    "sr": ("sr", "Serbian"), "serbian": ("sr", "Serbian"),
    "so": ("so", "Somali"), "somali": ("so", "Somali"),
    "sv": ("sv", "Swedish"), "swedish": ("sv", "Swedish"),
    "sw": ("sw", "Swahili"), "swahili": ("sw", "Swahili"),
    "ta": ("ta", "Tamil"), "tamil": ("ta", "Tamil"),
    "th": ("th", "Thai"), "thai": ("th", "Thai"),
    "te": ("te", "Telugu"), "telugu": ("te", "Telugu"),
    "tr": ("tr", "Turkish"), "turkish": ("tr", "Turkish"),
    "uk": ("uk", "Ukrainian"), "ukrainian": ("uk", "Ukrainian"),
    "ur": ("ur", "Urdu"), "urdu": ("ur", "Urdu"),
    "uz": ("uz", "Uzbek"), "uzbek": ("uz", "Uzbek"),
    "vi": ("vi", "Vietnamese"), "vietnamese": ("vi", "Vietnamese"),
    "cy": ("cy", "Welsh"), "welsh": ("cy", "Welsh"),
    "yi": ("yi", "Yiddish"), "yiddish": ("yi", "Yiddish"),
    "yo": ("yo", "Yoruba"), "yoruba": ("yo", "Yoruba"),
    "zh": ("zh", "Chinese"), "chinese": ("zh", "Chinese"),
    "yue": ("yue", "Cantonese"), "cantonese": ("yue", "Cantonese"),
    "zu": ("zu", "Zulu"), "zulu": ("zu", "Zulu"),
}
GOOGLE_LOCALES_BY_LANGUAGE = {
    "af": "af-ZA", "am": "am-ET", "ar": "ar-SA", "az": "az-AZ",
    "be": "be-BY", "bn": "bn-IN", "bg": "bg-BG",
    "bs": "bs-BA", "ca": "ca-ES", "ceb": "ceb-PH", "cs": "cs-CZ",
    "da": "da-DK", "de": "de-DE",
    "el": "el-GR", "en": "en-IN", "es": "es-ES", "et": "et-EE",
    "eu": "eu-ES", "fa": "fa-IR", "fi": "fi-FI", "fr": "fr-FR",
    "gl": "gl-ES", "gu": "gu-IN", "ha": "ha-NG", "he": "he-IL", "hi": "hi-IN",
    "hr": "hr-HR", "hu": "hu-HU", "hy": "hy-AM", "id": "id-ID",
    "is": "is-IS", "it": "it-IT", "ja": "ja-JP", "jv": "jv-ID",
    "ka": "ka-GE", "kk": "kk-KZ", "km": "km-KH", "kn": "kn-IN",
    "ky": "ky-KG", "la": "la", "lb": "lb-LU",
    "ko": "ko-KR", "lo": "lo-LA", "lt": "lt-LT", "lv": "lv-LV",
    "ml": "ml-IN", "mk": "mk-MK", "mn": "mn-MN", "mr": "mr-IN", "ms": "ms-MY",
    "mg": "mg-MG", "mi": "mi-NZ",
    "mt": "mt-MT", "my": "my-MM", "ne": "ne-NP", "nl": "nl-NL",
    "no": "no-NO", "oc": "oc-FR", "pa": "pa-IN", "pl": "pl-PL", "ps": "ps-AF", "pt": "pt-BR",
    "ro": "ro-RO", "ru": "ru-RU", "sa": "sa-IN", "sd": "sd-IN",
    "si": "si-LK", "sn": "sn-ZW", "sk": "sk-SK", "sl": "sl-SI",
    "sq": "sq-AL", "sr": "sr-RS", "so": "so-SO", "sv": "sv-SE",
    "sw": "sw-KE", "ta": "ta-IN",
    "te": "te-IN", "th": "th-TH", "tr": "tr-TR", "uk": "uk-UA",
    "ur": "ur-PK", "uz": "uz-UZ", "vi": "vi-VN", "cy": "cy-GB",
    "yi": "yi", "yo": "yo-NG", "zh": "zh-CN", "yue": "yue-HK",
    "zu": "zu-ZA",
}
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "hi").strip().lower()
if DEFAULT_LANGUAGE not in LANGUAGE_CODES:
    raise ValueError(f"Unsupported DEFAULT_LANGUAGE: {DEFAULT_LANGUAGE}")
DEFAULT_LANGUAGE_CODE = LANGUAGE_CODES[DEFAULT_LANGUAGE][0]
DEFAULT_LANGUAGE_NAME = LANGUAGE_CODES[DEFAULT_LANGUAGE][1]
COMMAND_WORDS = (
    "calendar", "check", "email", "gmail", "instagram", "jobs", "status",
    "telegram", "whatsapp",
)
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
    link_labels = {
        "en": "a link", "gu": "એક લિંક", "hi": "एक लिंक",
        "es": "un enlace", "fr": "un lien", "de": "ein Link",
        "it": "un link", "pt": "um link", "ru": "ссылка",
        "ar": "رابط", "bn": "একটি লিংক", "mr": "एक लिंक",
        "pa": "ਇੱਕ ਲਿੰਕ", "ta": "ஒரு இணைப்பு", "te": "ఒక లింక్",
        "ur": "ایک لنک", "zh": "一个链接", "ja": "リンク",
    }
    link_label = link_labels.get(language, "a link")
    details_label = {
        "gu": "મીટિંગમાં જોડાવાની વિગતો છોડી છે",
        "hi": "मीटिंग में शामिल होने की जानकारी छोड़ी गई",
    }.get(language, "meeting join details omitted")

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


def _wake_word_pattern() -> re.Pattern[str]:
    wake_words = {WAKE_WORD, "जार्विस", "જાર્વિસ"}
    alternatives = "|".join(
        re.escape(word) for word in sorted(wake_words, key=len, reverse=True)
    )
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def _normalize_near_wake_word(text: str) -> str:
    """Correct only close Latin-script wake-word transcription variants."""
    aliases = {"jarvis", "jarwis", "jervis", "javis"}
    return re.sub(
        r"(?<!\w)[A-Za-z]{4,8}(?!\w)",
        lambda match: "Jarvis"
        if match.group().casefold() in aliases
        or SequenceMatcher(None, match.group().casefold(), "jarvis").ratio() >= 0.83
        else match.group(),
        text,
    )


def _resolve_language(value: str, fallback_code: str) -> tuple[str, str]:
    """Resolve Whisper language names/codes and regional locale codes."""
    normalized = value.strip().casefold()
    language = LANGUAGE_CODES.get(normalized)
    if language:
        return language
    base_code = normalized.split("-", 1)[0]
    language = LANGUAGE_CODES.get(base_code)
    if language:
        return language
    return LANGUAGE_CODES.get(fallback_code, LANGUAGE_CODES["hi"])


def correct_nearby_command_words(text: str) -> str:
    """Correct close ASR variants of known command words, not names or free text."""
    words = list(re.finditer(r"(?<!\w)[A-Za-z]{4,}(?!\w)", text))
    edits = []
    for word in words[:3]:
        token = word.group().casefold()
        match = max(
            COMMAND_WORDS,
            key=lambda candidate: SequenceMatcher(None, token, candidate).ratio(),
        )
        if token != match and SequenceMatcher(None, token, match).ratio() >= 0.86:
            edits.append((word.start(), word.end(), match))
    for start, end, replacement in reversed(edits):
        text = f"{text[:start]}{replacement}{text[end:]}"
    return text


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
        self.recognizer.operation_timeout = FALLBACK_SPEECH_TIMEOUT
        self._groq_retry_after = 0.0
        self._last_transcription_warning = {}

        self._speaking = False
        self._lock = threading.Lock()
        self._microphone_lock = threading.Lock()
        self.default_language_code = DEFAULT_LANGUAGE_CODE
        self.last_language_code = DEFAULT_LANGUAGE_CODE
        self.last_language = DEFAULT_LANGUAGE_NAME
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

    def speak(
        self,
        text: str,
        language_code: str | None = None,
        prefer_local: bool = False,
    ):
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
                if self.tts_provider == "elevenlabs" and not prefer_local:
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

            normalized_text = _normalize_near_wake_word(text)
            wake_word = _wake_word_pattern()
            match = wake_word.search(normalized_text)
            if not match:
                return
            _print_safe(f"You: {text}")

            heard = wake_word.sub("", normalized_text, count=1).strip(" ,.!?;:")
            heard = correct_nearby_command_words(heard)
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
        if time.monotonic() >= self._groq_retry_after:
            try:
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
                    timeout=(3, GROQ_TRANSCRIPTION_TIMEOUT),
                )
                response.raise_for_status()
                transcription = response.json()
                if not isinstance(transcription, dict):
                    raise ValueError("Groq returned an invalid transcription response.")
            except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                self._groq_retry_after = time.monotonic() + GROQ_RETRY_COOLDOWN
                self._warn_transcription_failure(
                    "groq",
                    f"Groq unavailable; using Google speech recognition fallback: "
                    f"{type(e).__name__}: {e}",
                )
                return self._transcribe_with_google(audio)
        else:
            return self._transcribe_with_google(audio)

        text = str(transcription.get("text", "")).strip()
        normalized_text = " ".join(text.casefold().split())
        if not text or not any(character.isalnum() for character in text):
            return None
        if any(phrase in normalized_text for phrase in ASR_ARTIFACT_PHRASES):
            return None

        detected_language = str(
            transcription.get("language", self.default_language_code)
        ).strip().lower()
        self._groq_retry_after = 0.0
        language_code, language_name = _resolve_language(
            detected_language, self.default_language_code
        )
        self.last_language_code = language_code
        self.last_language = language_name
        self.last_transcript = text
        return text

    def _transcribe_with_google(self, audio) -> str | None:
        """Use the last detected language, then configured Google locales."""
        configured_locales = os.getenv(
            "SPEECH_FALLBACK_LOCALES",
            DEFAULT_GOOGLE_FALLBACK_LOCALES,
        )
        locales = [GOOGLE_LOCALES_BY_LANGUAGE.get(self.last_language_code)]
        locales.extend(
            locale.strip()
            for locale in configured_locales.split(",")
            if locale.strip()
        )
        locales = list(dict.fromkeys(locale for locale in locales if locale))
        text = ""
        recognized_locale = None
        for locale in locales:
            try:
                text = self.recognizer.recognize_google(
                    audio, language=locale
                ).strip()
                if text:
                    recognized_locale = locale
                    break
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                self._warn_transcription_failure(
                    "google",
                    f"Google speech recognition fallback failed: {e}",
                )
                return None

        if not text or not any(character.isalnum() for character in text):
            return None

        if recognized_locale:
            recognized_code = recognized_locale.split("-", 1)[0].lower()
            self.last_language_code, self.last_language = _resolve_language(
                recognized_code, self.default_language_code
            )
        self.last_transcript = text
        return text

    def _warn_transcription_failure(self, backend: str, message: str) -> None:
        """Keep persistent provider outages visible without warning on every listen."""
        now = time.monotonic()
        last_warning = self._last_transcription_warning.get(backend)
        if last_warning is None or now - last_warning >= GROQ_RETRY_COOLDOWN:
            _print_safe(f"Warning: {message}")
            self._last_transcription_warning[backend] = now

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

    def record_audio(self, timeout: int = 8, phrase_limit: int = 30) -> bytes | None:
        """Record a short microphone clip and return it as WAV bytes."""
        with self._microphone_lock:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                try:
                    audio = self.recognizer.listen(
                        source, timeout=timeout, phrase_time_limit=phrase_limit
                    )
                    return audio.get_wav_data()
                except sr.WaitTimeoutError:
                    _print_safe("Warning: No audio was recorded.")
                    return None
                except OSError as e:
                    _print_safe(f"Warning: Could not record audio: {e}")
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

            normalized_text = _normalize_near_wake_word(text)
            wake_word = _wake_word_pattern()
            match = wake_word.search(normalized_text)
            if not match:
                continue
            _print_safe(f"You: {text}")

            command = wake_word.sub("", normalized_text, count=1).strip(" ,.!?;:")
            command = correct_nearby_command_words(command)
            if command:
                return command
            # Let the orchestrator respond in the detected language before listening.
            return ""
