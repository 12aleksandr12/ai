from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os
import uuid
import shutil
import whisper
from argostranslate.translate import translate
from TTS.api import TTS
import ffmpeg

app = Flask(__name__)

# Путь к папке Downloads внутри контейнера
DOWNLOAD_FOLDER = "/app/downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

whisper_model = whisper.load_model("small")
tts_model = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)

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
    media_type = data.get("media_type")  # Добавлено поле для типа контента (видео или аудио)
    target_lang = data.get("target_lang")

    if not url or not quality or not media_type or not target_lang:
        return jsonify({"error": "URL, качество, тип медиа и язык перевода должны быть указаны"}), 400

    # Убираем ненужные части формата
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
        try:
            info_dict = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info_dict)

            unique_id = str(uuid.uuid4())[:3]
            base, ext = os.path.splitext(filename)
            new_filename = f"{base}_{unique_id}{ext}"
            os.rename(filename, new_filename)

            if media_type == "audio":
                translated_audio = process_audio(new_filename, target_lang)
                return jsonify({"filename": os.path.basename(translated_audio)})

            translated_audio = process_audio(new_filename, target_lang)
            final_video = merge_audio_with_video(new_filename, translated_audio)
            return jsonify({"filename": os.path.basename(final_video)})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

def process_audio(audio_path, target_lang):
    transcript = whisper_model.transcribe(audio_path)["text"]
    translated_text = translate(transcript, "en", target_lang)
    translated_audio_path = audio_path.replace(".aac", "_translated.wav")
    tts_model.tts_to_file(text=translated_text, file_path=translated_audio_path)
    return translated_audio_path

def merge_audio_with_video(video_path, audio_path):
    output_path = video_path.replace(".mp4", "_translated.mp4")
    ffmpeg.input(video_path).output(audio_path, codec="aac").run()
    ffmpeg.input(video_path).input(audio_path).output(output_path, vcodec="copy", acodec="aac").run()
    return output_path

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
