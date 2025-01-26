import gradio as gr
from project_name import create_ollama_chat, create_gpt_chat, models_app, download_video_audio

def main():
    def switch_interface(interface):
        if interface == "Ollama custom":
            return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
        elif interface == "ChatGPT Аналог с Gradio":
            return gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)
        else:
            return gr.update(visible=False), gr.update(visible=False), gr.update(visible=True)

    with gr.Blocks() as demo:
        gr.Markdown("<h1>Переключение между интерфейсами</h1>")

        interface_selector = gr.Dropdown(
            choices=["Ollama custom", "ChatGPT Аналог с Gradio", "Download Video"],
            value="Ollama custom",
            label="Выберите интерфейс"
        )

        with gr.Group(visible=True) as interface_ollama_chat:
            create_ollama_chat(models_app)

        with gr.Group(visible=False) as interface_gpt_chat:
            create_gpt_chat(models_app)

        interface_download_video_audio = download_video_audio()

        interface_selector.change(
            switch_interface,
            inputs=[interface_selector],
            outputs=[interface_ollama_chat, interface_gpt_chat, interface_download_video_audio]
        )

    demo.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
