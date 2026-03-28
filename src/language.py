"""
language_manager.py — Multilingual support for StudyBuddy
Uses Gemini to translate flashcards, MCQs, UI, and alerts.

Supports: English, Hindi, Urdu, Arabic (+ any other language Gemini knows)
Auto-detects browser/system language, allows manual override.
"""

import os
import json
import re
from dataclasses import dataclass
from typing import Optional

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# ── Supported languages ───────────────────────────────────────────────────────

LANGUAGES = {
    "en": {"name": "English",    "native": "English",    "rtl": False, "flag": "🇺🇸"},
    "hi": {"name": "Hindi",      "native": "हिन्दी",       "rtl": False, "flag": "🇮🇳"},
    "ur": {"name": "Urdu",       "native": "اردو",         "rtl": True,  "flag": "🇵🇰"},
    "ar": {"name": "Arabic",     "native": "العربية",      "rtl": True,  "flag": "🇸🇦"},
    "fr": {"name": "French",     "native": "Français",    "rtl": False, "flag": "🇫🇷"},
    "es": {"name": "Spanish",    "native": "Español",     "rtl": False, "flag": "🇪🇸"},
    "zh": {"name": "Mandarin",   "native": "中文",          "rtl": False, "flag": "🇨🇳"},
    "pt": {"name": "Portuguese", "native": "Português",   "rtl": False, "flag": "🇧🇷"},
}

# UI strings — translated versions fetched at runtime
UI_STRINGS = {
    "en": {
        "app_title":        "StudyBuddy",
        "tagline":          "Your AI-powered study companion",
        "confusion_low":    "Calm",
        "confusion_medium": "Uncertain",
        "confusion_high":   "Confused",
        "confusion_label":  "Confusion level",
        "flashcard_title":  "Flashcards",
        "question_title":   "Practice questions",
        "got_it":           "✅ Got it!",
        "next":             "Next →",
        "prev":             "← Prev",
        "submit":           "Submit answer",
        "correct":          "Correct!",
        "incorrect":        "Not quite.",
        "correct_answer":   "Correct answer",
        "close":            "✕ Close",
        "studying_now":     "What you're studying right now",
        "start":            "▶ Start detector",
        "stop":             "⏹ Stop detector",
        "spike_count":      "Confusion spikes detected",
        "focus_alert_title":"Focus check!",
        "focus_alert_body": "You switched away. Come back — your session is running.",
        "dismiss":          "I'm back — dismiss",
        "confusion_alert":  "Confusion detected! Generating flashcards for you...",
        "hint_label":       "💡 Hint",
        "session_stats":    "Session stats",
        "time_studied":     "time studied",
        "cards_done":       "cards done",
        "focus_alerts":     "focus alerts",
    }
}

# RTL CSS to inject when language is right-to-left
RTL_CSS = """
<style>
body, .stMarkdown, .stText, input, textarea, button { direction: rtl; text-align: right; }
.sidebar .sidebar-content { direction: rtl; }
</style>
"""


# ── Translation cache (avoid re-translating same strings) ─────────────────────
_translation_cache: dict = {}


@dataclass
class TranslatedStudySet:
    flashcards: list
    questions:  list
    summary:    str
    language:   str


# ── Main language manager ─────────────────────────────────────────────────────

class LanguageManager:

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.client = None
        if GENAI_AVAILABLE and key:
            self.client = genai.Client(api_key=key)
        self.current_lang = "en"

    # ── Language detection ────────────────────────────────────────────────────

    def detect_from_text(self, text: str) -> str:
        """
        Detect language from a text sample using Gemini.
        Returns a language code like 'hi', 'ur', 'ar', 'en'.
        Falls back to 'en' if detection fails.
        """
        if not self.client or not text.strip():
            return "en"

        prompt = f"""Detect the language of this text and return ONLY the ISO 639-1 
two-letter language code (e.g. 'en', 'hi', 'ur', 'ar', 'fr', 'es').
No explanation, just the code.

Text: {text[:200]}"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            code = response.text.strip().lower()[:2]
            return code if code in LANGUAGES else "en"
        except Exception:
            return "en"

    def detect_from_browser(self, accept_language_header: str) -> str:
        """
        Parse browser Accept-Language header.
        e.g. 'hi-IN,hi;q=0.9,en;q=0.8' → 'hi'
        """
        if not accept_language_header:
            return "en"
        first = accept_language_header.split(",")[0].split(";")[0].strip()
        code  = first.split("-")[0].lower()
        return code if code in LANGUAGES else "en"

    # ── Study set translation ─────────────────────────────────────────────────

    def translate_study_set(self, study_set, target_lang: str) -> TranslatedStudySet:
        """
        Translates flashcards, MCQs and summary into target_lang.
        Returns a TranslatedStudySet.
        """
        if target_lang == "en" or not self.client:
            return TranslatedStudySet(
                flashcards=study_set.flashcards,
                questions=study_set.questions,
                summary=study_set.summary,
                language=target_lang,
            )

        lang_name = LANGUAGES.get(target_lang, {}).get("name", target_lang)

        # Build a single batch translation request
        payload = {
            "summary": study_set.summary,
            "flashcards": [
                {"term": fc.term, "definition": fc.definition, "hint": fc.hint}
                for fc in study_set.flashcards
            ],
            "questions": [
                {
                    "question":     q.question,
                    "options":      q.options,
                    "explanation":  q.explanation,
                }
                for q in study_set.questions
            ],
        }

        prompt = f"""Translate the following JSON content into {lang_name}.
Preserve the exact JSON structure. Translate all string values.
Do NOT translate: JSON keys, numbers, correct_index values.
Return ONLY valid JSON, no markdown fences.

{json.dumps(payload, ensure_ascii=False)}"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            raw     = re.sub(r'```(?:json)?', '', response.text).strip().strip('`')
            data    = json.loads(raw)
            return self._build_translated_set(data, study_set, target_lang)
        except Exception as e:
            print(f"[LanguageManager] Translation failed: {e}")
            return TranslatedStudySet(
                flashcards=study_set.flashcards,
                questions=study_set.questions,
                summary=study_set.summary,
                language="en",
            )

    def _build_translated_set(self, data: dict, original, lang: str) -> TranslatedStudySet:
        from flashcard_generator import Flashcard, MCQuestion

        flashcards = []
        for i, fc_data in enumerate(data.get("flashcards", [])):
            orig = original.flashcards[i] if i < len(original.flashcards) else None
            flashcards.append(Flashcard(
                term=fc_data.get("term", orig.term if orig else ""),
                definition=fc_data.get("definition", orig.definition if orig else ""),
                hint=fc_data.get("hint", orig.hint if orig else ""),
            ))

        questions = []
        for i, q_data in enumerate(data.get("questions", [])):
            orig = original.questions[i] if i < len(original.questions) else None
            opts = q_data.get("options", orig.options if orig else [])
            if len(opts) != 4:
                opts = (opts + ["—", "—", "—", "—"])[:4]
            questions.append(MCQuestion(
                question=q_data.get("question", orig.question if orig else ""),
                options=opts,
                correct_index=orig.correct_index if orig else 0,
                explanation=q_data.get("explanation", orig.explanation if orig else ""),
            ))

        return TranslatedStudySet(
            flashcards=flashcards,
            questions=questions,
            summary=data.get("summary", original.summary),
            language=lang,
        )

    # ── UI string translation ─────────────────────────────────────────────────

    def get_ui_strings(self, lang: str) -> dict:
        """
        Returns translated UI strings for the given language.
        Caches results so we only call Gemini once per language.
        """
        if lang == "en":
            return UI_STRINGS["en"]
        if lang in UI_STRINGS:
            return UI_STRINGS[lang]
        if lang in _translation_cache:
            return _translation_cache[lang]

        if not self.client:
            return UI_STRINGS["en"]

        lang_name = LANGUAGES.get(lang, {}).get("name", lang)
        prompt = f"""Translate these UI strings into {lang_name}.
Return ONLY valid JSON with the same keys. Keep emojis as-is.

{json.dumps(UI_STRINGS["en"], ensure_ascii=False)}"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            raw      = re.sub(r'```(?:json)?', '', response.text).strip().strip('`')
            strings  = json.loads(raw)
            _translation_cache[lang] = strings
            UI_STRINGS[lang]         = strings
            return strings
        except Exception as e:
            print(f"[LanguageManager] UI translation failed: {e}")
            return UI_STRINGS["en"]

    # ── Confusion alert translation ───────────────────────────────────────────

    def translate_alert(self, message: str, lang: str) -> str:
        if lang == "en" or not self.client:
            return message
        cache_key = f"{lang}:{message}"
        if cache_key in _translation_cache:
            return _translation_cache[cache_key]
        lang_name = LANGUAGES.get(lang, {}).get("name", lang)
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Translate to {lang_name}. Return only the translation:\n{message}",
            )
            translated = response.text.strip()
            _translation_cache[cache_key] = translated
            return translated
        except Exception:
            return message

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def is_rtl(lang: str) -> bool:
        return LANGUAGES.get(lang, {}).get("rtl", False)

    @staticmethod
    def get_language_options() -> list:
        """Returns list of (code, display_label) for dropdown."""
        return [
            (code, f"{info['flag']} {info['native']} ({info['name']})")
            for code, info in LANGUAGES.items()
        ]


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mgr = LanguageManager()

    print("Language options:")
    for code, label in mgr.get_language_options():
        print(f"  {code}: {label}")

    print("\nDetecting language of 'यह एक परीक्षण है':")
    print(" →", mgr.detect_from_text("यह एक परीक्षण है"))

    print("\nFetching Hindi UI strings:")
    strings = mgr.get_ui_strings("hi")
    print(f"  got_it: {strings.get('got_it')}")
    print(f"  confusion_high: {strings.get('confusion_high')}")