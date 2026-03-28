# flask_app/Dockerfile — bookworm: более новый FFmpeg, меньше сбоев при merge DASH (video+audio).
FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY install_argos_models.py .
RUN python install_argos_models.py

COPY . .

ENV FLASK_APP=app.py

CMD ["flask", "run", "--host=0.0.0.0", "--port=5001"]
