You are an expert technical writer. Write a comprehensive, narrative-style development log (devlog) for a personal AI assistant project called JARVIS. The tone should be conversational and engaging — like a senior engineer telling the story of the build over coffee. Not a dry reference manual. Include personality, honest reflections on what went wrong, and the "why" behind decisions. Use the exact information provided below. Do not invent features or details that aren't listed.

---

## PROJECT IDENTITY

**Name:** JARVIS
**Tagline:** A personal AI assistant with long-term memory, semantic retrieval, voice interaction, and a holographic UI. Modeled after Tony Stark's British AI butler.
**Core differentiator:** Unlike stateless chatbots, JARVIS stores every conversation in a vector database and retrieves relevant past memories on every query, making it feel like a companion rather than a search box.

---

## TECH STACK

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.13 + FastAPI | HTTP server, routing, SSE streaming |
| LLM | DeepSeek (deepseek-chat) | Reasoning, responses, research. Accessed via OpenAI-compatible client. Temperature=0.3, max_tokens=120 |
| Embeddings | SentenceTransformers all-MiniLM-L6-v2 | Local 384-dim text embeddings, ~80MB, ~10-30ms per encoding on CPU, lazy-loaded singleton |
| Vector DB | ChromaDB 1.5.9 (PersistentClient) | Semantic similarity search, HNSW cosine index, embeds SQLite internally |
| Relational DB | SQLite (jarvis.db) | Users table, messages table with user_id foreign key |
| Auth | bcrypt 5.0.0 | Password hashing with gensalt() and checkpw() |
| Voice In | Browser SpeechRecognition API (en-GB) | Continuous listening with auto-retry (max 10 retries), visual state indicators |
| Voice Out | ElevenLabs (George voice, eleven_turbo_v2) → browser speechSynthesis fallback | British male TTS. gTTS is wired as a middle tier but broken due to dependency conflict |
| Frontend | Vanilla HTML/CSS/JS (~2,000 lines, single file) | No React, no build step, no node_modules. Canvas-based HUD with ring animation, holographic cylinders, mind-map engine |
| Maps | Google Maps Embed | Triggered by [LOCATION: ...] tags in LLM output |
| Deployment | Docker (Python 3.12-slim) | Containerization |

---

## PROJECT STRUCTURE

```
jarvis/
├── .env                    # API keys (DeepSeek, ElevenLabs)
├── .venv/                  # Python 3.13 virtual environment
├── main.py                 # FastAPI server — all endpoints
├── ai.py                   # DeepSeek LLM integration + system prompt
├── storage.py              # SQLite + ChromaDB + SentenceTransformers (unified data layer)
├── database.py             # LEGACY — replaced by storage.py, not imported
├── memory.py               # LEGACY — duplicate of database.py, not imported
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container deployment
├── runtime.txt             # Platform spec
├── README.md               # Project overview
├── DEVLOG.md               # The devlog you're writing
├── jarvis.db               # SQLite database (auto-created)
├── chroma_data/            # ChromaDB vector store (auto-created)
└── static/
    └── index.html          # Single-file HUD (~2,000 lines)
```

---

## PHASE 0 — SCAFFOLDING (June 2026)

**Goal:** Get from zero to "I can talk to it and it talks back" as fast as possible. No memory system, no auth. Just microphone → LLM → speaker with a cool UI.

**What was built:**

Backend (main.py):
- FastAPI server on port 8000
- POST /chat endpoint streaming responses from DeepSeek
- GET /tts endpoint hitting ElevenLabs (George British male voice) with gTTS fallback
- GET /system_stats endpoint for CPU/RAM telemetry

AI Layer (ai.py):
- OpenAI-compatible client pointed at DeepSeek (deepseek-chat)
- ask_jarvis() for sync chat, ask_jarvis_stream() for SSE streaming
- System prompt: British butler persona, one-sentence replies, dry wit
- [LOCATION: ...] parser that triggers Google Maps embed when the AI mentions a place
- research_jarvis() function that returns structured JSON for mind-map visualization

Database (database.py):
- Single SQLite table called "memory"
- save_message(role, content) and get_history(limit=10)
- Called it "memory" but it was just a linear chat log

Frontend (static/index.html) — the HUD:
- Single-file, no frameworks, no build step
- Cyberpunk-inspired holographic aesthetic with cyan/gold color palette
- Canvas-based JARVIS ring animation: multi-layered concentric rings rotating at different speeds
- 3D holographic cylinder visualization (bottom center, particle-based)
- Clock display (Orbitron font, right panel)
- Network/CPU/RAM stats panel
- Notes panel (chat log + input box)
- Left rail with targeting reticle and indicator dots
- Right rail with animated bar segments
- Bottom status bar with rotating quotes
- Overlay system: shared modal for System Monitor, Full Chat, Map, Terminal, Research
- Map overlay: Google Maps embed triggered by [LOCATION: ...] tags
- Mind-map engine: custom Canvas-based interactive node graph with pan/zoom (no D3, pure Canvas)
- Voice pipeline: SpeechRecognition API (en-GB), mic toggle with visual states (muted/listening/thinking), auto-retry up to 10 times, ElevenLabs → gTTS → browser speechSynthesis fallback chain
- Stats polling every 2.5 seconds

Devops:
- Dockerfile for Python 3.12-slim
- runtime.txt for platform compatibility
- .env for API keys

**Voice pipeline constraint (locked in as non-negotiable):**
1. Speech Recognition → 2. AI Chat → 3. TTS Output
- Language: en-GB only
- Voice: ElevenLabs George (primary), gTTS British (fallback), browser speechSynthesis (last resort)
- Database roles: "user" / "assistant" (required by DeepSeek API format)

---

## PHASE 1 — KEYSTONE ARCHITECTURE (Late June 2026)

**Seven keystone goals were defined:**
1. Long-term data storage (SQLite)
2. SentenceTransformers (local) for language processing
3. AI retrieval system (retrieving memory for usage)
4. Vector database (for AI retrieval)
5. AI reasoning layer (LLM via DeepSeek)
6. User layer (web app / HUD)
7. System orchestration (Python backend with FastAPI)

**The honest reality check:**

All seven were initially marked "done." But when the actual code was inspected:

| Component | Actual Status |
|---|---|
| FastAPI orchestration | ✅ Working — main.py with /chat, /tts, /research |
| DeepSeek LLM reasoning | ✅ Working — ai.py with streaming + sync |
| Web HUD | ✅ Working — index.html, single-file, no frameworks |
| SQLite storage | ⚠️ Partial — database.py + duplicate memory.py, only raw chat messages, no real semantic memory |
| SentenceTransformers | ❌ Not installed, not imported, not used |
| Vector database | ❌ No ChromaDB, no FAISS, no Pinecone |
| AI retrieval system | ❌ get_history() only returned last 10 raw messages — that's a scrollback buffer, not retrieval |

**Actual score: 4/7, not 7/7.** The three missing pieces were all in the same category: semantic memory. Phase 1 delivered a fully functional voice assistant with a stunning UI, but the "memory" was just a linear chat log — no embeddings, no semantic search, no real recall beyond the last ~1,200 tokens of context window. There were also two duplicate database files (database.py and memory.py) that both did the same basic thing — the result of copy-pasting code and forgetting about it.

This gap drove Phase 2.

---

## PHASE 2 — TRUE MEMORY & MULTI-USER (July 1, 2026)

**Goals:**
- Full semantic memory with SentenceTransformers + ChromaDB
- Memory retrieval injected into every LLM call
- Simple account creation (username + password, bcrypt-hashed)
- Per-user data isolation
- Foundation for future UI optimization

### Architecture Decisions

**SentenceTransformers all-MiniLM-L6-v2:** 80MB, runs on CPU, 384-dim vectors, ~10-30ms per embedding. The latency is invisible next to the 1-3 second LLM response time. Local-only means no API costs, no rate limits, no external dependencies. Loads once as a singleton — first call takes a moment, every subsequent call is instant.

**ChromaDB:** Embeds SQLite internally — natural pair with the existing SQLite setup. HNSW indexing gives sub-millisecond similarity search. All data in a chroma_data/ directory — no separate server, no Docker containers, no configuration. Just files on disk.

**bcrypt:** Industry standard for 20+ years. Simple API. No JWT overhead needed for a local-first app. No OAuth flows. Just username + password, hashed properly, stored in SQLite.

**Dual-write pattern (SQLite + ChromaDB):** SQLite handles structured queries (auth, recency-based history, user stats). ChromaDB handles semantic search. Both writes happen on every message. The separation of concerns is clean and the overhead is negligible.

### What Changed

**NEW FILE: storage.py** — Unified data layer replacing the fragmented database.py + memory.py:

```
storage.py
├── SQLite side
│   ├── users table (id, username, bcrypt-hashed password, created_at)
│   └── messages table (id, user_id FK, role, content, timestamp, index on user_id)
│
├── ChromaDB side
│   └── jarvis_messages collection (384-dim cosine vectors, HNSW indexed, metadata: user_id, role, timestamp, preview)
│
├── Embeddings
│   └── SentenceTransformer singleton (all-MiniLM-L6-v2, lazy-loaded, 80MB one-time download from HuggingFace)
│
├── User Management
│   ├── create_user(username, password) → {id, username} (bcrypt hashed, enforces min lengths)
│   └── authenticate_user(username, password) → {id, username} (bcrypt verify)
│
├── Message Persistence
│   ├── save_message(user_id, role, content) → dual-write to SQLite + ChromaDB with embedding
│   └── get_history(user_id, limit) → chronological, per-user, configurable limit
│
└── Semantic Memory
    ├── retrieve_memories(user_id, query, top_k) → [{content, timestamp, relevance}] via ChromaDB HNSW cosine search
    ├── search_memories(user_id, query, top_k) → API alias
    └── get_user_message_count(user_id) → simple stats
```

init_db() auto-runs on import and is fully idempotent — safe to restart the server as many times as you want.

**MODIFIED: ai.py** — Memory injection into the LLM:

New function _build_system_prompt(memories). When memories are provided, they get formatted into the system prompt like:
```
=== RELEVANT PAST MEMORIES (use these if they help answer the user) ===
[MEMORY 1 — 2026-07-01] My name is Bruce and I love building AI assistants
[MEMORY 2 — 2026-06-30] I prefer short answers and hate small talk
```

The LLM sees these before the user's message — it treats them like context it "knows" about the person. Result: JARVIS responds to who you ARE, not just what you SAID.

Both ask_jarvis() and ask_jarvis_stream() now accept optional user_id and memories params. Backward compatible — existing callers without memories still work.

**MODIFIED: main.py** — Auth + memory-aware chat:

New endpoints:
- POST /auth/register — create account, returns {id, username}
- POST /auth/login — authenticate, returns {id, username}
- POST /search — semantic search across past conversations
- GET /user/{user_id}/stats — message count per user

Modified /chat endpoint flow (before → after):

Before (Phase 1):
history = get_history()              # last 10 global messages
save_message("user", request.message) # no user isolation
# LLM call with just the raw history

After (Phase 2):
memories = retrieve_memories(user_id, msg, top_k=5)  # semantic search
history = get_history(user_id)                        # per-user history
save_message(user_id, "user", request.message)        # user-scoped
# LLM call with memories injected into system prompt + history
save_message(user_id, "assistant", response)           # user-scoped

**MODIFIED: index.html** — Login overlay:

- Full-screen login/register card with tab switching (LOG IN / REGISTER)
- bcrypt-backed auth (passwords never in plaintext)
- Session persisted in localStorage; auto-restored on reload with verification against /user/{id}/stats
- user_id sent with every /chat request
- Falls back to user_id=1 for backward compatibility
- HUD doesn't appear until authenticated (Boot() only runs after login)

### Test Results (All Passed, July 1, 2026)

Full pipeline test:
1. AUTH: Registered user → {id: 1, username: "testuser"}
2. CHAT (store): "My name is Bruce and I love building AI assistants" → JARVIS: "A pleasure, sir Bruce—though I suspect your AI assistants lack my particular brand of charm."
3. CHAT (recall): "What is my name and what do I enjoy building?" → JARVIS: "Your name is Bruce, sir, and you enjoy building AI assistants—though I daresay none quite as polished as myself."
4. SEMANTIC SEARCH for "AI assistants": [1] relevance=0.667 (Bruce's message), [2] relevance=0.639 (JARVIS recalling), [3] relevance=0.468 (JARVIS's first response)
5. USER STATS: {user_id: 1, total_messages: 4}

The moment where the AI says your name back to you after you told it five minutes ago — that's the entire point of the project. Stateless chatbots can't do that. JARVIS now can.

---

## KNOWN ISSUES

1. **gTTS / click version conflict:** sentence-transformers requires click>=8.4. gTTS requires click<8.2. They can't coexist. click is kept at 8.4, meaning gTTS may fail at runtime. The browser speechSynthesis fallback still works. Fix: wait for gTTS to update, or replace it entirely.

2. **Two Python installations on the machine:** Windows Store Python and standalone Python 3.13. Pip was installing to one while python ran from the other. Fixed by creating .venv in the project directory. Always use .\.venv\Scripts\python.exe.

3. **No JWT/session tokens:** Auth is stateless — just returns user ID. Frontend stores it in localStorage. Fine for localhost. Needs proper token auth before exposing to a network.

4. **ChromaDB first-run download:** SentenceTransformers downloads all-MiniLM-L6-v2 (~80MB) from HuggingFace on first import. One-time cost.

5. **No input sanitization:** Messages stored and retrieved as-is. No XSS filtering. Fine for personal use, needs fixing for multi-tenant.

6. **database.py and memory.py are dead code:** They're not imported anywhere. Kept as historical artifacts until confident nothing references them.

---

## UPCOMING MILESTONES

**Phase 3 — Autonomy & Tool Use:**
- Function calling (DeepSeek supports it) — reminders, calendar, email
- Fact extraction pipeline (auto-extract user facts from conversations)
- Web search integration (DuckDuckGo or SerpAPI)
- Scheduled/background tasks (daily summaries, proactive check-ins)

**Phase 4 — Production Hardening:**
- JWT-based authentication
- Structured logging (Loguru)
- Configuration management (move hardcoded values to config.yaml or env vars)
- Conversation summarization for long-term compression
- Input sanitization / XSS prevention
- Rate limiting

**Phase 5 — UI Optimization:**
- Responsive design for mobile/tablet
- Dark/light theme support
- Customizable HUD layout
- Notification system
- File upload / image recognition
- Voice command customization

---

## WRITING INSTRUCTIONS

Write the devlog in a narrative, conversational tone. Think of it as a story told by the developer — include honest reflections, the "oh wait that doesn't actually work" moments, and the satisfaction of things finally clicking. Use section titles that sound like a human wrote them, not a template.

Include a Mermaid flowchart showing the data flow from user input → auth → memory retrieval → LLM → response → TTS.

Include the project directory tree.

Include the tech stack, but explain each choice in plain language — why that specific technology earned its place rather than just listing what it does.

Structure it as: The Idea → Phase 0 → Phase 1 → Phase 2 → How It All Fits Together → Known Issues → Where We're Going Next.

Make it something someone would actually enjoy reading. Keep all the technical substance, but wrap it in personality.

Output the final devlog as a single Markdown file.
