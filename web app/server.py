"""
server.py — StudyBuddy FastAPI Backend
Run: uvicorn server:app --reload --port 8000

Endpoints:
  POST /generate       — generate flashcards from text
  POST /translate      — translate existing study set
  POST /detect-lang    — detect language of text
  POST /session        — receive session data from Chrome extension
  GET  /session        — get latest session data
"""

import os, json, re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ── Gemini ────────────────────────────────────────────────────────────────────
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("[server] google-genai not installed. Run: pip install google-genai")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    print("[server] WARNING: GEMINI_API_KEY not set. Create a .env file with GEMINI_API_KEY=your_key")
SESSION_FILE   = Path("/tmp/studybuddy_session.json")

app = FastAPI(title="StudyBuddy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve frontend ────────────────────────────────────────────────────────────
@app.get("/")
def serve_frontend():
    return FileResponse("app.html")

# ── Gemini helper ─────────────────────────────────────────────────────────────
def call_gemini(prompt: str) -> str:
    if not GENAI_AVAILABLE:
        raise HTTPException(500, "google-genai not installed")
    if not GEMINI_API_KEY:
        raise HTTPException(400, "GEMINI_API_KEY not set. Run: export GEMINI_API_KEY=your_key")
    client   = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text

def parse_json(raw: str) -> dict:
    cleaned = re.sub(r'```json|```', '', raw).strip()
    return json.loads(cleaned)

# ── Request models ────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    text:     str
    language: str = "English"
    confusion_score: float = 0.3

class TranslateRequest(BaseModel):
    study_set: dict
    language:  str

class DetectRequest(BaseModel):
    text: str

class SessionData(BaseModel):
    startTime:       Optional[int]  = None
    confusionSpikes: int            = 0
    focusScore:      int            = 100
    cardsDone:       int            = 0
    pomodorosDone:   int            = 0
    confusionLog:    list           = []
    active:          bool           = False

# ── /generate ─────────────────────────────────────────────────────────────────
@app.post("/generate")
def generate(req: GenerateRequest):
    if not req.text.strip():
        raise HTTPException(400, "No text provided")

    level = "high" if req.confusion_score > 0.65 else "medium" if req.confusion_score > 0.35 else "low"

    prompt = f"""You are a study assistant. Generate study material IN {req.language}.
Student confusion level: {level} — {"simplify and use analogies" if level=="high" else "standard depth"}.

Content:
\"\"\"
{req.text[:7000]}
\"\"\"

Return ONLY valid JSON (no markdown fences):
{{
  "summary": "2-3 sentence plain summary",
  "flashcards": [
    {{ "front": "Question or concept", "back": "Answer or explanation", "hint": "one-line memory tip" }},
    {{ "front": "...", "back": "...", "hint": "..." }},
    {{ "front": "...", "back": "...", "hint": "..." }}
  ],
  "questions": [
    {{ "question": "MCQ question", "options": ["A","B","C","D"], "correct_index": 0, "explanation": "why correct" }},
    {{ "question": "...", "options": ["...","...","...","..."], "correct_index": 1, "explanation": "..." }}
  ]
}}"""

    try:
        raw  = call_gemini(prompt)
        data = parse_json(raw)
        return data
    except json.JSONDecodeError:
        raise HTTPException(500, "Failed to parse Gemini response as JSON")
    except Exception as e:
        raise HTTPException(500, str(e))

# ── /translate ────────────────────────────────────────────────────────────────
@app.post("/translate")
def translate(req: TranslateRequest):
    if req.language == "English":
        return req.study_set

    prompt = f"""Translate this JSON study material into {req.language}.
Keep the exact JSON structure. Translate all string values.
Do NOT translate JSON keys or numbers.
Return ONLY valid JSON, no markdown fences.

{json.dumps(req.study_set, ensure_ascii=False)}"""

    try:
        raw  = call_gemini(prompt)
        data = parse_json(raw)
        return data
    except Exception as e:
        raise HTTPException(500, str(e))

# ── /detect-lang ──────────────────────────────────────────────────────────────
@app.post("/detect-lang")
def detect_lang(req: DetectRequest):
    prompt = f"""Detect the language of this text. Return ONLY the language name in English (e.g. "Hindi", "Arabic", "English"). No explanation.
Text: {req.text[:300]}"""
    try:
        result = call_gemini(prompt)
        return {"language": result.strip()}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── /session ──────────────────────────────────────────────────────────────────
@app.post("/session")
def save_session(session: SessionData):
    SESSION_FILE.write_text(json.dumps(session.dict()))
    return {"success": True}

@app.get("/session")
def get_session():
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return {}


# ── /translate-text ───────────────────────────────────────────────────────────
class TranslateTextRequest(BaseModel):
    text:     str
    language: str

@app.post("/translate-text")
def translate_text(req: TranslateTextRequest):
    if req.language == "English":
        return {"translated": req.text}
    prompt = f"""Translate the following text into {req.language}.
Preserve line breaks exactly — each line in the input must correspond to one line in the output.
Return ONLY the translated text, no explanations.

{req.text}"""
    try:
        result = call_gemini(prompt)
        return {"translated": result.strip()}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

# ── /generate-simple (low-bandwidth + simplified language) ───────────────────
class SimplifyRequest(BaseModel):
    text:     str
    language: str = "English"
    mode:     str = "normal"

@app.post("/generate-simple")
def generate_simple(req: SimplifyRequest):
    if not req.text.strip():
        raise HTTPException(400, "No text provided")

    if req.mode == "low-bandwidth":
        prompt = f"Study assistant. Generate in {req.language}. Be VERY brief.\nText: {req.text[:2000]}\nReturn ONLY JSON no markdown: {{\"summary\":\"1 sentence\",\"flashcards\":[{{\"front\":\"Q\",\"back\":\"A\",\"hint\":\"tip\"}},{{\"front\":\"Q\",\"back\":\"A\",\"hint\":\"tip\"}},{{\"front\":\"Q\",\"back\":\"A\",\"hint\":\"tip\"}}],\"questions\":[{{\"question\":\"Q\",\"options\":[\"A\",\"B\",\"C\",\"D\"],\"correct_index\":0,\"explanation\":\"why\"}}]}}"
    else:
        prompt = f"""You are a study assistant helping students who find reading difficult.
Generate study material in {req.language} using VERY simple words (5th grade level).
Use short sentences. Avoid jargon. Use everyday examples.
Content: {req.text[:5000]}
Return ONLY valid JSON no markdown:
{{"summary":"1-2 simple sentences","flashcards":[{{"front":"simple question","back":"simple answer","hint":"easy tip"}},{{"front":"...","back":"...","hint":"..."}},{{"front":"...","back":"...","hint":"..."}}],"questions":[{{"question":"simple MCQ","options":["A","B","C","D"],"correct_index":0,"explanation":"simple reason"}},{{"question":"...","options":["...","...","...","..."],"correct_index":1,"explanation":"..."}}]}}"""

    try:
        raw  = call_gemini(prompt)
        data = parse_json(raw)
        return data
    except Exception as e:
        raise HTTPException(500, str(e))