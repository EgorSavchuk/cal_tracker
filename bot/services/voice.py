import io
import tempfile

from aiogram import Bot
from aiogram.types import Voice
from pydub import AudioSegment
import speech_recognition as sr

from loader import log


async def voice_to_text(bot: Bot, voice: Voice) -> str:
    """Download voice message and transcribe to text."""
    # Download OGG file
    file = await bot.get_file(voice.file_id)
    ogg_data = io.BytesIO()
    await bot.download_file(file.file_path, ogg_data)
    ogg_data.seek(0)

    # Convert OGG to WAV
    audio = AudioSegment.from_ogg(ogg_data)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        audio.export(tmp.name, format="wav")
        recognizer = sr.Recognizer()
        with sr.AudioFile(tmp.name) as source:
            audio_data = recognizer.record(source)

    try:
        text = recognizer.recognize_google(audio_data, language="ru-RU")
        log.info(f"Voice transcribed: {text}")
        return text
    except sr.UnknownValueError:
        log.warning("Voice: could not understand audio")
        return ""
    except sr.RequestError as e:
        log.error(f"Voice STT error: {e}")
        return ""
