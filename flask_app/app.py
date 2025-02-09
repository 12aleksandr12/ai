from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os
import uuid
import whisper as ai_whisper
from argostranslate import package, translate
import gtts as gTTS
import ffmpeg
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_FOLDER = "/app/downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

whisper_model = ai_whisper.load_model("small", device="cpu")

LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ru": "Russian"
}

@app.route("/")
def home():
    return jsonify({"message": "Flask server is running!"})

@app.route("/languages", methods=["GET"])
def get_languages():
    return jsonify(LANGUAGES)

@app.route("/download", methods=["POST"])
def download_video():
    data = request.json
    url = data.get("url")
    quality = data.get("quality")
    media_type = data.get("media_type")
    target_lang = data.get("target_lang")

    logger.info("Язык перевода: %s", target_lang)

    if not url or not quality or not media_type:
        return jsonify({"error": "URL, качество, тип медиа должны быть указаны"}), 400

    logger.info("Начинается загрузка видео: %s", url)

    quality = quality.split(" - ")[0]
    options = {
        'outtmpl': f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
        'format': 'bestaudio' if media_type == "audio" else f"{quality}+bestaudio",
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'aac',
            'preferredquality': '192'
        }] if media_type == "audio" else []
    }

    try:
        with YoutubeDL(options) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info_dict)

        unique_id = str(uuid.uuid4())[:3]
        base, ext = os.path.splitext(filename)
        new_filename = f"{base}_{unique_id}{ext}"
        os.rename(filename, new_filename)

        logger.info("Загрузка завершена: %s", new_filename)

        translated_audio = process_audio(new_filename, target_lang)
        if not translated_audio:
            return jsonify({"error": "Ошибка обработки аудио"}), 500

        if media_type == "audio":
            return jsonify({"filename": os.path.basename(translated_audio)})

        final_video = merge_audio_with_video(new_filename, translated_audio)
        if not final_video:
            return jsonify({"error": "Ошибка объединения видео и аудио"}), 500

        return jsonify({"filename": os.path.basename(final_video)})
    except Exception as e:
        logger.exception("Ошибка загрузки видео: %s", str(e))
        return jsonify({"error": str(e)}), 400

def process_audio(audio_path, target_lang):
    logger.info("Начинается обработка аудио: %s", audio_path)
    try:
        audio_ext = os.path.splitext(audio_path)[1]
        if audio_ext != ".wav":
            converted_audio_path = audio_path.replace(audio_ext, ".wav")
            logger.info("Конвертация в WAV: %s -> %s", audio_path, converted_audio_path)
            ffmpeg.input(audio_path).output(converted_audio_path, format="wav").run()
            audio_path = converted_audio_path

        transcript = whisper_model.transcribe(audio_path)["text"]
        logger.info("Распознанный текст (первые 100 символов): %s", transcript[:100])

        logger.info("Начинаю перевод с en на %s", target_lang)
        try:
            translated_text = translate.translate(transcript, "en", target_lang)
            if not translated_text:
                raise ValueError("Ошибка: переводчик для указанного языка не найден")
            logger.info("Переведенный текст (первые 100 символов): %s", translated_text[:100])
        except Exception as e:
            logger.error("Ошибка перевода текста: %s", str(e))
            return None

        translated_audio_path = audio_path.replace(".wav", "_translated.wav")
        logger.info("Генерация аудио: %s", translated_audio_path)
        tts = gTTS.gTTS(translated_text, lang=target_lang)
        tts.save(translated_audio_path)

        logger.info("Аудио перевода сохранено: %s", translated_audio_path)
        return translated_audio_path
    except Exception as e:
        logger.exception("Ошибка в process_audio: %s", str(e))
        return None

def merge_audio_with_video(video_path, audio_path):
    logger.info("Начинается объединение аудио с видео: %s + %s", video_path, audio_path)
    try:
        output_path = video_path.replace(".webm", "_translated.webm")
        logger.info("Файл результата: %s", output_path)

        if os.path.exists(output_path):
            os.remove(output_path)
            logger.info("Оригинальное аудио удалено: %s", output_path)

        # Преобразование аудио в формат libopus и сохранение во временный файл
        temp_audio_path = "/tmp/temp_audio.opus"
        ffmpeg.input(audio_path).output(temp_audio_path, acodec="libopus").run()

        # Загружаем видео
        video = ffmpeg.input(video_path, format="webm")

        # Объединяем видео и аудио, передавая потоки в output
        audio = ffmpeg.input(temp_audio_path)
        ffmpeg.output(video, audio, output_path, vcodec="copy", acodec="libopus").overwrite_output().run()

        # Удаляем временный файл
        os.remove(temp_audio_path)

        logger.info("Видео с замененным аудио сохранено: %s", output_path)

        return output_path
    except Exception as e:
        logger.exception("Ошибка в merge_audio_with_video: %s", str(e))
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
