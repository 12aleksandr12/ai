from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os

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

    if not url or not quality:
        return jsonify({"error": "URL и качество должны быть указаны"}), 400

    # Убираем ненужные части формата
    quality = quality.split(" - ")[0]

    options = {
        'outtmpl': f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
        'format': quality,
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
            app.logger.info(f"Скачивание завершено: {filename}")
            return jsonify({"filename": filename})
        except Exception as e:
            app.logger.error(f"Ошибка при скачивании: {str(e)}")
            return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
