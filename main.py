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
from ai import ask_jarvis
from database import save_message, get_history

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.get("/system_stats")
async def get_stats():
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent
    }

@app.post("/chat")
async def chat(request: ChatRequest):
    print(f"\n>>> [USER]: {request.message}")
    try:
        history = get_history()
        result = ask_jarvis(request.message, history)
        
        save_message("user", request.message)
        save_message("assistant", result["text"])
        
        print(f"<<< [JARVIS]: {result['text']}")
        if result['location']:
            print(f"    [!] Triggering Map for: {result['location']}")
            
        return result
    except Exception as e:
        print(f"!!! [GEMINI ERROR]: {str(e)}")
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

# Mount static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)