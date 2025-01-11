FROM python:3.9-slim

# Установим системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Установим Python-зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Скопируем проект
COPY . .

# Укажем порт, если используется Gradio
EXPOSE 7860

# Запускаем приложение
CMD ["python", "main_app.py"]
