import gradio as gr
import requests

FLASK_SERVER_URL = "http://flask_app:5001"

def create_download_interface():
    with gr.Group(visible=False) as download_section:
        gr.Markdown("<h1>Скачать видео</h1>")

        url_input = gr.Textbox(label="Введите URL")
        quality_input = gr.Dropdown(
            choices=["best", "worst", "bestaudio"],
            value="best",
            label="Выберите качество"
        )

        download_button = gr.Button("Скачать")
        output_text = gr.Textbox()

        download_button.click(download_video, inputs=[url_input, quality_input], outputs=[output_text])

    return download_section

def download_video(url, quality):
    response = requests.post(f"{FLASK_SERVER_URL}/download", json={"url": url, "quality": quality})
    if response.status_code == 200:
        return f"Скачивание завершено: {response.json().get('filename')}"
    else:
        return f"Ошибка: {response.json().get('error', 'Неизвестная ошибка')}"

def main():
    with gr.Blocks() as demo:
        gr.Markdown("<h1>Скачать видео</h1>")

        url_input = gr.Textbox(label="Введите URL")
        quality_input = gr.Dropdown(
            choices=["best", "worst", "bestaudio"],
            value="best",
            label="Выберите качество"
        )

        download_button = gr.Button("Скачать")
        output_text = gr.Textbox()

        download_button.click(download_video, inputs=[url_input, quality_input], outputs=[output_text])

    demo.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
