# __init__.py
from .chat_apps.ollama_chat import create_app as create_ollama_chat
from .chat_apps.gpt_chat import create_app as create_gpt_chat
from config.constants import models_app

__all__ = ["create_ollama_chat", "create_gpt_chat", "models_app"]
