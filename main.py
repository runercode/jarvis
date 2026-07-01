import os
import io
import requests
import psutil
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai import ask_jarvis, ask_jarvis_stream, research_jarvis

# ── Phase 2: memory & auth ──
from storage import (
    create_user,
    authenticate_user,
    save_message,
    get_history,
    retrieve_memories,
    search_memories,
    get_user_message_count,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

app = FastAPI()


class ChatRequest(BaseModel):
    message: str
    user_id: int = 1

class ResearchRequest(BaseModel):
    topic: str

class AuthRequest(BaseModel):
    username: str
    password: str

class SearchRequest(BaseModel):
    query: str
    user_id: int


@app.get("/system_stats")
async def get_stats():
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
    }


# ── Auth ───────────────────────────────────────────────────────────────

@app.post("/auth/register")
async def register(req: AuthRequest):
    result = create_user(req.username, req.password)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/auth/login")
async def login(req: AuthRequest):
    result = authenticate_user(req.username, req.password)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


# ── Chat (memory‑aware) ────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    print(f"\n>>> [USER {request.user_id}]: {request.message}")
    try:
        # 1. Retrieve semantically similar past messages
        memories = retrieve_memories(request.user_id, request.message, top_k=5)
        if memories:
            print(f"    [MEMORY] Retrieved {len(memories)} relevant memories")

        # 2. Get recent chat history for context window
        history = get_history(request.user_id)

        # 3. Persist user message
        save_message(request.user_id, "user", request.message)

        # 4. Stream the LLM response with memories injected
        async def generate():
            full_text = ""
            location = None
            for sse_chunk in ask_jarvis_stream(
                request.message,
                chat_history=history,
                user_id=request.user_id,
                memories=memories,
            ):
                yield sse_chunk
                if '"done": true' in sse_chunk:
                    import json
                    data = json.loads(sse_chunk.replace("data: ", "").strip())
                    full_text = data.get("text", "")
                    location = data.get("location")
                    save_message(request.user_id, "assistant", full_text)
                    print(f"<<< [JARVIS]: {full_text}")
                    if location:
                        print(f"    [!] Triggering Map for: {location}")

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        print(f"!!! [DEEPSEEK ERROR]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

@app.get("/tts")
async def tts(text: str):
    try:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY not set")

        voice_id = "JBFqnCBsd6RMkjVDRZzb"  # George — British male voice
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.7,
                "speed": 1.1
            }
        }
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers, stream=True)
        response.raise_for_status()

        def generate():
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk

        print(f"<-- ElevenLabs British audio streaming for text length {len(text)}")
        return StreamingResponse(generate(), media_type="audio/mpeg")

    except requests.RequestException as e:
        print(f"!!! [ELEVENLABS ERROR]: {e}")
        # Fallback: try to use gTTS if ElevenLabs fails
        try:
            from gtts import gTTS
            audio = gTTS(text=text, lang='en', tld='co.uk')
            buffer = io.BytesIO()
            audio.write_to_fp(buffer)
            buffer.seek(0)
            print(f"<-- Fallback gTTS British audio for text length {len(text)}")
            return StreamingResponse(buffer, media_type="audio/mpeg")
        except Exception as fallback_err:
            print(f"!!! [FALLBACK TTS ERROR]: {fallback_err}")
            raise HTTPException(status_code=500, detail=f"TTS Error: {e}")
    except Exception as err:
        print(f"!!! [TTS ERROR]: {err}")
        raise HTTPException(status_code=500, detail=f"TTS Error: {err}")

@app.post("/research")
async def research(request: ResearchRequest):
    print(f"\n>>> [RESEARCH]: {request.topic}")
    try:
        data = research_jarvis(request.topic)
        print(f"<<< [RESEARCH] returned {len(data.get('nodes',[]))} nodes")
        return data
    except Exception as e:
        print(f"!!! [RESEARCH ERROR]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Research Error: {str(e)}")

# ── Memory search ──────────────────────────────────────────────────────

@app.post("/search")
async def search_memory_ep(request: SearchRequest):
    """Semantically search past conversations."""
    results = search_memories(request.user_id, request.query, top_k=10)
    return {
        "query": request.query,
        "total_stored": get_user_message_count(request.user_id),
        "results": results,
    }

@app.get("/user/{user_id}/stats")
async def user_stats(user_id: int):
    return {
        "user_id": user_id,
        "total_messages": get_user_message_count(user_id),
    }

# Mount static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
