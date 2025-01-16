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

ENV PYTHONPATH=/app

# Let's specify the port if Gradio is used
EXPOSE 7860

CMD ["python", "project_name/main.py"]
