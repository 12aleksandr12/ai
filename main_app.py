import gradio as gr
from app import create_app as create_app1
from app2 import create_app as create_app2
from config import models  # Импорт списка моделей

def main():
    # print("Loaded CSS:")
    def switch_interface(interface):
        if interface == "Ollama custom":
            return gr.update(visible=True), gr.update(visible=False)
        else:
            return gr.update(visible=False), gr.update(visible=True)

    with gr.Blocks() as demo:
        gr.Markdown("<h1>Переключение между интерфейсами</h1>")

        interface_selector = gr.Dropdown(
            choices=["Ollama custom", "ChatGPT Аналог с Gradio"],
            value="Ollama custom",
            label="Выберите интерфейс"
        )

        with gr.Group(visible=True) as interface_1_container:
            create_app1(models)  # Передаем список моделей

        with gr.Group(visible=False) as interface_2_container:
            create_app2(models)  # Передаем список моделей

        interface_selector.change(
            switch_interface,
            inputs=[interface_selector],
            outputs=[interface_1_container, interface_2_container]
        )

    demo.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
