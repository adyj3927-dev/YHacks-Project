# StudyBuddy Chrome Extension

Detects confusion and explains what's on your screen. Built at YHack 2026.

## Setup

1. **Add your Gemini API key**
   - Copy `config.example.js` → `config.js`
   - Paste your Gemini API key inside
   - `config.js` is gitignored — never commit it

2. **Load in Chrome**
   - Go to `chrome://extensions`
   - Enable **Developer Mode** (top right toggle)
   - Click **Load unpacked**
   - Select this folder

3. **Test it**
   - Navigate to any webpage
   - Click the StudyBuddy extension icon
   - Hit "Explain This Page" or "Generate Flashcards"

## Integration with Confusion Detector (Khwahish's module)

When her webcam detects confusion, send this message to the extension:

```js
chrome.runtime.sendMessage({ type: 'CONFUSION_DETECTED' }, (response) => {
  console.log(response.explanation);
});
```

## File Structure

```
manifest.json      — extension config + permissions
background.js      — service worker, handles Gemini API calls
content.js         — injected into pages, extracts text
popup.html/js      — the UI when you click the extension icon
config.js          — YOUR API KEY (gitignored)
.gitignore         — keeps config.js out of git
```

## Message Types

| Type | What it does |
|------|-------------|
| `CONFUSION_DETECTED` | Extracts page + asks Gemini to explain simply |
| `GENERATE_FLASHCARDS` | Extracts page + generates 5 flashcards as JSON |
| `EXTRACT_CONTENT` | Just returns raw extracted page content |
