"""
Module 3: AI Flashcard Generator (Gemini)
Takes a TextContext + confusion_score and generates:
  - Flashcards (term → definition)
  - Multiple-choice questions
  - A short summary/hint

Set your Gemini API key:
    export GEMINI_API_KEY="your_key_here"
or pass it directly to GeminiFlashcardGenerator(api_key="...")

Requires: pip install google-generativeai
"""

import os
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional
from text_extractor import TextContext

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[FlashcardGen] google-generativeai not installed. "
          "Run: pip install google-generativeai")


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class Flashcard:
    term: str
    definition: str
    hint: str = ""

    def __str__(self):
        return f"Q: {self.term}\nA: {self.definition}"


@dataclass
class MCQuestion:
    question: str
    options: List[str]      # always 4 options
    correct_index: int      # 0-3
    explanation: str = ""

    @property
    def correct_answer(self) -> str:
        return self.options[self.correct_index]

    def __str__(self):
        opts = "\n".join(f"  {'ABCD'[i]}. {o}" for i, o in enumerate(self.options))
        return f"Q: {self.question}\n{opts}\nAnswer: {'ABCD'[self.correct_index]}"


@dataclass
class StudySet:
    flashcards: List[Flashcard]    = field(default_factory=list)
    questions: List[MCQuestion]    = field(default_factory=list)
    summary: str                   = ""
    topic: str                     = ""
    confusion_level: str           = "low"    # low / medium / high
    difficulty: str                = "medium" # easy / medium / hard

    def is_empty(self) -> bool:
        return not self.flashcards and not self.questions


# ── Generator ─────────────────────────────────────────────────────────────────

class GeminiFlashcardGenerator:

    MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: Optional[str] = None):
        key = "AIzaSyCsa7Yua5-mPsd00eEwkreMfFiOqmEQPVk" or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY env var "
                "or pass api_key= to GeminiFlashcardGenerator()"
            )
        if GEMINI_AVAILABLE:
            genai.configure(api_key=key)
            self.model = genai.GenerativeModel(self.MODEL)
        self._key = key

    def generate(
        self,
        ctx: TextContext,
        confusion_score: float = 0.3,
        num_flashcards: int = 3,
        num_questions: int = 2,
    ) -> StudySet:
        """
        Main entry point. Returns a StudySet.
        confusion_score: 0.0 (calm) → 1.0 (very confused)
        """
        level, difficulty = self._confusion_to_level(confusion_score)

        prompt = self._build_prompt(
            ctx.snippet,
            ctx.topic_keywords,
            level,
            difficulty,
            num_flashcards,
            num_questions,
        )

        raw = self._call_gemini(prompt)
        study_set = self._parse_response(raw)
        study_set.topic          = ", ".join(ctx.topic_keywords[:3])
        study_set.confusion_level = level
        study_set.difficulty      = difficulty
        return study_set

    # ── Prompt engineering ────────────────────────────────────────────────────

    def _build_prompt(self, snippet, keywords, level, difficulty,
                      n_cards, n_qs):
        difficulty_instruction = {
            "easy":   "Use simple language, focus on definitions and basic facts.",
            "medium": "Include application and understanding questions.",
            "hard":   "Include analysis, comparison, and 'why/how' questions.",
        }[difficulty]

        confusion_instruction = {
            "low":    "The student is following well. Create standard review material.",
            "medium": "The student seems slightly confused. Add helpful hints and "
                      "break concepts into smaller steps.",
            "high":   "The student is very confused. Simplify heavily, use analogies, "
                      "and focus on the single most important concept first.",
        }[level]

        kw_str = ", ".join(keywords[:6]) if keywords else "unknown"

        return f"""You are a study assistant helping a student understand their lesson material.

CONTEXT:
- Student confusion level: {level.upper()} ({confusion_instruction})
- Difficulty: {difficulty.upper()} ({difficulty_instruction})
- Key topics detected: {kw_str}

LESSON TEXT:
\"\"\"
{snippet}
\"\"\"

TASK: Generate exactly the following in valid JSON (no markdown, no code fences):

{{
  "summary": "<2-3 sentence plain-English summary of the key idea>",
  "flashcards": [
    {{
      "term": "<concept or question>",
      "definition": "<clear answer or explanation>",
      "hint": "<one-sentence memory aid>"
    }}
    // repeat for {n_cards} flashcards total
  ],
  "questions": [
    {{
      "question": "<question text>",
      "options": ["<A>", "<B>", "<C>", "<D>"],
      "correct_index": <0-3>,
      "explanation": "<why the answer is correct>"
    }}
    // repeat for {n_qs} questions total
  ]
}}

RULES:
- Output ONLY the JSON object. No intro text, no markdown fences.
- options array must always have exactly 4 items.
- correct_index must be an integer 0, 1, 2, or 3.
- Base everything strictly on the provided lesson text.
- Keep language appropriate for a student studying this topic.
"""

    # ── Gemini API call ───────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str) -> str:
        if not GEMINI_AVAILABLE:
            return self._mock_response()
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.4,
                    max_output_tokens=1500,
                )
            )
            return response.text
        except Exception as e:
            print(f"[FlashcardGen] Gemini API error: {e}")
            return self._mock_response()

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> StudySet:
        # Strip any accidental markdown fences
        cleaned = re.sub(r'```(?:json)?', '', raw).strip().strip('`')

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON object from response
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except Exception:
                    return self._fallback_set()
            else:
                return self._fallback_set()

        flashcards = []
        for fc in data.get("flashcards", []):
            flashcards.append(Flashcard(
                term=fc.get("term", ""),
                definition=fc.get("definition", ""),
                hint=fc.get("hint", ""),
            ))

        questions = []
        for q in data.get("questions", []):
            opts = q.get("options", ["A", "B", "C", "D"])
            if len(opts) != 4:
                opts = (opts + ["—", "—", "—", "—"])[:4]
            questions.append(MCQuestion(
                question=q.get("question", ""),
                options=opts,
                correct_index=int(q.get("correct_index", 0)),
                explanation=q.get("explanation", ""),
            ))

        return StudySet(
            flashcards=flashcards,
            questions=questions,
            summary=data.get("summary", ""),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _confusion_to_level(score: float):
        if score < 0.35:
            return "low", "medium"
        elif score < 0.65:
            return "medium", "easy"
        else:
            return "high", "easy"

    @staticmethod
    def _fallback_set() -> StudySet:
        return StudySet(
            summary="Could not generate study material — please try again.",
            flashcards=[Flashcard(
                term="Error",
                definition="AI response could not be parsed. Check your API key and try again.",
                hint="",
            )],
        )

    @staticmethod
    def _mock_response() -> str:
        """Returned when Gemini is unavailable — useful for UI testing."""
        return json.dumps({
            "summary": "Photosynthesis converts light energy into glucose using CO₂ and water.",
            "flashcards": [
                {
                    "term": "What is the overall equation for photosynthesis?",
                    "definition": "6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂",
                    "hint": "Think: carbon dioxide + water + sunlight → sugar + oxygen"
                },
                {
                    "term": "Where do the light-dependent reactions occur?",
                    "definition": "In the thylakoid membrane of the chloroplast.",
                    "hint": "Thylakoids are the flat disc-like structures inside chloroplasts."
                },
                {
                    "term": "What enzyme fixes CO₂ in the Calvin cycle?",
                    "definition": "RuBisCO (Ribulose-1,5-bisphosphate carboxylase/oxygenase)",
                    "hint": "Most abundant enzyme on Earth — it grabs CO₂ from the air."
                }
            ],
            "questions": [
                {
                    "question": "Which pigment absorbs light for photosynthesis?",
                    "options": ["Melanin", "Chlorophyll", "Haemoglobin", "Carotene"],
                    "correct_index": 1,
                    "explanation": "Chlorophyll absorbs red and blue light in the chloroplast."
                },
                {
                    "question": "What is released as a byproduct of photosynthesis?",
                    "options": ["Carbon dioxide", "Nitrogen", "Oxygen", "Glucose"],
                    "correct_index": 2,
                    "explanation": "Oxygen is released when water is split during light reactions (photolysis)."
                }
            ]
        })


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from text_extractor import TextExtractor
    ext = TextExtractor()
    ctx = ext.demo_text("photosynthesis")

    gen = GeminiFlashcardGenerator()  # reads GEMINI_API_KEY from env
    study_set = gen.generate(ctx, confusion_score=0.7)

    print(f"Topic: {study_set.topic}")
    print(f"Level: {study_set.confusion_level} | Difficulty: {study_set.difficulty}")
    print(f"\nSummary: {study_set.summary}\n")
    for fc in study_set.flashcards:
        print(fc)
        print()
    for q in study_set.questions:
        print(q)
        print()