#!/bin/env python3

import asyncio
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import silero, openai
from livekit.plugins.ollama import OllamaLLM
import mariadb
from livekit.agents.llm import function_tool
from common import settings

# MCP tool: a routine to get a user account balance
@function_tool
async def get_user_balance(user_id: int) -> str:
    """Get user balance from DB via MCP interface."""
    try:
        conn = mariadb.connect(host=settings.db_host,
                               port=settings.db_port,
                               user=settings.db_user,
                               password=settings.db_pass,
                               database=settings.db_name)
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
    llm_plugin = OllamaLLM(model=settings.ollama_model,
                           base_url=settings.ollama_url,
                           temperature=0.7)

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
