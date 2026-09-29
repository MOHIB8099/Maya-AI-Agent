import os
import time
import queue
import asyncio
import tempfile
import threading

import numpy as np
import sounddevice as sd
import pygame
import torch
import edge_tts

from scipy.io.wavfile import write
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad, VADIterator


# =========================================================
# 1. VOICE SETTINGS
# =========================================================

SAMPLE_RATE = 16000
CHANNELS = 1

# Fixed listening
DEFAULT_RECORD_SECONDS = 6

# Smart listening
AUDIO_CHUNK_SAMPLES = 512
MAX_LISTEN_SECONDS = 30

VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 700
VAD_SPEECH_PAD_MS = 200

# Whisper
WHISPER_MODEL_NAME = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

# Maya voice
VOICE_NAME = "hi-IN-SwaraNeural"
VOICE_RATE = "+0%"
VOICE_VOLUME = "+0%"
VOICE_PITCH = "+0Hz"


# =========================================================
# 2. VOICE STATE
# =========================================================

mic_enabled = True
voice_muted = False
is_speaking = False

whisper_model = None
vad_model = None

playback_lock = threading.Lock()


# =========================================================
# 3. INITIALIZE AUDIO PLAYER
# =========================================================

def initialize_audio_player():
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        return True

    except Exception as error:
        print("Audio player error:", error)
        return False


initialize_audio_player()


# =========================================================
# 4. LOAD WHISPER MODEL
# =========================================================

def load_whisper_model():
    global whisper_model

    if whisper_model is None:
        print("Loading Maya Whisper model...")

        whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )

        print("Maya Whisper model ready.")

    return whisper_model


# =========================================================
# 5. LOAD SILERO VAD MODEL
# =========================================================

def load_vad_model():
    global vad_model

    if vad_model is None:
        print("Loading Maya VAD model...")

        torch.set_num_threads(1)

        vad_model = load_silero_vad(
            onnx=True
        )

        print("Maya VAD ready.")

    return vad_model


# =========================================================
# 6. MICROPHONE ENABLE / DISABLE
# =========================================================

def enable_microphone():
    global mic_enabled

    mic_enabled = True
    return True


def disable_microphone():
    global mic_enabled

    mic_enabled = False
    return True


def microphone_status():
    return mic_enabled


# =========================================================
# 7. FIXED MICROPHONE RECORDING
# =========================================================

def record_audio(seconds=DEFAULT_RECORD_SECONDS):
    """
    Record microphone audio for fixed seconds.
    This is fallback/manual listening mode.
    """

    if not mic_enabled:
        print("Microphone is disabled.")
        return None

    try:
        print("Listening...")

        recording = sd.rec(
            int(seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16"
        )

        sd.wait()

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".wav"
        )

        audio_path = temp_file.name
        temp_file.close()

        write(
            audio_path,
            SAMPLE_RATE,
            recording
        )

        return audio_path

    except Exception as error:
        print("Microphone error:", error)
        return None


# =========================================================
# 8. SPEECH TO TEXT
# =========================================================

def transcribe_audio(audio_file):
    """
    Convert audio file into text using faster-whisper.
    """

    if not audio_file:
        return ""

    try:
        model = load_whisper_model()

        segments, info = model.transcribe(
            audio_file,
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500
            }
        )

        text_parts = []

        for segment in segments:
            text = segment.text.strip()

            if text:
                text_parts.append(text)

        final_text = " ".join(text_parts).strip()

        return final_text

    except Exception as error:
        print("Speech recognition error:", error)
        return ""

    finally:
        try:
            if os.path.exists(audio_file):
                os.remove(audio_file)
        except Exception:
            pass


# =========================================================
# 9. FIXED LISTEN FUNCTION
# =========================================================

def listen(seconds=DEFAULT_RECORD_SECONDS):
    """
    Fixed-duration listening.

    Flow:
    microphone
    -> record
    -> whisper
    -> text
    """

    audio_file = record_audio(seconds)

    if not audio_file:
        return ""

    return transcribe_audio(audio_file)


# =========================================================
# 10. SMART VAD LISTENING
# =========================================================

def smart_listen():
    """
    Advanced listening.

    Maya waits for speech.
    When speech starts, audio is collected.
    When silence is detected, recording stops automatically.
    """

    if not mic_enabled:
        print("Microphone is disabled.")
        return ""

    audio_queue = queue.Queue()

    collected_audio = []
    pre_speech_audio = []

    speech_started = False

    model = load_vad_model()

    vad_iterator = VADIterator(
        model,
        threshold=VAD_THRESHOLD,
        sampling_rate=SAMPLE_RATE,
        min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        speech_pad_ms=VAD_SPEECH_PAD_MS
    )

    def audio_callback(indata, frames, time_info, status):
        if status:
            print("Audio status:", status)

        audio_queue.put(
            indata.copy()
        )

    print("Maya is listening...")

    start_time = time.time()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=AUDIO_CHUNK_SAMPLES,
            callback=audio_callback
        ):

            while True:

                # Safety timeout
                if time.time() - start_time > MAX_LISTEN_SECONDS:
                    print("Listening timeout.")
                    break

                try:
                    audio_chunk = audio_queue.get(
                        timeout=1
                    )

                except queue.Empty:
                    continue

                mono_audio = audio_chunk[:, 0]

                audio_tensor = torch.from_numpy(
                    mono_audio.copy()
                )

                speech_event = vad_iterator(
                    audio_tensor,
                    return_seconds=True
                )

                # Keep a tiny amount of audio before speech starts
                if not speech_started:
                    pre_speech_audio.append(
                        mono_audio.copy()
                    )

                    # Prevent unlimited buildup
                    if len(pre_speech_audio) > 8:
                        pre_speech_audio.pop(0)

                if speech_event:

                    if "start" in speech_event:
                        speech_started = True

                        print("Speech detected...")

                        collected_audio.extend(
                            pre_speech_audio
                        )

                        pre_speech_audio.clear()

                    if "end" in speech_event:
                        if speech_started:
                            print("Speech ended.")
                            break

                if speech_started:
                    collected_audio.append(
                        mono_audio.copy()
                    )

    except Exception as error:
        print("Smart listening error:", error)

        try:
            vad_iterator.reset_states()
        except Exception:
            pass

        return ""

    try:
        vad_iterator.reset_states()
    except Exception:
        pass

    if not collected_audio:
        return ""

    try:
        final_audio = np.concatenate(
            collected_audio
        )

    except Exception:
        return ""

    final_audio = np.clip(
        final_audio,
        -1.0,
        1.0
    )

    final_audio_int16 = (
        final_audio * 32767
    ).astype(np.int16)

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".wav"
    )

    audio_path = temp_file.name
    temp_file.close()

    write(
        audio_path,
        SAMPLE_RATE,
        final_audio_int16
    )

    return transcribe_audio(
        audio_path
    )


# =========================================================
# 11. GENERATE MAYA VOICE
# =========================================================

async def generate_voice(text, output_file):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE_NAME,
        rate=VOICE_RATE,
        volume=VOICE_VOLUME,
        pitch=VOICE_PITCH
    )

    await communicate.save(
        output_file
    )


# =========================================================
# 12. STOP SPEAKING
# =========================================================

def stop_speaking():
    global is_speaking

    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()

        is_speaking = False

    except Exception:
        pass


# =========================================================
# 13. SPEAK
# =========================================================

def speak(text):
    """
    Convert Maya's text into voice and play it.
    """

    global is_speaking

    if voice_muted:
        return False

    if not text:
        return False

    text = str(text).strip()

    if not text:
        return False

    audio_path = None

    try:
        with playback_lock:

            stop_speaking()

            if not pygame.mixer.get_init():
                initialize_audio_player()

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".mp3"
            )

            audio_path = temp_file.name
            temp_file.close()

            asyncio.run(
                generate_voice(
                    text,
                    audio_path
                )
            )

            pygame.mixer.music.load(
                audio_path
            )

            pygame.mixer.music.play()

            is_speaking = True

            while pygame.mixer.music.get_busy():
                time.sleep(0.05)

            is_speaking = False

            try:
                pygame.mixer.music.unload()
            except Exception:
                pass

            return True

    except Exception as error:
        is_speaking = False
        print("Voice error:", error)

        return False

    finally:
        if audio_path:
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except Exception:
                pass


# =========================================================
# 14. SPEAK IN BACKGROUND
# =========================================================

def speak_async(text):
    """
    Speak without blocking Maya's main controller.
    """

    thread = threading.Thread(
        target=speak,
        args=(text,),
        daemon=True
    )

    thread.start()

    return thread


# =========================================================
# 15. MUTE / UNMUTE
# =========================================================

def mute_voice():
    global voice_muted

    voice_muted = True
    stop_speaking()

    return True


def unmute_voice():
    global voice_muted

    voice_muted = False
    return True


def voice_mute_status():
    return voice_muted


# =========================================================
# 16. CHANGE MAYA VOICE
# =========================================================

def set_voice(voice_name):
    global VOICE_NAME

    if not voice_name:
        return False

    VOICE_NAME = str(
        voice_name
    ).strip()

    return True


def get_voice():
    return VOICE_NAME


# =========================================================
# 17. CHANGE VOICE RATE
# =========================================================

def set_voice_rate(rate):
    """
    Examples:
    +10%
    +20%
    -10%
    """

    global VOICE_RATE

    if not rate:
        return False

    VOICE_RATE = str(rate).strip()

    return True


# =========================================================
# 18. CHANGE VOICE VOLUME
# =========================================================

def set_voice_volume(volume):
    """
    Examples:
    +10%
    -10%
    -25%
    """

    global VOICE_VOLUME

    if not volume:
        return False

    VOICE_VOLUME = str(
        volume
    ).strip()

    return True


# =========================================================
# 19. CHANGE VOICE PITCH
# =========================================================

def set_voice_pitch(pitch):
    """
    Examples:
    +5Hz
    +10Hz
    -5Hz
    """

    global VOICE_PITCH

    if not pitch:
        return False

    VOICE_PITCH = str(
        pitch
    ).strip()

    return True


# =========================================================
# 20. CHANGE WHISPER MODEL
# =========================================================

def set_whisper_model(model_name):
    """
    Examples:
    tiny
    base
    small
    medium
    """

    global WHISPER_MODEL_NAME
    global whisper_model

    if not model_name:
        return False

    WHISPER_MODEL_NAME = str(
        model_name
    ).strip()

    # Reload model next time
    whisper_model = None

    return True


def get_whisper_model():
    return WHISPER_MODEL_NAME


# =========================================================
# 21. WAKE WORD DETECTION
# =========================================================

def wake_word_detected(text):
    """
    Basic text-level wake word detection.

    Actual always-listening wake word engine
    can be added later inside voice.py.
    """

    if not text:
        return False

    text = str(text).lower().strip()

    wake_words = [
        "maya",
        "hey maya",
        "hello maya",
        "hi maya"
    ]

    return any(
        wake_word in text
        for wake_word in wake_words
    )


# =========================================================
# 22. REMOVE WAKE WORD
# =========================================================

def remove_wake_word(text):
    """
    Example:
    'Hey Maya open Chrome'
    becomes
    'open Chrome'
    """

    if not text:
        return ""

    cleaned_text = str(text).strip()

    wake_words = [
        "hey maya",
        "hello maya",
        "hi maya",
        "maya"
    ]

    lower_text = cleaned_text.lower()

    for wake_word in wake_words:

        if lower_text.startswith(wake_word):

            cleaned_text = cleaned_text[
                len(wake_word):
            ].strip()

            break

    return cleaned_text


# =========================================================
# 23. VOICE STATUS
# =========================================================

def voice_status():
    return {
        "microphone_enabled": mic_enabled,
        "muted": voice_muted,
        "speaking": is_speaking,

        "voice": VOICE_NAME,
        "rate": VOICE_RATE,
        "volume": VOICE_VOLUME,
        "pitch": VOICE_PITCH,

        "whisper_model": WHISPER_MODEL_NAME,
        "whisper_device": WHISPER_DEVICE,

        "sample_rate": SAMPLE_RATE,

        "smart_listening": True,
        "vad_threshold": VAD_THRESHOLD,
        "vad_min_silence_ms": VAD_MIN_SILENCE_MS
    }
