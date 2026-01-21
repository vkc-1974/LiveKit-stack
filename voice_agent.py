#!/usr/bin/env python3

import asyncio
import httpx
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, Agent, AgentSession, APIConnectOptions
from livekit.agents.types import APIConnectOptions, NOT_GIVEN, NotGivenOr
from livekit.agents.stt import STT, SpeechEvent, SpeechEventType, STTCapabilities, StreamAdapter
from livekit.agents.utils.audio import AudioBuffer
from livekit.agents.tts import TTS, TTSCapabilities, SynthesizedAudio
from livekit.agents.tts.tts import ChunkedStream
from livekit.plugins import silero
from livekit.plugins.openai import LLM as OpenAILLM
from livekit.agents.llm import function_tool, ChatContext
from common import settings
from faster_whisper import WhisperModel
import edge_tts
import os
import asyncio
import logging

DEFAULT_LANGUAGE = "ru"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# STT — faster-whisper
class FasterWhisperSTT(STT):
    def __init__(self):
        print("Initialization of FasterWhisperSTT")
        super().__init__(
            capabilities=STTCapabilities(
                # FasterWhisperSTT does not support streaming at all!
                streaming=False,
                # No intermediate results
                interim_results=False,
            ))
        #### model_size = "large-v3"
        model_size = "base"
        model_dir = os.path.abspath(f"models/faster-whisper-{model_size}")
        print(f"Loading WhisperModel {model_dir}...")
        self.whisper_model = WhisperModel(
            model_dir,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            num_workers=2,
            local_files_only=True
        )
        print(f"WhisperModel {model_dir} loaded successfully!")

    async def _recognize_impl(
            self,
            buffer: AudioBuffer,
            *,
            language: NotGivenOr[str] = NOT_GIVEN,
            conn_options: APIConnectOptions,
    ) -> SpeechEvent:
        print("An audio buffer has been passed")

        # AudioBuffer — это bytes-like объект, его можно передать напрямую
        segments, info = self.whisper_model.transcribe(
            buffer,  # ← можно передать AudioBuffer как bytes
            language=language if language is not NOT_GIVEN else DEFAULT_LANGUAGE,
            # An option to Beam Search Decoding algorithm;
            # it controls the number of alternative hypotheses
            # (potential transcriptions) that the model keeps at each step
            beam_size=5,
            # Activate Voice Activity Detection (VAD):
            # * reduces hallucinations
            # * improves accuracy
            # * potential speed increase
            vad_filter=True,
        )

        if not segments:
            return SpeechEvent(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[],
            )

        text = " ".join(s.text.strip() for s in segments if s.text.strip())

        alternative = {
            "text": text,
            "confidence": float(info.language_probability) if info else 0.95,
            "language": info.language if info else DEFAULT_LANGUAGE,
        }

        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[alternative],
        )

from livekit.agents.tts import TTS, TTSCapabilities, SynthesizedAudio
from livekit import rtc
import edge_tts

class EdgeTTSSynthesize(TTS):
    def __init__(self):
        super().__init__(
            capabilities=TTSCapabilities(
                streaming=False,
                aligned_transcript=False
            ),
            sample_rate=24000,
            num_channels=1
        )
        self.voice = "ru-RU-SvetlanaNeural"
        self.rate = "+0%"
        self.pitch = "+0Hz"

    # метод stream() можно полностью удалить или оставить с raise
    # async def stream(...): raise NotImplementedError("streaming TTS not supported")

    # synthesize остаётся как есть (только убери yield, замени на send)
    async def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = APIConnectOptions()
    ) -> ChunkedStream:

        class EdgeChunkedStream(ChunkedStream):
            def __init__(self, tts: TTS, input_text: str, conn_options: APIConnectOptions):
                super().__init__(
                    tts=tts,
                    input_text=input_text,
                    conn_options=conn_options
                )

            async def _run(self):
                print(f"Text-to-Speach: {self.input_text[:80]}...")
                communicate = edge_tts.Communicate(
                    self.input_text,
                    voice=self._tts.voice,
                    rate=self._tts.rate,
                    pitch=self._tts.pitch
                )
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunk = SynthesizedAudio(
                            data=chunk["data"],
                            sample_rate=self._tts.sample_rate,
                            num_channels=self._tts.num_channels
                        )
                        await self._event_ch.send(audio_chunk)
                        print(f"Chunk of {len(chunk['data'])} byte(s) gas been sent")

                await self._event_ch.close()
                print("Channel has been closed")

        return EdgeChunkedStream(self, text, conn_options)

# Tool для баланса
@function_tool(name="get_user_balance")
async def get_user_balance(user_id: int) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{settings.mcp_server_url}/tools/get_user_balance",
                json={"user_id": user_id}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("content", "Error: unable to get account balance")
        except Exception as e:
            return f"Error: unexpected exception {str(e)}"

# Entrypoint
async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    raw_stt = FasterWhisperSTT()
    
    agent_vad = silero.VAD.load()
    agent_stt = StreamAdapter(
        stt=raw_stt,
        vad=agent_vad
    )
    agent_llm_plugin = OpenAILLM.with_ollama(
        model=settings.ollama_model,
        base_url=settings.ollama_url.rstrip('/') + "/v1",
        temperature=0.65
    )
    agent_tts = EdgeTTSSynthesize()

    agent_instructions = "Голосовой помощник. Отвечай на русском."
    agent_tools = [get_user_balance]

    agent_session = AgentSession(
        vad=agent_vad,
        stt=agent_stt,
        llm=agent_llm_plugin,
        tts=agent_tts,
        allow_interruptions=False, ### True,
    )

    print("AgentSession is ready")
    
    agent = Agent(
        instructions=agent_instructions,
        tools=agent_tools,
    )

    print("Agent is ready")

    await agent_session.start(room=ctx.room,
                        agent=agent)

    # Handle session events
    @agent_session.on("agent_state_changed")
    def on_state_changed(ev):
        """Log agent state changes."""
        print(f"State: {ev.old_state} -> {ev.new_state}")
    
    @agent_session.on("user_started_speaking")
    def on_user_speaking():
        """Track when user starts speaking."""
        print("User started speaking")
    
    @agent_session.on("user_stopped_speaking")
    def on_user_stopped():
        """Track when user stops speaking."""
        print("User stopped speaking")

    print("agent_session.start() is running")

    await agent_session.generate_reply(
        ### instructions="Привет! Я могу проверить баланс твоего счёта, если скажешь user_id.",
        instructions="Greet the user warmly and ask how you can help.",
        ### allow_interruptions=False, ### True
    )

    print("agent_session.generate_reply(GREATING) running")
 
    
if __name__ == "__main__":
    agent_name="ai-voice-agent"
    print(f"[V-AGENT] Start running [{agent_name}] agent")
    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        job_memory_warn_mb=2048,
        agent_name=agent_name
    )
    cli.run_app(worker_options)
