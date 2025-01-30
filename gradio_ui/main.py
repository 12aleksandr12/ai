import gradio as gr
import requests

FLASK_SERVER_URL = "http://flask_app:5001"

def fetch_languages():
    response = requests.get(f"{FLASK_SERVER_URL}/languages")
    return response.json() if response.status_code == 200 else {}

# Функция для получения форматов видео через yt-dlp
def get_video_formats(url):
    response = requests.post(f"{FLASK_SERVER_URL}/formats", json={"url": url})
    return response.json().get("formats", [])

def download_video(url, quality, target_lang):
    response = requests.post(
        f"{FLASK_SERVER_URL}/download",
        json={"url": url, "quality": quality, "media_type": "video", "target_lang": target_lang}
    )
    return response.json().get("filename", "Ошибка при скачивании")

def enable_download(url, quality, language):
    return gr.update(interactive=bool(url and quality and language))

languages = fetch_languages()

def gradio_interface():
    with gr.Blocks() as demo:
        gr.Markdown("# Скачать и перевести видео")
        url_input = gr.Textbox(label="Введите URL")
        get_formats_button = gr.Button("Получить форматы")
        quality_input = gr.Dropdown(choices=[], label="Выберите качество")
        language_input = gr.Dropdown(choices=list(languages.keys()), label="Выберите язык перевода")
        download_button = gr.Button("Скачать", interactive=False)
        output_text = gr.Textbox(label="Статус")

        get_formats_button.click(get_video_formats, inputs=[url_input], outputs=[quality_input])
        url_input.change(enable_download, inputs=[url_input, quality_input, language_input], outputs=[download_button])
        quality_input.change(enable_download, inputs=[url_input, quality_input, language_input], outputs=[download_button])
        language_input.change(enable_download, inputs=[url_input, quality_input, language_input], outputs=[download_button])
        download_button.click(download_video, inputs=[url_input, quality_input, language_input], outputs=[output_text])
    demo.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    gradio_interface()
