// background.js — service worker
// Handles tab extraction + Gemini API calls

// 🔑 Paste your Gemini API key here
const GEMINI_API_KEY = 'AIzaSyD-nL8LfabOZsgpc8tPkCGFaB0rLBucQ44';

const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`;

// ── Get content from active tab ──────────────────────────────────────────────
async function extractActiveTabContent() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error('No active tab found');

  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      // Inline extraction (content script may not always be ready)
      const noisyTags = ['script', 'style', 'noscript', 'svg', 'nav', 'footer'];
      const clone = document.body.cloneNode(true);
      noisyTags.forEach(tag => clone.querySelectorAll(tag).forEach(el => el.remove()));
      const text = (clone.innerText || clone.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 8000);
      return { url: location.href, title: document.title, content: text };
    }
  });

  return results[0]?.result;
}

// ── Call Gemini API ───────────────────────────────────────────────────────────
async function callGemini(prompt) {
  const res = await fetch(GEMINI_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.4, maxOutputTokens: 1024 }
    })
  });

  if (!res.ok) throw new Error(`Gemini error: ${res.status}`);
  const data = await res.json();
  return data.candidates?.[0]?.content?.parts?.[0]?.text || 'No response';
}

// ── Explain what's on screen (called when confusion detected) ─────────────────
async function explainScreen() {
  const page = await extractActiveTabContent();

  const prompt = `
You are a helpful tutor. A student is viewing this webpage and looks confused.

Page title: ${page.title}
Page URL: ${page.url}
Page content (excerpt):
${page.content}

Please:
1. In 2-3 sentences, explain what this page is about in simple terms.
2. Identify the 1-2 concepts that might be confusing.
3. Give a simple, clear explanation of those concepts.

Keep your response friendly, concise, and easy to understand.
  `.trim();

  return await callGemini(prompt);
}

// ── Generate flashcards from page content ────────────────────────────────────
async function generateFlashcards() {
  const page = await extractActiveTabContent();

  const prompt = `
You are a study assistant. Based on this webpage, generate 5 flashcards to help a student study.

Page title: ${page.title}
Content:
${page.content}

Return ONLY a valid JSON array (no markdown, no extra text) in this format:
[
  { "front": "Question or concept", "back": "Answer or explanation" },
  ...
]
  `.trim();

  const raw = await callGemini(prompt);

  // Strip markdown fences if Gemini adds them
  const cleaned = raw.replace(/```json|```/g, '').trim();
  return JSON.parse(cleaned);
}

// ── Message handler (from popup or confusion detector) ────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CONFUSION_DETECTED') {
    explainScreen()
      .then(explanation => sendResponse({ success: true, explanation }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === 'GENERATE_FLASHCARDS') {
    generateFlashcards()
      .then(flashcards => sendResponse({ success: true, flashcards }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === 'EXTRACT_CONTENT') {
    extractActiveTabContent()
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
