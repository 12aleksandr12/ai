import gradio as gr
import requests
import json

# Функция для отправки запроса на Ollama
def query_ollama(prompt, model, chat_history):
    url = "http://host.docker.internal:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt
    }
    try:
        # Устанавливаем соединение и обрабатываем потоковый ответ
        with requests.post(url, json=payload, stream=True) as response:
            response.raise_for_status()
            result = ""
            for line in response.iter_lines():
                if line:  # Пропускаем пустые строки
                    try:
                        data = json.loads(line)
                        result += data.get("response", "")
                    except json.JSONDecodeError:
                        continue
            # Добавляем в историю
            chat_history.append((prompt, result))
            return "", chat_history
    except Exception as e:
        return f"Ошибка: {str(e)}", chat_history

# Функция для создания Gradio приложения
def create_app(models):

    # Создаём Gradio интерфейс
    with gr.Blocks(css="/app/styles.css") as demo:
        print("CSS applied to Gradio Blocks")
        gr.Markdown("<h1 style='text-align:center;'>Ollama custom</h1>")

        with gr.Row():
            # История чата
            with gr.Column(scale=3):
                chat_history = gr.Chatbot(label="История чата", height=600)
            # Выбор модели (сайдбар)
            with gr.Column(scale=1, min_width=200):  # Сужаем сайдбар
                model_dropdown = gr.Dropdown(
                    choices=models,
                    value="qwen2.5-coder:3b",
                    label="Выберите модель"
                )

        # Поле ввода для текста и кнопка отправки в одной строке
        with gr.Row():
            with gr.Column(scale=99):  # Поле ввода занимает 99%
                prompt_input = gr.Textbox(
                    placeholder="Введите текстовый запрос...",
                    label="Запрос",
                    lines=1,  # Однострочный ввод для отправки при Enter
                    max_lines=1
                )
            with gr.Column(scale=1):  # Кнопка занимает 1%
                submit_button = gr.Button("Отправить", size="small")

        # Связываем элементы интерфейса с функцией
        submit_button.click(  # Обработчик для кнопки отправки
            query_ollama,
            inputs=[prompt_input, model_dropdown, chat_history],
            outputs=[prompt_input, chat_history]
        )
        prompt_input.submit(  # Обработчик для Enter
            query_ollama,
            inputs=[prompt_input, model_dropdown, chat_history],
            outputs=[prompt_input, chat_history]
        )

    return demo

# Основная функция для локального запуска
def main():
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
