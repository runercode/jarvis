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
        "end with: [LOCATION: Name of Place]. "
        "Be conservative with data — if listing things, cap at 5 max. "
        "Summarize, don't enumerate."
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


def research_jarvis(topic: str):
    """Research a topic and return structured mind-map data."""
    system_instruction = (
        "You are JARVIS, Tony Stark's AI research assistant. "
        "Research the given topic thoroughly but concisely. "
        "Return ONLY valid JSON — no markdown, no code fences, no extra text. "
        "Categorize into exactly 3-5 parent categories, each with 2-4 child items. "
        "Total child items must not exceed 15. Keep each item to 1 line.\n\n"
        "JSON format:\n"
        '{"summary":"1-sentence overview","nodes":[\n'
        '  {"id":"c1","title":"Category Name","parent":null,"depth":0},\n'
        '  {"id":"c1_a","title":"Item title — brief detail","parent":"c1","depth":1},\n'
        '  ...\n'
        ']}'
    )

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Research: {topic}"}
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.4
    )

    raw = response.choices[0].message.content.strip()
    # Strip code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    import json
    data = json.loads(raw)
    return data