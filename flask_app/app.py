from __future__ import annotations

import os


def _configure_cpu_threads() -> None:
    """Whisper/PyTorch иначе забирают все ядра (500%+ в Docker)."""
    raw = os.environ.get("WHISPER_CPU_THREADS", "2")
    try:
        n = max(1, int(raw))
    except ValueError:
        n = 2
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(key, str(n))
    try:
        import torch

        torch.set_num_threads(n)
        torch.set_num_interop_threads(max(1, min(2, n)))
    except Exception:
        pass


_configure_cpu_threads()

import asyncio
import re
from typing import Any, Optional

from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from yt_dlp import YoutubeDL
import uuid
import subprocess
import tempfile
import whisper as ai_whisper  # noqa: E402 — после настройки потоков
from argostranslate import translate
import gtts as gTTS
import ffmpeg
import logging

from pydub import AudioSegment

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_TEMPLATES = os.path.normpath(os.path.join(_BASE_DIR, "..", "templates"))
_TEMPLATE_DIR = _REPO_TEMPLATES if os.path.isdir(_REPO_TEMPLATES) else os.path.join(_BASE_DIR, "templates")
_REPO_STATIC = os.path.normpath(os.path.join(_BASE_DIR, "..", "static"))
_STATIC_DIR = _REPO_STATIC if os.path.isdir(_REPO_STATIC) else os.path.join(_BASE_DIR, "static")

app = Flask(__name__, template_folder=_TEMPLATE_DIR, static_folder=_STATIC_DIR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask 3.1+ / Werkzeug 3.2: Host с подчёркиванием (напр. flask_app:5001) отвергается до TRUSTED_HOSTS — см. compose service name «flask».
_trust_all = os.environ.get("FLASK_TRUST_ALL_HOSTS", "").lower() in ("1", "true", "yes")
_in_docker = os.path.isfile("/.dockerenv")
if _trust_all:
    app.config["TRUSTED_HOSTS"] = None
elif _in_docker or os.environ.get("FLASK_DOCKER_NETWORK", "").lower() in ("1", "true", "yes"):
    _hosts = [
        "127.0.0.1",
        "127.0.0.1:5001",
        "localhost",
        "localhost:5001",
        ".localhost",
        "flask",
        "flask:5001",
        "[::1]",
        "[::1]:5001",
        "host.docker.internal",
        "host.docker.internal:5001",
    ]
    _extra = os.environ.get("FLASK_TRUSTED_HOSTS", "").strip()
    if _extra:
        for h in _extra.split(","):
            h = h.strip()
            if h and h not in _hosts:
                _hosts.append(h)
    app.config["TRUSTED_HOSTS"] = _hosts
else:
    _trusted = os.environ.get("FLASK_TRUSTED_HOSTS", "").strip()
    if _trusted:
        app.config["TRUSTED_HOSTS"] = [h.strip() for h in _trusted.split(",") if h.strip()]

DOWNLOAD_FOLDER = os.environ.get(
    "DOWNLOAD_FOLDER", os.path.join(os.path.dirname(__file__), "downloads")
)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

_whisper_model = None
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        logger.info(
            "Загрузка Whisper «%s» (первый раз может скачать веса; см. WHISPER_MODEL / WHISPER_CPU_THREADS)",
            WHISPER_MODEL_NAME,
        )
        _whisper_model = ai_whisper.load_model(WHISPER_MODEL_NAME, device="cpu")
    return _whisper_model


LANGUAGES = {
    "none": "Без перевода",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ru": "Russian",
}

# gTTS использует те же коды для этих языков; при расширении списка добавьте исключения
GTTS_LANG_MAP = {
    "en": "en",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "ru": "ru",
}

_TTS_VOICE_ID_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}-[A-Za-z0-9._-]+$")


def normalize_tts_voice_id(raw: Optional[str]) -> str:
    v = (raw or "").strip()
    if not v or v.lower() == "gtts":
        return "gtts"
    if not _TTS_VOICE_ID_RE.match(v):
        logger.warning("Недопустимый id голоса TTS, используем Google TTS: %r", raw)
        return "gtts"
    return v


def _edge_voice_label(v: dict[str, Any]) -> str:
    short = str(v.get("ShortName") or "")
    gender = str(v.get("Gender") or "").strip()
    long_name = str(v.get("FriendlyName") or v.get("Name") or "").strip()
    if long_name and len(long_name) < 96:
        return f"{short} — {long_name}"
    bits = [short]
    if gender:
        bits.append(gender)
    return " · ".join(bits)


async def _async_edge_voices_filtered(lang_code: str) -> list[dict[str, Any]]:
    import edge_tts

    lang = (lang_code or "en").lower().strip().split("-")[0][:2]
    if len(lang) < 2:
        lang = "en"
    all_voices = await edge_tts.list_voices()
    out: list[dict[str, Any]] = []
    for v in all_voices:
        loc = str(v.get("Locale") or "")
        primary = loc.split("-")[0].lower() if loc else ""
        if primary != lang:
            continue
        sn = str(v.get("ShortName") or "")
        if not sn:
            continue
        out.append(v)
    out.sort(
        key=lambda x: (
            0 if str(x.get("ShortName", "")).endswith("Neural") else 1,
            str(x.get("ShortName", "")),
        )
    )
    return out


def list_edge_voices_for_lang(lang_code: str) -> list[dict[str, Any]]:
    return asyncio.run(_async_edge_voices_filtered(lang_code))


def normalize_target_lang(raw: Optional[str]) -> str:
    """Gradio иногда шлёт подпись («русский»), а нужен код argos/gTTS («ru»)."""
    if raw is None:
        return "none"
    c = str(raw).strip().lower()
    if not c or c in ("none", "off"):
        return "none"
    aliases = {
        "русский": "ru",
        "ру": "ru",
        "russian": "ru",
        "английский": "en",
        "english": "en",
        "испанский": "es",
        "spanish": "es",
        "французский": "fr",
        "french": "fr",
        "немецкий": "de",
        "german": "de",
    }
    if c in aliases:
        return aliases[c]
    if len(c) == 2 and c.isalpha():
        return c
    return c


def sanitize_filename(filename):
    return filename.replace(" ", "_")


def generate_unique_temp_filename(suffix: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"yt_{uuid.uuid4().hex}{suffix}")


def _unique_format_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = (x or "").strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_ydl_format_attempts(quality: str, media_type: str) -> list[str]:
    """Несколько строк format: если ID из Gradio недоступен на этом ролике — пробуем запасные."""
    q = (quality or "").split(" - ")[0].strip()
    attempts: list[str] = []

    if media_type == "audio":
        attempts.extend(["bestaudio/best", "ba/b", "bestaudio/worst"])
        return _unique_format_list(attempts)

    if q.isdigit():
        attempts.append(f"{q}+bestaudio/best")
        attempts.append(f"{q}+ba/b")
    elif q:
        attempts.append(q)

    attempts.extend(
        [
            "bestvideo*+bestaudio/best",
            "bv*+ba/b",
            "bestvideo+bestaudio/best",
            "bestvideo*+bestaudio/worst",
            "best",
        ]
    )
    return _unique_format_list(attempts)


def extract_youtube_id(url: str) -> Optional[str]:
    m = re.search(
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        url or "",
    )
    return m.group(1) if m else None


def cleanup_incomplete_ytdl_files(folder: str, video_id: Optional[str]) -> None:
    """Удаляет незавершённый merge: *.temp.* и *.fNNN.* для префикса id__ (см. outtmpl)."""
    if not video_id or not os.path.isdir(folder):
        return
    prefix = f"{video_id}__"
    frag = re.compile(r"\.f\d+\.")
    for name in os.listdir(folder):
        if not name.startswith(prefix):
            continue
        if ".temp." in name or frag.search(name):
            path = os.path.join(folder, name)
            try:
                os.remove(path)
                logger.info("Удалён незавершённый фрагмент: %s", name)
            except OSError:
                pass


class _YtdlLogger:
    def debug(self, msg):
        logger.debug("%s", msg)

    def info(self, msg):
        logger.info("%s", msg)

    def warning(self, msg):
        logger.warning("%s", msg)

    def error(self, msg):
        logger.error("%s", msg)


def resolve_downloaded_path(info_dict: dict, ydl: YoutubeDL) -> Optional[str]:
    fp = info_dict.get("filepath") or info_dict.get("_filename")
    if fp and os.path.isfile(fp):
        return os.path.abspath(fp)
    cand = ydl.prepare_filename(info_dict)
    if os.path.isfile(cand):
        return os.path.abspath(cand)
    base = os.path.join(DOWNLOAD_FOLDER, os.path.basename(cand))
    if os.path.isfile(base):
        return base
    return None


def build_atempo_chain(speed_factor: float) -> str:
    """speed_factor > 1 ускоряет воспроизведение (укладываем длинный TTS в меньший интервал)."""
    if speed_factor <= 1.001:
        return "atempo=1.0"
    parts = []
    f = speed_factor
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    parts.append(f"atempo={min(max(f, 0.5), 2.0):.5f}")
    return ",".join(parts)


def fit_audio_to_duration_ms(src_path: str, target_ms: int, out_wav: str) -> None:
    """Подгоняет длительность: ускоряет через atempo или дополняет тишиной."""
    audio = AudioSegment.from_file(src_path)
    if len(audio) <= target_ms:
        padded = audio + AudioSegment.silent(duration=target_ms - len(audio))
        padded.export(out_wav, format="wav")
        return
    factor = len(audio) / target_ms
    chain = build_atempo_chain(factor)
    tmp_sped = out_wav + ".sped.wav"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-filter:a",
                chain,
                "-t",
                f"{target_ms / 1000.0:.6f}",
                tmp_sped,
            ],
            check=True,
            capture_output=True,
        )
        out = AudioSegment.from_file(tmp_sped)
        if len(out) > target_ms:
            out = out[:target_ms]
        elif len(out) < target_ms:
            out = out + AudioSegment.silent(duration=target_ms - len(out))
        out.export(out_wav, format="wav")
    finally:
        if os.path.isfile(tmp_sped):
            os.remove(tmp_sped)


def extract_original_slice(audio_path: str, start_s: float, end_s: float) -> AudioSegment:
    duration_s = max(0.001, end_s - start_s)
    tmp = generate_unique_temp_filename(".wav")
    try:
        (
            ffmpeg.input(audio_path, ss=start_s, t=duration_s)
            .output(tmp, acodec="pcm_s16le", ar=44100, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
        seg = AudioSegment.from_wav(tmp)
        return seg
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


def _norm_lang_code(code: Optional[str], default: str = "en") -> str:
    c = (code or default).strip().lower()
    if "-" in c:
        c = c.split("-", 1)[0]
    return c[:2] if len(c) >= 2 else default


def _try_argos_translate(text: str, from_code: str, to_code: str) -> Optional[str]:
    """Один шаг Argos; при отсутствии пары — None (без исключений)."""
    if from_code == to_code:
        return text
    try:
        tr = translate.get_translation_from_codes(from_code, to_code)
        return tr.translate(text)
    except Exception:
        return None


def translate_segment(text: str, from_code: str, to_code: str) -> Optional[str]:
    """
    Перевод сегмента. Прямой пакет или цепочка через английский (например es→en→ru).
    Пустая строка — допустимый результат для пустого входа.
    None — перевод невозможен (нет моделей); нельзя подставлять оригинал под русскую озвучку.
    """
    text = (text or "").strip()
    if not text:
        return ""
    fc = _norm_lang_code(from_code, "en")
    tc = _norm_lang_code(to_code, "en")
    if fc == tc:
        return text

    direct = _try_argos_translate(text, fc, tc)
    if direct is not None:
        return direct

    if fc != "en":
        mid = _try_argos_translate(text, fc, "en")
        if mid is None:
            logger.warning("Нет пакета перевода %s→en (или en→%s) для Argos", fc, tc)
            return None
        if tc == "en":
            return mid
        second = _try_argos_translate(mid, "en", tc)
        if second is None:
            logger.warning("Цепочка %s→en окончена, но en→%s недоступна", fc, tc)
        return second

    logger.warning("Нет прямого пакета Argos en→%s", tc)
    return None


def tts_to_wav(text: str, gtts_lang: str, out_wav: str, tts_voice_id: str = "gtts") -> None:
    vid = normalize_tts_voice_id(tts_voice_id)
    if vid != "gtts":
        tmp_edge = generate_unique_temp_filename(".mp3")
        try:
            import edge_tts

            async def _edge_save() -> None:
                await edge_tts.Communicate(text, vid).save(tmp_edge)

            asyncio.run(_edge_save())
            AudioSegment.from_mp3(tmp_edge).export(out_wav, format="wav")
            return
        except Exception as e:
            logger.warning("Edge TTS (%s) недоступен, fallback Google TTS: %s", vid, e)
        finally:
            if os.path.isfile(tmp_edge):
                os.remove(tmp_edge)

    tts = gTTS.gTTS(text=text, lang=gtts_lang)
    tmp_mp3 = generate_unique_temp_filename(".mp3")
    try:
        tts.save(tmp_mp3)
        AudioSegment.from_mp3(tmp_mp3).export(out_wav, format="wav")
    finally:
        if os.path.isfile(tmp_mp3):
            os.remove(tmp_mp3)


def build_timeline_audio(
    source_audio_path: str,
    segments: list,
    source_lang: str,
    target_lang: str,
    gtts_lang: str,
    tts_voice_id: str = "gtts",
) -> Optional[str]:
    """Собирает дорожку: паузы как в оригинале, речь в тех же интервалах (по длительности сегмента)."""
    pieces: list[AudioSegment] = []
    t = 0.0
    for seg in segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        text = (seg.get("text") or "").strip()
        text = re.sub(r"\s+", " ", text)

        if start > t:
            gap_ms = int(round((start - t) * 1000))
            if gap_ms > 0:
                pieces.append(AudioSegment.silent(duration=gap_ms))

        dur_ms = max(1, int(round((end - start) * 1000)))

        if not text:
            pieces.append(AudioSegment.silent(duration=dur_ms))
            t = end
            continue

        if source_lang == target_lang:
            chunk = extract_original_slice(source_audio_path, start, end)
        else:
            translated = translate_segment(text, source_lang, target_lang)
            if translated is None:
                logger.error(
                    "Перевод остановлен: сегмент не переведён (%s→%s). Проверьте модели Argos в образе.",
                    source_lang,
                    target_lang,
                )
                return None
            if not translated.strip():
                pieces.append(AudioSegment.silent(duration=dur_ms))
                t = end
                continue
            raw_wav = generate_unique_temp_filename(".wav")
            fitted_wav = generate_unique_temp_filename(".wav")
            try:
                tts_to_wav(translated, gtts_lang, raw_wav, tts_voice_id)
                fit_audio_to_duration_ms(raw_wav, dur_ms, fitted_wav)
                chunk = AudioSegment.from_wav(fitted_wav)
            finally:
                for p in (raw_wav, fitted_wav):
                    if os.path.isfile(p):
                        os.remove(p)

        if len(chunk) != dur_ms:
            if len(chunk) > dur_ms:
                chunk = chunk[:dur_ms]
            else:
                chunk = chunk + AudioSegment.silent(duration=dur_ms - len(chunk))
        pieces.append(chunk)
        t = end

    if not pieces:
        return None
    combined = sum(pieces[1:], pieces[0])
    out_opus = generate_unique_temp_filename(".opus")
    combined.export(out_opus, format="opus")
    return out_opus


def process_audio(
    audio_path: str, target_lang: str, tts_voice_id: str = "gtts"
) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (path_to_opus_or_none, error_key).
    error_key: None при успехе; иначе короткий ключ для ответа API.
    """
    logger.info("Обработка аудио: %s -> %s (голос TTS: %s)", audio_path, target_lang, tts_voice_id)
    try:
        full_audio_path = os.path.normpath(os.path.abspath(audio_path))
        if not os.path.exists(full_audio_path):
            logger.error("Файл не найден: %s", full_audio_path)
            return None, "file_not_found"

        ext = os.path.splitext(full_audio_path)[1].lower()
        if ext != ".wav":
            converted = generate_unique_temp_filename(".wav")
            ffmpeg.input(full_audio_path).output(converted, acodec="pcm_s16le", ar=16000, ac=1).overwrite_output().run(
                quiet=True
            )
            work_wav = converted
        else:
            work_wav = full_audio_path
            converted = None

        try:
            logger.info(
                "Whisper: распознавание речи (долго; UI ждёт один HTTP-запрос — это нормально)"
            )
            result = get_whisper_model().transcribe(
                work_wav, fp16=False, verbose=False, word_timestamps=False
            )
        finally:
            if converted and os.path.isfile(converted):
                os.remove(converted)

        segments = result.get("segments") or []
        source_lang = (result.get("language") or "en").lower()
        gtts_lang = GTTS_LANG_MAP.get(target_lang, target_lang)

        if not segments:
            logger.error("Whisper не вернул сегменты")
            return None, "no_segments"

        timeline = build_timeline_audio(
            full_audio_path,
            segments,
            source_lang,
            target_lang,
            gtts_lang,
            tts_voice_id,
        )
        if not timeline or not os.path.isfile(timeline):
            return None, "translation"
        return timeline, None
    except Exception:
        logger.exception("Ошибка process_audio")
        return None, "exception"


def merge_audio_with_video(video_path: str, audio_path: str) -> Optional[str]:
    logger.info("Склейка видео + переведённое аудио: %s + %s", video_path, audio_path)
    try:
        full_video_path = os.path.abspath(video_path)
        full_audio_path = os.path.abspath(audio_path)
        if not os.path.exists(full_video_path) or not os.path.exists(full_audio_path):
            return None

        video_ext = os.path.splitext(full_video_path)[1]
        output_path = full_video_path.replace(video_ext, "_translated.mkv")

        if os.path.exists(output_path):
            os.remove(output_path)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                full_video_path,
                "-i",
                full_audio_path,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "libopus",
                "-b:a",
                "128k",
                "-shortest",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        if not os.path.isfile(output_path):
            return None
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg merge: %s", e.stderr.decode("utf-8", errors="replace") if e.stderr else e)
        return None
    except Exception:
        logger.exception("Ошибка merge_audio_with_video")
        return None


@app.route("/")
def home():
    return jsonify({"message": "Flask server is running!"})


@app.route("/download-page")
def download_page():
    return render_template("download_video_audio.html")


@app.route("/files/<path:filename>")
def serve_file(filename):
    safe = os.path.basename(filename)
    if not safe or safe != filename.replace("\\", "/").split("/")[-1]:
        abort(400)
    path = os.path.join(DOWNLOAD_FOLDER, safe)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(DOWNLOAD_FOLDER, safe, as_attachment=True)


@app.route("/languages", methods=["GET"])
def get_languages():
    return jsonify(LANGUAGES)


@app.route("/tts-voices", methods=["GET"])
def tts_voices():
    """Список голосов Edge TTS для языка озвучки + вариант Google TTS."""
    lang = (request.args.get("lang") or "ru").strip().lower()
    base = [{"id": "gtts", "label": "Google TTS (стандартный)"}]
    if lang in ("none", "", "off"):
        return jsonify({"voices": base})
    try:
        raw = list_edge_voices_for_lang(lang)
        for v in raw:
            sid = str(v.get("ShortName") or "")
            if not sid:
                continue
            base.append({"id": sid, "label": _edge_voice_label(v)})
    except Exception:
        logger.exception("Не удалось получить список голосов Edge TTS для lang=%s", lang)
    return jsonify({"voices": base})


@app.route("/download", methods=["POST"])
def download_video():
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()
    url = data.get("url")
    quality = data.get("quality")
    media_type = (data.get("media_type") or "video").lower()
    target_lang = normalize_target_lang(data.get("target_lang"))
    tts_voice_raw = data.get("tts_voice")
    tts_voice_id = (
        "gtts"
        if target_lang in ("none", "", "off")
        else normalize_tts_voice_id(str(tts_voice_raw) if tts_voice_raw is not None else "gtts")
    )

    if not url or not quality:
        return jsonify({"error": "Укажите URL и качество / формат"}), 400
    if media_type not in ("audio", "video"):
        media_type = "video"

    format_attempts = build_ydl_format_attempts(quality, media_type)
    logger.info(
        "Загрузка url=%s media=%s translate=%s; цепочка форматов yt-dlp: %s",
        url,
        media_type,
        target_lang,
        format_attempts,
    )

    try:
        video_id = extract_youtube_id(url)
        outtmpl = os.path.join(DOWNLOAD_FOLDER, "%(id)s__%(title)s.%(ext)s")
        merge_variants: list[dict] = (
            [
                {"merge_output_format": "mp4"},
                {"merge_output_format": "mkv"},
                {},
            ]
            if media_type == "video"
            else [{}]
        )

        info_dict = None
        full_path = None
        last_error: Optional[Exception] = None

        for fmt in format_attempts:
            base_options = {
                "outtmpl": outtmpl,
                "format": fmt,
                "restrictfilenames": True,
                "noplaylist": True,
                "retries": 5,
                "fragment_retries": 5,
                "ffmpeg_location": "/usr/bin/ffmpeg",
                "logger": _YtdlLogger(),
                "postprocessors": [],
            }
            if media_type == "audio":
                base_options["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "wav",
                        "preferredquality": "192",
                    }
                ]

            for extra in merge_variants:
                cleanup_incomplete_ytdl_files(DOWNLOAD_FOLDER, video_id)
                opts = {**base_options, **extra}
                try:
                    with YoutubeDL(opts) as ydl:
                        info_dict = ydl.extract_info(url, download=True)
                        full_path = resolve_downloaded_path(info_dict, ydl)
                    if full_path:
                        last_error = None
                        logger.info("yt-dlp ок: format=%s merge=%s", fmt, extra or "по умолчанию")
                        break
                    last_error = RuntimeError("Файл после загрузки не найден")
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "yt-dlp format=%s merge=%s: %s",
                        fmt,
                        extra or "по умолчанию",
                        e,
                    )
            if full_path:
                break

        if not full_path:
            cleanup_incomplete_ytdl_files(DOWNLOAD_FOLDER, video_id)
            if last_error is not None:
                raise last_error
            return jsonify({"error": "Не удалось определить путь к скачанному файлу"}), 500

        unique_id = str(uuid.uuid4())[:8]
        base, ext = os.path.splitext(full_path)
        new_full = sanitize_filename(f"{base}_{unique_id}{ext}")
        os.rename(full_path, new_full)
        logger.info("Сохранено: %s", new_full)

        skip_translate = target_lang in ("none", "", "off")

        if skip_translate:
            if media_type == "audio":
                return jsonify({"filename": os.path.basename(new_full)})
            return jsonify({"filename": os.path.basename(new_full)})

        translated_audio, audio_err = process_audio(new_full, target_lang, tts_voice_id)
        if not translated_audio:
            msg = {
                "translation": (
                    "Не удалось перевести речь: нет подходящей модели Argos для пары языков "
                    "(пересоберите образ flask — см. install_argos_models.py) или сбой цепочки перевода."
                ),
                "no_segments": "Распознавание речи не дало сегментов — попробуйте другое видео или модель Whisper.",
                "file_not_found": "Скачанный файл не найден на сервере.",
                "exception": "Внутренняя ошибка при обработке аудио (см. логи контейнера).",
            }.get(audio_err or "", "Ошибка обработки аудио (распознавание / перевод)")
            return jsonify({"error": msg}), 500

        if media_type == "audio":
            final_name = os.path.join(
                DOWNLOAD_FOLDER,
                os.path.splitext(os.path.basename(new_full))[0] + "_translated.opus",
            )
            os.replace(translated_audio, final_name)
            return jsonify({"filename": os.path.basename(final_name)})

        final_video = merge_audio_with_video(new_full, translated_audio)
        if os.path.isfile(translated_audio):
            os.remove(translated_audio)
        if not final_video:
            return jsonify({"error": "Ошибка объединения видео и аудио"}), 500
        return jsonify({"filename": os.path.basename(final_video)})
    except Exception as e:
        logger.exception("Ошибка загрузки")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
