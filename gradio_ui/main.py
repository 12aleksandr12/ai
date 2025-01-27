import gradio as gr
import requests
import subprocess
import re

FLASK_SERVER_URL = "http://flask_app:5001"

# Функция для получения форматов видео через yt-dlp
def get_video_formats(url):
    try:
        result = subprocess.run(
            ["yt-dlp", "-F", url],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout

        formats = []
        for line in output.splitlines():
            match = re.match(r"^(\d+)\s+(\w+)\s+([\d+x\d+]+|\b[a-zA-Z]+\b)", line)
            if match:
                format_id, ext, resolution = match.groups()
                formats.append(f"{format_id} - {resolution} ({ext})")

        if not formats:
            return []
        return formats

    except subprocess.CalledProcessError as e:
        return ["Ошибка выполнения yt-dlp"]
    except Exception as e:
        return [f"Ошибка: {str(e)}"]

# Функция создания интерфейса загрузки видео
def create_download_interface():
    with gr.Group(visible=False) as download_section:
        gr.Markdown("<h1>Скачать видео</h1>")

        # Ввод ссылки
        url_input = gr.Textbox(label="Введите URL")

        # Кнопка для получения форматов
        get_formats_button = gr.Button("Получить форматы")

        # Выпадающий список выбора качества (изначально пустой)
        quality_input = gr.Dropdown(choices=[], label="Выберите качество", interactive=True, value=None)

        # Кнопка скачивания (изначально скрыта)
        download_button = gr.Button("Скачать", interactive=False, visible=False)

        # Поле вывода статуса загрузки
        output_text = gr.Textbox(label="Статус")

        # Обработчик получения форматов
        def update_quality_list(url):
            formats = get_video_formats(url)
            if isinstance(formats, list) and len(formats) > 0 and isinstance(formats[0], list):
                return gr.update(choices=formats[0])  # Извлечение вложенного списка
            return gr.update(choices=formats)

        get_formats_button.click(
            fn=update_quality_list,
            inputs=[url_input],
            outputs=[quality_input],
            show_progress="full"
        )

        # Активация кнопки "Скачать" при вводе URL и выборе качества
        def enable_download_button(url, quality):
            if url and quality:
                return gr.update(interactive=True, visible=True)
            return gr.update(interactive=False, visible=False)

        url_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])
        quality_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])

        # Обработчик для скачивания видео
        download_button.click(download_video, inputs=[url_input, quality_input], outputs=[output_text])

    return download_section

def clean_quality_string(quality):
    # Извлекаем ID качества (например, "137" или "22") и разрешение/формат
    quality_id = quality.split(" - ")[0]

    # Пример: можно извлечь тип медиафайла из строки, предполагая что будет что-то вроде "audio" или "video"
    media_type = "audio" if "audio" in quality.lower() else "video"

    return quality_id, media_type

# Функция для скачивания видео
def download_video(url, quality):
    try:
        quality_id, media_type = clean_quality_string(quality)
        response = requests.post(
            f"{FLASK_SERVER_URL}/download",
            json={"url": url, "quality": quality_id, "media_type": media_type},
            timeout=15
        )
        if response.status_code == 200:
            return f"Скачивание завершено: {response.json().get('filename')}"
        else:
            return f"Ошибка при скачивании: {response.json().get('error', 'Неизвестная ошибка')}"
    except requests.ConnectionError:
        return "Ошибка: не удается подключиться к серверу Flask"
    except requests.Timeout:
        return "Ошибка: сервер не отвечает, попробуйте позже"
    except Exception as e:
        return f"Ошибка: {str(e)}"

# Основная функция запуска приложения Gradio
def main():
    with gr.Blocks() as demo:
        gr.Markdown("<h1>Скачать видео</h1>")

        url_input = gr.Textbox(label="Введите URL")
        get_formats_button = gr.Button("Получить форматы")
        quality_input = gr.Dropdown(choices=[], label="Выберите качество", interactive=True, value=None)
        download_button = gr.Button("Скачать", interactive=False, visible=False)
        output_text = gr.Textbox(label="Статус")

        # Обработчик для получения форматов
        get_formats_button.click(
            get_video_formats,
            inputs=[url_input],
            outputs=[quality_input],
            show_progress="full"
        )

        # Логика активации кнопки скачивания
        def enable_download_button(url, quality):
            if url and quality:
                return gr.update(interactive=True, visible=True)
            return gr.update(interactive=False, visible=False)

        url_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])
        quality_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])

        download_button.click(
            fn=lambda url, quality: download_video(url, quality),
            inputs=[url_input, quality_input],
            outputs=[output_text]
        )

    demo.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
