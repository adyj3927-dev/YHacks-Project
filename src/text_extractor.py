"""
Module 2: Text Extractor
Extracts clean text from:
  - PDF files (via pdfminer)
  - Plain text / markdown files
  - Raw text strings (pasted content or from Chrome extension)

Returns a TextContext object with:
  - full_text     : entire extracted text
  - snippet       : most relevant ~500 word chunk
  - topic_keywords: top keywords guessed from content
  - source_type   : 'pdf' | 'text' | 'web'
"""

import re
import os
from dataclasses import dataclass, field
from typing import List
from collections import Counter


# ── Optional imports (graceful fallback) ─────────────────────────────────────
try:
    from pdfminer.high_level import extract_text as pdf_extract
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("[TextExtractor] pdfminer not installed — PDF support disabled. "
          "Run: pip install pdfminer.six")


# ─────────────────────────────────────────────────────────────────────────────
STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","are","was","were","be","been","being","have","has","had","do","does",
    "did","will","would","could","should","may","might","shall","can","this",
    "that","these","those","it","its","they","them","their","we","our","you",
    "your","he","she","his","her","i","me","my","not","from","as","by","also",
    "which","who","what","when","where","how","all","each","more","other",
    "than","then","so","if","about","into","up","out","after","before","over",
}


@dataclass
class TextContext:
    full_text: str        = ""
    snippet: str          = ""          # ~500 words around most-dense section
    topic_keywords: List[str] = field(default_factory=list)
    source_type: str      = "text"
    word_count: int       = 0
    char_count: int       = 0

    def summary(self) -> str:
        return (f"[{self.source_type.upper()}] "
                f"{self.word_count} words | "
                f"Topics: {', '.join(self.topic_keywords[:5])}")


# ── Core extractor ────────────────────────────────────────────────────────────
class TextExtractor:

    SNIPPET_WORDS = 500    # words per snippet sent to AI
    TOP_KEYWORDS  = 10

    # ── Public API ────────────────────────────────────────────────────────────

    def from_pdf(self, path: str) -> TextContext:
        if not PDF_AVAILABLE:
            return self._error_ctx("pdfminer not installed")
        if not os.path.exists(path):
            return self._error_ctx(f"File not found: {path}")
        try:
            raw = pdf_extract(path)
            return self._build_context(raw, source_type="pdf")
        except Exception as e:
            return self._error_ctx(str(e))

    def from_text(self, text: str, source_type: str = "text") -> TextContext:
        """Accept raw text string (from Chrome extension, paste, etc.)."""
        return self._build_context(text, source_type=source_type)

    def from_file(self, path: str) -> TextContext:
        """Load a plain .txt / .md file."""
        if not os.path.exists(path):
            return self._error_ctx(f"File not found: {path}")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        return self._build_context(raw, source_type="text")

    # ── Demo: preloaded lesson text (for hackathon MVP) ───────────────────────
    def demo_text(self, topic: str = "photosynthesis") -> TextContext:
        """Returns a canned lesson snippet for offline demo."""
        lessons = {
            "photosynthesis": """
                Photosynthesis is the process by which plants, algae, and some bacteria
                convert light energy—usually from the sun—into chemical energy stored as
                glucose. The overall chemical equation is:
                6CO₂ + 6H₂O + light energy → C₆H₁₂O₆ + 6O₂

                The process occurs in two main stages:
                1. Light-dependent reactions (in the thylakoid membrane):
                   Water molecules are split (photolysis), releasing oxygen as a byproduct.
                   ATP and NADPH are produced using light energy.
                2. Light-independent reactions / Calvin Cycle (in the stroma):
                   CO₂ is fixed into organic molecules using the ATP and NADPH from stage 1.
                   The enzyme RuBisCO catalyses the fixation of CO₂ onto RuBP.

                Factors that affect the rate of photosynthesis:
                - Light intensity: more light → faster rate (up to a saturation point)
                - CO₂ concentration: higher CO₂ → faster rate
                - Temperature: optimal ~25°C; too high denatures enzymes
                - Water availability: required as a raw material

                Chlorophyll, the green pigment in chloroplasts, absorbs mainly red and
                blue wavelengths and reflects green, which is why plants appear green.
            """,
            "newton_laws": """
                Newton's Three Laws of Motion form the foundation of classical mechanics.

                First Law (Law of Inertia): An object at rest stays at rest and an object
                in motion stays in motion with the same speed and direction unless acted
                upon by an unbalanced force. This means that objects naturally resist
                changes to their state of motion.

                Second Law (F = ma): The acceleration of an object depends on the net force
                acting on it and its mass. Force equals mass times acceleration (F = ma).
                A larger force produces greater acceleration; a larger mass requires more
                force to achieve the same acceleration.

                Third Law (Action-Reaction): For every action there is an equal and opposite
                reaction. When object A exerts a force on object B, object B simultaneously
                exerts a force equal in magnitude and opposite in direction on object A.

                Applications: rockets (exhaust pushes back → rocket moves forward),
                walking (foot pushes ground → ground pushes foot), swimming strokes.
            """,
        }
        text = lessons.get(topic, lessons["photosynthesis"])
        ctx = self._build_context(text, source_type="demo")
        return ctx

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_context(self, raw: str, source_type: str) -> TextContext:
        cleaned    = self._clean(raw)
        words      = cleaned.split()
        keywords   = self._extract_keywords(cleaned)
        snippet    = self._best_snippet(cleaned, keywords)

        return TextContext(
            full_text=cleaned,
            snippet=snippet,
            topic_keywords=keywords,
            source_type=source_type,
            word_count=len(words),
            char_count=len(cleaned),
        )

    def _clean(self, text: str) -> str:
        # Remove excessive whitespace / control chars
        text = re.sub(r'\r\n|\r', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'[^\x20-\x7E\n°²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉→←↔≈≠≤≥αβγδεζηθλμπρστφψω]', ' ', text)
        return text.strip()

    def _extract_keywords(self, text: str) -> List[str]:
        tokens = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        freq   = Counter(t for t in tokens if t not in STOPWORDS)
        return [w for w, _ in freq.most_common(self.TOP_KEYWORDS)]

    def _best_snippet(self, text: str, keywords: List[str]) -> str:
        """Sliding window: find the ~500-word chunk with highest keyword density."""
        words = text.split()
        if len(words) <= self.SNIPPET_WORDS:
            return text

        kw_set  = set(keywords)
        best_score, best_start = 0, 0
        step = max(1, self.SNIPPET_WORDS // 4)

        for i in range(0, len(words) - self.SNIPPET_WORDS, step):
            chunk = words[i: i + self.SNIPPET_WORDS]
            score = sum(1 for w in chunk if w.lower() in kw_set)
            if score > best_score:
                best_score, best_start = score, i

        return " ".join(words[best_start: best_start + self.SNIPPET_WORDS])

    @staticmethod
    def _error_ctx(msg: str) -> TextContext:
        return TextContext(
            full_text=f"[ERROR] {msg}",
            snippet=f"[ERROR] {msg}",
            source_type="error"
        )


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ext = TextExtractor()

    # Test with demo text
    ctx = ext.demo_text("photosynthesis")
    print(ctx.summary())
    print("\nSnippet preview (first 300 chars):")
    print(ctx.snippet[:300])
    print("\nKeywords:", ctx.topic_keywords)