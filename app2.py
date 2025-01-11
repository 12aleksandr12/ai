import gradio as gr
import requests
import json

# Функция для отправки запроса
def query_ollama(prompt, model, chat_history):
    url = "http://host.docker.internal:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt
    }
    try:
        with requests.post(url, json=payload, stream=True) as response:
            response.raise_for_status()
            result = ""
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        result += data.get("response", "")
                    except json.JSONDecodeError:
                        continue
            # Добавляем сообщение в историю
            chat_history.append(("Вы", prompt))
            chat_history.append(("Модель", result))
            return "", chat_history
    except Exception as e:
        chat_history.append(("Ошибка", f"Произошла ошибка: {str(e)}"))
        return "", chat_history

# Фабричная функция для создания приложения
def create_app(models):

    with gr.Blocks(css="/app/chat_styles.css") as demo:
        with gr.Row():
            gr.Markdown("<h1 style='text-align:center;'>ChatGPT Аналог с Gradio</h1>")

        with gr.Row():
            with gr.Column(scale=3):  # История чата занимает 75% ширины
                chat_history = gr.Chatbot(elem_id="chat-history", label="История")
            with gr.Column(scale=1, min_width=200):  # Сайдбар для выбора модели
                model_dropdown = gr.Dropdown(
                    choices=models,
                    value="qwen2.5-coder:3b",
                    label="Выберите модель"
                )

        with gr.Row():
            with gr.Column(scale=9):  # Поле ввода занимает 90%
                prompt_input = gr.Textbox(
                    placeholder="Введите сообщение...",
                    label="",
                    elem_id="input-box",
                    lines=1
                )
            with gr.Column(scale=1):  # Кнопка занимает 10%
                submit_button = gr.Button("Отправить", elem_id="submit-btn")

        # Привязка функций к элементам
        prompt_input.submit(
            query_ollama,
            inputs=[prompt_input, model_dropdown, chat_history],
            outputs=[prompt_input, chat_history]
        )
        submit_button.click(
            query_ollama,
            inputs=[prompt_input, model_dropdown, chat_history],
            outputs=[prompt_input, chat_history]
        )

    return demo

# Основная функция приложения
def main():
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
