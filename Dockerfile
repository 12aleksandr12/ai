FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    tree \
    yt-dlp \
    ffmpeg \
    gcc \
    g++ \
    make \
    libespeak-ng1 \
    liblapack-dev \
    libatlas-base-dev \
    gfortran \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

#RUN tree -a -I ".gigaide|.git|.idea|.DS_Store|__pycache__|venv|project-structure.txt" > project-structure.txt
RUN tree -a -I ".gigaide|.git|.idea|.DS_Store|__pycache__|venv|project-structure.txt" | sed 's/\xC2\xA0/ /g' > project-structure.txt
#yt-dlp -F https://www.youtube.com/watch?v=VIDEO_ID
#yt-dlp -f best "link to video"
#ffmpeg -i "video name" -i "audoi name" -c:v copy -c:a copy "new name file.mp4"

ENV PYTHONPATH=/app

# Let's specify the port if Gradio is used
EXPOSE 7860

CMD ["python", "project_name/main.py"]
