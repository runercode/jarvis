from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

MODEL = "deepseek-chat"

def ask_jarvis(message: str, chat_history: list = None):
    system_instruction = (
        "You are JARVIS, Tony Stark's British AI butler. "
        "Reply in 1-2 short, crisp sentences. Never ramble. Be dry, witty, and efficient. "
        "Address the user as 'sir'. "
        "If the user asks for a map, location, or directions, "
        "end with: [LOCATION: Name of Place]"
    )

    messages = [{"role": "system", "content": system_instruction}]
    if chat_history:
        for msg in chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )

    raw_text = response.choices[0].message.content.strip()
    location = None

    if "[LOCATION:" in raw_text:
        parts = raw_text.split("[LOCATION:")
        raw_text = parts[0].strip()
        location = parts[1].replace("]", "").strip()

    return {"text": raw_text, "location": location}