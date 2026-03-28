# Все зависимости только в образе (yt-dlp — для «Получить форматы»).
FROM python:3.11-slim-bookworm

# yt-dlp только из pip (requirements.txt) — та же ветка, что во flask; пакет Debian сильно отстаёт и даёт чужие format_id.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
