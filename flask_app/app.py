from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os
import uuid

app = Flask(__name__)

# Путь к папке Downloads внутри контейнера
DOWNLOAD_FOLDER = "/app/downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return jsonify({"message": "Flask server is running!"})

@app.route("/download", methods=["POST"])
def download_video():
    data = request.json
    url = data.get("url")
    quality = data.get("quality")
    media_type = data.get("media_type")  # Добавлено поле для типа контента (видео или аудио)

    if not url or not quality or not media_type:
        return jsonify({"error": "URL, качество и тип медиа должны быть указаны"}), 400

    # Убираем ненужные части формата
    quality = quality.split(" - ")[0]

    if media_type == "audio":
        options = {
            'outtmpl': f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
            'format': 'bestaudio',  # Скачиваем только аудио
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'aac',
                    'preferredquality': '192',
                }
            ]
        }
    else:  # Если media_type == "video"
        options = {
            'outtmpl': f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
            'format': f"{quality}+bestaudio",  # Скачиваем видео и аудио
            'merge_output_format': 'mp4',
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }
            ]
        }

    with YoutubeDL(options) as ydl:
        try:
            info_dict = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info_dict).replace('.webm', '.mp4').replace('.mkv', '.mp4')

            # Генерация уникального идентификатора из первых 3 символов UUID
            unique_id = str(uuid.uuid4())[:3]  # Берем только первые 3 символа UUID
            # Создание нового имени файла с уникальным идентификатором
            base, ext = os.path.splitext(filename)
            new_filename = f"{base}_{unique_id}{ext}"

            # Переименовываем файл
            os.rename(os.path.join(DOWNLOAD_FOLDER, filename), os.path.join(DOWNLOAD_FOLDER, new_filename))

            # Убираем путь из имени файла и выводим только имя файла
            filename_without_path = os.path.basename(new_filename)

            app.logger.info(f"Скачивание файла завершено: {filename_without_path}")
            return jsonify({"filename": filename_without_path})
        except Exception as e:
            app.logger.error(f"Ошибка при скачивании: {str(e)}")
            return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
