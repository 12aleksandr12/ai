FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    tree \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

#RUN tree -a -I ".gigaide|.git|.idea|.DS_Store|__pycache__|venv|project-structure.txt" > project-structure.txt
RUN tree -a -I ".gigaide|.git|.idea|.DS_Store|__pycache__|venv|project-structure.txt" | sed 's/\xC2\xA0/ /g' > project-structure.txt

ENV PYTHONPATH=/app

# Let's specify the port if Gradio is used
EXPOSE 7860

CMD ["python", "project_name/main.py"]
