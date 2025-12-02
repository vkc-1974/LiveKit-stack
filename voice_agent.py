#!/bin/env python3

import asyncio
import os
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice_assistant import VoiceAssistant  # Для voice pipeline
from livekit.plugins import silero, openai  # Замените на ollama для Llama
# Для Ollama: pip install livekit-plugins-ollama (если доступно; иначе custom LLM)
from livekit.plugins.ollama import OllamaLLM  # Предполагаем плагин; если нет, используйте openai с proxy или custom
import mariadb  # Для MCP/DB access
from livekit.agents.llm import function_tool  # Для инструментов MCP

load_dotenv()

# Env vars (добавьте в .env или docker-compose env для agent-сервиса)
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "APIAr4ziPRxD7RQ")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "NG4BDigFkZpjXZrJ7oPfHd9p0WdxPLuffJcAKUHJjKfC")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")  # Или ollama:11434 в сети
DB_HOST = os.getenv("DB_HOST", "mariadb")
DB_USER = os.getenv("DB_USER", "livekit_user")
DB_PASS = os.getenv("DB_PASS", "livekit_pass")
DB_NAME = os.getenv("DB_NAME", "livekit_db")

# MCP tool: функция для query DB (пример для баланса пользователя)
@function_tool
async def get_user_balance(user_id: int) -> str:
    """Get user balance from DB via MCP interface."""
    try:
        conn = mariadb.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT balance_value FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return f"Balance: {result[0] if result else 'Not found'}"
    except Exception as e:
        return f"DB error: {str(e)}"

async def entrypoint(ctx: JobContext):
    """Entrypoint: запускается при dispatch в room."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)  # Подписка только на аудио (SIP)

    # Инициализация LLM с Llama (Ollama plugin; если нет, используйте openai.LLM с custom endpoint)
    llm_plugin = OllamaLLM(
        model="llama3.2:3b-instruct-q4_K_M",
        base_url=OLLAMA_URL,
        temperature=0.7
    )
    # Добавьте tool для MCP
    llm_plugin.add_tool(get_user_balance)

    # Voice pipeline: VAD/STT/LLM/TTS (адаптируйте под ваши plugins; здесь Silero для VAD, Deepgram для STT если env)
    assistant = VoiceAssistant(
        vad=silero.VAD.load(),  # Voice Activity Detection
        stt=openai.STT(),  # Или deepgram.STT() если ключ
        llm=llm_plugin,  # Llama для instruct
        tts=openai.TTS(voice="alloy"),  # TTS; для local — custom или elevenlabs
        chat_ctx=llm.ChatContext().append(  # Initial system prompt
            role="system",
            text="You are a voice assistant integrated with SIP calls. Use DB tools for user context. Greet callers and handle queries."
        )
    )
    assistant.start(ctx.room)  # Запуск в room

if __name__ == "__main__":
    # Worker options: регистрирует в LiveKit
    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        healthcheck_url="http://localhost:8080"  # Опционально, для monitoring
    )
    cli.run_app(worker=worker_options)  # Запуск worker'а
