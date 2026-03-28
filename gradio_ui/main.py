import json
import os
import subprocess

import gradio as gr
import requests

# URL задаётся в docker-compose (FLASK_API_URL); на машине без compose — значение по умолчанию.
FLASK_SERVER_URL = os.environ.get("FLASK_API_URL", "http://flask:5001").rstrip("/")

# Совпадает с flask_app/app.py LANGUAGES; используется, если /languages недоступен при старте Gradio.
DEFAULT_LANGUAGES = {
    "none": "Без перевода",
    "ru": "Русский",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}
# Порядок пунктов в выпадающем списке
LANGUAGE_KEYS_ORDER = ["none", "ru", "en", "es", "fr", "de"]
DEFAULT_TARGET_LANG = "ru"


def _safe_response_json(response):
    """Flask/прокси иногда отдают пустое тело или HTML — без этого падает response.json()."""
    try:
        return response.json()
    except ValueError:
        text = (response.text or "").strip()
        if text:
            return {"error": text[:800]}
        return {"error": f"Пустой ответ (HTTP {response.status_code}), ожидался JSON"}


def fetch_languages():
    """Объединяет ответ Flask с локальным словарём — список никогда не схлопывается до одного none."""
    merged = dict(DEFAULT_LANGUAGES)
    try:
        response = requests.get(f"{FLASK_SERVER_URL}/languages", timeout=15)
        if response.status_code != 200:
            return merged
        data = _safe_response_json(response)
        if isinstance(data, dict) and "error" not in data:
            for k, v in data.items():
                if k and isinstance(v, str):
                    merged[k] = v
    except requests.RequestException:
        pass
    return merged


languages = fetch_languages()


def language_dropdown_choices():
    return [(k, languages[k]) for k in LANGUAGE_KEYS_ORDER if k in languages]


def language_dropdown_default():
    return DEFAULT_TARGET_LANG if DEFAULT_TARGET_LANG in languages else "none"

def get_video_formats(url):
    """Список форматов из JSON yt-dlp (таблица -F зависит от локали/версии и ломала regex)."""
    u = (url or "").strip()
    if not u:
        return []

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-J",
                "--skip-download",
                "--no-warnings",
                "--no-playlist",
                u,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        info = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return ["Ошибка: таймаут yt-dlp"]
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip() or str(e)
        return [f"Ошибка yt-dlp: {err[:300]}"]
    except json.JSONDecodeError as e:
        return [f"Ошибка разбора ответа: {e}"]
    except Exception as e:
        return [f"Ошибка: {str(e)}"]

    raw = info.get("formats") or []
    video_rows: list[tuple[int, int, str]] = []
    audio_labels: list[str] = []

    for f in raw:
        fid = str(f.get("format_id") or "")
        if not fid or "+" in fid:
            continue
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        ext = f.get("ext") or "?"

        if vcodec != "none":
            w = int(f.get("width") or 0)
            h = int(f.get("height") or 0)
            fps = f.get("fps")
            res = f"{w}x{h}" if w and h else (f.get("resolution") or "?")
            fps_s = f" {fps:g}fps" if fps else ""
            label = f"{fid} - {res}{fps_s} ({ext})"
            video_rows.append((h, w, label))
        elif acodec != "none":
            abr = f.get("abr") or f.get("tbr")
            abr_s = f" ~{int(abr)} kb/s" if abr else ""
            audio_labels.append(f"{fid} - только аудио{abr_s} ({ext})")

    video_rows.sort(key=lambda t: (-t[0], -t[1]))
    out = [row[2] for row in video_rows]
    out.extend(audio_labels[:20])
    if not out:
        return ["Нет доступных форматов"]
    return out


def _is_format_error_message(s: str) -> bool:
    return bool(
        s.startswith("Ошибка")
        or s.startswith("Нет доступных")
    )


def update_quality_and_button(url):
    """Обновляет список качества и сразу кнопку «Скачать» (programmatic value не всегда дергает .change)."""
    formats = get_video_formats(url)
    if isinstance(formats, list) and formats and isinstance(formats[0], list):
        formats = formats[0]

    if not formats:
        return gr.update(choices=[], value=None), gr.update(
            interactive=False, visible=False
        )

    first = formats[0]
    if _is_format_error_message(first):
        return gr.update(choices=formats, value=None), gr.update(
            interactive=False, visible=False
        )

    # По умолчанию — лучшее видео (первое после сортировки по высоте)
    default_val = formats[0]
    return gr.update(choices=formats, value=default_val), gr.update(
        interactive=True, visible=True
    )


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

        # Добавляем выбор языка перевода
        target_lang_input = gr.Dropdown(
            choices=language_dropdown_choices(),
            label="Выберите язык перевода",
            value=language_dropdown_default(),
            allow_custom_value=True,
        )

        # Кнопка скачивания (изначально скрыта)
        download_button = gr.Button("Скачать", interactive=False, visible=False)

        # Поле вывода статуса загрузки
        output_text = gr.Textbox(label="Статус")

        get_formats_button.click(
            fn=update_quality_and_button,
            inputs=[url_input],
            outputs=[quality_input, download_button],
            show_progress="full",
        )

        def enable_download_button(url, quality):
            if url and quality:
                return gr.update(interactive=True, visible=True)
            return gr.update(interactive=False, visible=False)

        url_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])
        quality_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])

        # Обработчик для скачивания видео
        download_button.click(
            fn=lambda url, quality, target_lang: download_video(url, quality, target_lang),
            inputs=[url_input, quality_input, target_lang_input],
            outputs=[output_text]
        )

    return download_section

def clean_quality_string(quality):
    quality_id = (quality or "").split(" - ")[0].strip()
    qlow = (quality or "").lower()
    media_type = (
        "audio"
        if "audio only" in qlow
        or "только аудио" in qlow
        or "audio" in qlow
        else "video"
    )
    return quality_id, media_type

# Функция для скачивания видео
def download_video(url, quality, target_lang):
    try:
        if not quality or _is_format_error_message(str(quality)):
            return "Сначала нажмите «Получить форматы» и выберите строку качества."
        quality_id, media_type = clean_quality_string(quality)
        lang = (
            "none"
            if target_lang in (None, "none", "Без перевода", "Без перевода (только скачать)")
            else target_lang
        )
        response = requests.post(
            f"{FLASK_SERVER_URL}/download",
            json={"url": url, "quality": quality_id, "media_type": media_type, "target_lang": lang},
            timeout=3600
        )
        data = _safe_response_json(response)
        if response.status_code == 200:
            fn = data.get("filename")
            if fn:
                return f"Скачивание завершено: {fn}"
            return f"Ошибка: сервер вернул 200 без JSON-файла: {data.get('error', data)}"
        return f"Ошибка при скачивании: {data.get('error', 'Неизвестная ошибка')}"
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

        # Добавляем выбор языка перевода
        target_lang_input = gr.Dropdown(
            choices=language_dropdown_choices(),
            label="Выберите язык перевода",
            value=language_dropdown_default(),
            allow_custom_value=True,
        )

        download_button = gr.Button("Скачать", interactive=False, visible=False)
        output_text = gr.Textbox(label="Статус")

        get_formats_button.click(
            fn=update_quality_and_button,
            inputs=[url_input],
            outputs=[quality_input, download_button],
            show_progress="full",
        )

        def enable_download_button(url, quality):
            if url and quality:
                return gr.update(interactive=True, visible=True)
            return gr.update(interactive=False, visible=False)

        url_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])
        quality_input.change(enable_download_button, inputs=[url_input, quality_input], outputs=[download_button])

        download_button.click(
            fn=lambda url, quality, target_lang: download_video(url, quality, target_lang),
            inputs=[url_input, quality_input, target_lang_input],
            outputs=[output_text]
        )

    demo.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
