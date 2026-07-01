from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os
import json

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

MODEL = "deepseek-chat"

# ---------------------------------------------------------------------------
# System prompt builder — injects retrieved memories when available
# ---------------------------------------------------------------------------

def _build_system_prompt(memories: list[dict] | None = None) -> str:
    """Build the JARVIS system instruction, optionally enriched with past memories."""
    base = (
        "You are JARVIS, Tony Stark's British AI butler. "
        "Reply in 1 short, crisp sentence. Never ramble. Be dry, witty, efficient. "
        "Address the user as 'sir'. "
        "If the user asks for a product, item, or shopping search, "
        "end with: [AMAZON: search term]. "
        "Cap lists at 5 max. Summarize, don't enumerate."
    )

    if not memories:
        return base

    # Build a compact memory block from the most relevant past messages
    mem_lines = []
    for i, m in enumerate(memories, 1):
        ts = m.get("timestamp", "")[:10] if m.get("timestamp") else "unknown"
        mem_lines.append(f"[MEMORY {i} — {ts}] {m['content']}")

    mem_block = (
        "\n\n=== RELEVANT PAST MEMORIES (use these if they help answer the user) ===\n"
        + "\n".join(mem_lines)
    )
    return base + mem_block


# ---------------------------------------------------------------------------
# Core chat functions (now memory-aware via user_id)
# ---------------------------------------------------------------------------

def ask_jarvis(message: str, chat_history: list = None, user_id: int = None, memories: list[dict] = None):
    system_instruction = _build_system_prompt(memories)

    messages = [{"role": "system", "content": system_instruction}]
    if chat_history:
        for msg in chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=120
    )

    raw_text = response.choices[0].message.content.strip()
    location = None

    if "[AMAZON:" in raw_text:
        parts = raw_text.split("[AMAZON:")
        raw_text = parts[0].strip()
        location = parts[1].replace("]", "").strip()

    return {"text": raw_text, "location": location}


def ask_jarvis_stream(message: str, chat_history: list = None, user_id: int = None, memories: list[dict] = None):
    """Streaming version — yields SSE data strings for instant UI feedback."""
    system_instruction = _build_system_prompt(memories)

    messages = [{"role": "system", "content": system_instruction}]
    if chat_history:
        for msg in chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=120,
        stream=True
    )

    full_text = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            full_text += token
            yield f"data: {json.dumps({'t': token})}\n\n"

    # Extract amazon search
    location = None
    text = full_text.strip()
    if "[AMAZON:" in text:
        parts = text.split("[AMAZON:")
        text = parts[0].strip()
        location = parts[1].replace("]", "").strip()

    yield f"data: {json.dumps({'done': True, 'text': text, 'location': location})}\n\n"


def research_jarvis(topic: str):
    """Research a topic and return structured mind-map data."""
    system_instruction = (
        "You are JARVIS, Tony Stark's AI research assistant. "
        "Research the given topic thoroughly but concisely. "
        "Return ONLY valid JSON — no markdown, no code fences, no extra text. "
        "If the user is asking about products (bikes, scooters, electronics, etc.), "
        "categorize by product type/feature NOT by store/vendor. "
        "List specific product models with key specs, not where to buy them. "
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
        {"role": "user", "content": f"Research and give me actual items/products for: {topic}. NOT stores — I want the things themselves."}
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.4,
        max_tokens=800
    )

    raw = response.choices[0].message.content.strip()
    # Strip code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    import json
    data = json.loads(raw)
    return data