from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os
import uuid
import whisper as ai_whisper
from argostranslate import package, translate
import gtts as gTTS
import ffmpeg
import logging
import json
import wave
import vosk
from pydub import AudioSegment

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

def sanitize_filename(filename):
    """Заменяет пробелы на подчёркивания."""
    return filename.replace(" ", "_")

def generate_unique_temp_filename(ext):
    """Генерирует уникальное имя временного файла с заданным расширением."""
    return f"/tmp/temp{ext}_{uuid.uuid4()}{ext}"

def recognize_audio_vosk(audio_path, model_path="/path/to/vosk-model-small-en-us-0.22"):
    # Открываем аудиофайл
    wf = wave.open(audio_path, "rb")
    # Создаем объект VoskRecognizer
    model = vosk.Model(model_path)
    rec = vosk.KaldiRecognizer(model, wf.getframerate())
    # Инициализируем список для хранения текста и времени
    results = []

    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            if result.get("text"):
                results.append(result)

    # Получаем итоговый результат
    final_result = json.loads(rec.FinalResult())
    if final_result.get("text"):
        results.append(final_result)

    return results

def add_pause_markers(transcribed_results):
    translated_text_with_pauses = []
    for i, result in enumerate(transcribed_results):
        translated_text_with_pauses.append(result["text"])
        if i < len(transcribed_results) - 1:
            duration = transcribed_results[i+1]["start"] - result["end"]
            pause_duration_ms = int(duration * 1000)  # В миллисекундах
            translated_text_with_pauses.append(f"[pause:{pause_duration_ms}]")

    return " ".join(translated_text_with_pauses)

def generate_translated_audio_with_pauses(translated_text_with_pauses, target_lang):
    segments = []
    for segment in translated_text_with_pauses.split("[pause:"):
        if "]" in segment:
            text_part, pause_part = segment.split("]", 1)
            pause_duration_ms = int(pause_part.strip())

            # Генерируем аудио для текстовой части
            tts = gTTS.gTTS(text=text_part.strip(), lang=target_lang)
            tts.save("/tmp/tts_part.mp3")
            tts_audio = AudioSegment.from_mp3("/tmp/tts_part.mp3")
            segments.append(tts_audio)

            # Добавляем паузу
            silence = AudioSegment.silent(duration=pause_duration_ms)
            segments.append(silence)
        else:
            # Последний элемент может быть только текстом
            tts = gTTS.gTTS(text=segment.strip(), lang=target_lang)
            tts.save("/tmp/tts_part.mp3")
            tts_audio = AudioSegment.from_mp3("/tmp/tts_part.mp3")
            segments.append(tts_audio)

    # Объединяем все части
    combined_audio = sum(segments)
    translated_audio_path = "/tmp/translated_audio.opus"
    combined_audio.export(translated_audio_path, format="opus")
    return translated_audio_path

@app.route("/")
def home():
    logger.info("Запрос к домашней странице")
    return jsonify({"message": "Flask server is running!"})

@app.route("/languages", methods=["GET"])
def get_languages():
    logger.info("Запрос к списку языков")
    return jsonify(LANGUAGES)

@app.route("/download", methods=["POST"])
def download_video():
    data = request.json
    url = data.get("url")
    quality = data.get("quality")
    media_type = data.get("media_type")
    target_lang = data.get("target_lang")
    logger.info("Язык перевода: %s", target_lang)
    # Проверка входных данных
    if not all([url, quality, media_type]):
        logger.error("Не все входные данные указаны")
        return jsonify({"error": "URL, качество и тип медиа должны быть указаны"}), 400

    try:
        # Загрузка видео или аудио
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
        with YoutubeDL(options) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info_dict)
            # Логирование полного пути к скачанному файлу
            full_filename = os.path.join(DOWNLOAD_FOLDER, filename)
            logger.info("Скачанный файл: %s", full_filename)
            # Проверка существования скачанного файла
            if not os.path.exists(full_filename):
                logger.error("Скачанный файл не найден: %s", full_filename)
                return jsonify({"error": "Скачанный файл не найден"}), 500

            # Генерация уникального имени файла с заменой пробелов
            unique_id = str(uuid.uuid4())[:3]
            base, ext = os.path.splitext(filename)
            new_filename = sanitize_filename(f"{base}_{unique_id}{ext}")
            new_full_filename = os.path.join(DOWNLOAD_FOLDER, new_filename)
            os.rename(full_filename, new_full_filename)
            logger.info("Загрузка завершена: %s", new_full_filename)

            # Обработка аудио
            translated_audio = process_audio(new_full_filename, target_lang)
            if not translated_audio:
                return jsonify({"error": "Ошибка обработки аудио"}), 500

            # Если это аудио, возвращаем результат
            if media_type == "audio":
                return jsonify({"filename": os.path.basename(translated_audio)})

            # Объединение видео и аудио
            final_video = merge_audio_with_video(new_full_filename, translated_audio)
            if not final_video:
                return jsonify({"error": "Ошибка объединения видео и аудио"}), 500
            return jsonify({"filename": os.path.basename(final_video)})
    except Exception as e:
        logger.exception("Ошибка загрузки видео: %s", str(e))
        return jsonify({"error": str(e)}), 500

def process_audio(audio_path, target_lang):
    logger.info("Начинается обработка аудио: %s", audio_path)
    try:
        # Нормализация пути к аудиофайлу
        full_audio_path = os.path.normpath(os.path.abspath(audio_path))
        logger.info("Полный путь к аудиофайлу: %s", full_audio_path)
        # Проверка существования аудиофайла
        if not os.path.exists(full_audio_path):
            logger.error("Аудиофайл не найден: %s", full_audio_path)
            return None

        # Конвертация в WAV (если нужно)
        audio_ext = os.path.splitext(full_audio_path)[1]
        if audio_ext != ".wav":
            converted_audio_path = full_audio_path.replace(audio_ext, ".wav")
            logger.info("Конвертация в WAV: %s -> %s", full_audio_path, converted_audio_path)
            ffmpeg.input(full_audio_path).output(converted_audio_path, format="wav").overwrite_output().run()
            full_audio_path = converted_audio_path
            logger.info("Конвертированный аудиофайл: %s", full_audio_path)

        # Проверка существования конвертированного аудиофайла
        if not os.path.exists(full_audio_path):
            logger.error("Конвертированный аудиофайл не найден: %s", full_audio_path)
            return None

        # Распознавание текста с помощью Vosk
        transcribed_results = recognize_audio_vosk(full_audio_path)
        transcript = " ".join([result["text"] for result in transcribed_results])
        logger.info("Распознанный текст (первые 100 символов): %s", transcript[:100])

        logger.info("Начинаю перевод с en на %s", target_lang)
        try:
            # Перевод текста
            translated_text = translate.translate(transcript, "en", target_lang)
            if not translated_text:
                raise ValueError("Ошибка: переводчик для указанного языка не найден")
            logger.info("Переведенный текст (первые 100 символов): %s", translated_text[:100])
        except Exception as e:
            logger.error("Ошибка перевода текста: %s", str(e))
            return None

        # Добавляем паузы в текст
        translated_text_with_pauses = add_pause_markers(transcribed_results)

        # Генерация аудио с помощью gTTS с учетом пауз
        translated_audio_path = generate_translated_audio_with_pauses(translated_text_with_pauses, target_lang)
        logger.info("Аудио перевода сохранено: %s", translated_audio_path)

        # Проверка существования переведённого аудиофайла
        if not os.path.exists(translated_audio_path):
            logger.error("Переведённый аудиофайл не найден: %s", translated_audio_path)
            return None

        # Преобразование переведённого аудио в формат libopus
        temp_audio_path = generate_unique_temp_filename(".opus")
        logger.info("Преобразование аудио в libopus: %s -> %s", translated_audio_path, temp_audio_path)
        try:
            ffmpeg.input(translated_audio_path).output(temp_audio_path, acodec="libopus").overwrite_output().run()
        except ffmpeg.Error as e:
            logger.error("FFmpeg ошибка при преобразовании аудио: %s", e.stderr.decode('utf-8') if e.stderr else "Неизвестная ошибка")
            return None

        # Проверка существования временного аудиофайла
        if not os.path.exists(temp_audio_path):
            logger.error("Временный аудиофайл не найден: %s", temp_audio_path)
            return None
        logger.info("Временный аудиофайл создан: %s", temp_audio_path)
        return temp_audio_path
    except Exception as e:
        logger.exception("Ошибка в process_audio: %s", str(e))
        return None

def merge_audio_with_video(video_path, audio_path):
    logger.info("Начинается объединение аудио с видео: %s + %s", video_path, audio_path)
    try:
        # Нормализация путей к файлам
        full_video_path = os.path.normpath(os.path.abspath(video_path))
        full_audio_path = os.path.normpath(os.path.abspath(audio_path))
        logger.info("Полный путь к видео: %s", full_video_path)
        logger.info("Полный путь к аудио: %s", full_audio_path)
        # Проверка существования видеофайла
        if not os.path.exists(full_video_path):
            logger.error("Видео файл не найден: %s", full_video_path)
            return None
        # Проверка существования аудиофайла
        if not os.path.exists(full_audio_path):
            logger.error("Аудио файл не найден: %s", full_audio_path)
            return None
        # Определение формата выходного файла
        video_ext = os.path.splitext(full_video_path)[1]
        output_path = full_video_path.replace(video_ext, "_translated.webm")
        logger.info("Файл результата: %s", output_path)
        # Удаление существующего файла результата
        if os.path.exists(output_path):
            os.remove(output_path)
            logger.info("Оригинальное видео удалено: %s", output_path)
        # Создание уникального временного файла для перекодированного видео
        temp_video_path = generate_unique_temp_filename(".webm")
        logger.info("Перекодировка видео в VP9: %s -> %s", full_video_path, temp_video_path)
        # Перекодировка видео в VP9 без аудио
        try:
            ffmpeg.input(full_video_path, format="matroska").output(
                temp_video_path,
                vcodec="libvpx-vp9",
                crf=30,
                b="1M",
                an=None  # Отключаем аудио
            ).overwrite_output().run()
        except ffmpeg.Error as e:
            logger.error("FFmpeg ошибка при перекодировке видео: %s", e.stderr.decode('utf-8') if e.stderr else "Неизвестная ошибка")
            return None
        # Проверка существования временного видеофайла
        if not os.path.exists(temp_video_path):
            logger.error("Временный видеофайл не найден: %s", temp_video_path)
            return None
        logger.info("Временный видеофайл создан: %s", temp_video_path)
        # Загружаем перекодированное видео
        video = ffmpeg.input(temp_video_path)
        # Загружаем аудио
        audio = ffmpeg.input(full_audio_path)
        # Объединяем видео и аудио, передавая потоки в output
        ffmpeg_output = ffmpeg.output(video, audio, output_path, vcodec="copy", acodec="libopus")
        logger.info("Объединяем видео и аудио: %s + %s -> %s", temp_video_path, full_audio_path, output_path)
        try:
            ffmpeg_output.overwrite_output().run()
        except ffmpeg.Error as e:
            logger.error("FFmpeg ошибка при объединении: %s", e.stderr.decode('utf-8') if e.stderr else "Неизвестная ошибка")
            return None
        # Проверка существования файла результата
        if not os.path.exists(output_path):
            logger.error("Файл результата не найден: %s", output_path)
            return None
        logger.info("Файл результата создан: %s", output_path)
        # Удаление временных файлов
        os.remove(temp_video_path)
        logger.info("Временный видеофайл удалён: %s", temp_video_path)
        return output_path
    except Exception as e:
        logger.exception("Ошибка в merge_audio_with_video: %s", str(e))
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)