// popup.js

const explainBtn = document.getElementById('explainBtn');
const flashcardBtn = document.getElementById('flashcardBtn');
const extractBtn = document.getElementById('extractBtn');
const outputBox = document.getElementById('outputBox');
const loader = document.getElementById('loader');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

function setLoading(isLoading) {
  loader.classList.toggle('visible', isLoading);
  outputBox.classList.toggle('visible', !isLoading);
  explainBtn.disabled = isLoading;
  flashcardBtn.disabled = isLoading;
  extractBtn.disabled = isLoading;
  statusDot.classList.toggle('active', isLoading);
  statusText.textContent = isLoading ? 'Working...' : 'Ready';
}

function showText(text) {
  outputBox.innerHTML = `<p style="white-space:pre-wrap">${text}</p>`;
  outputBox.classList.add('visible');
}

function showFlashcards(cards) {
  outputBox.innerHTML = cards.map(c => `
    <div class="flashcard">
      <strong>Q</strong>${c.front}
      <strong style="margin-top:6px">A</strong>${c.back}
    </div>
  `).join('');
  outputBox.classList.add('visible');
}

// ── Explain current page ──────────────────────────────────────────────────────
explainBtn.addEventListener('click', async () => {
  setLoading(true);
  outputBox.innerHTML = '';
  try {
    const response = await chrome.runtime.sendMessage({ type: 'CONFUSION_DETECTED' });
    if (response.success) {
      showText(response.explanation);
    } else {
      showText(`Error: ${response.error}`);
    }
  } catch (err) {
    showText(`Something went wrong: ${err.message}`);
  } finally {
    setLoading(false);
  }
});

// ── Generate flashcards ───────────────────────────────────────────────────────
flashcardBtn.addEventListener('click', async () => {
  setLoading(true);
  outputBox.innerHTML = '';
  try {
    const response = await chrome.runtime.sendMessage({ type: 'GENERATE_FLASHCARDS' });
    if (response.success) {
      showFlashcards(response.flashcards);
    } else {
      showText(`Error: ${response.error}`);
    }
  } catch (err) {
    showText(`Something went wrong: ${err.message}`);
  } finally {
    setLoading(false);
  }
});

// ── Preview extracted content ─────────────────────────────────────────────────
extractBtn.addEventListener('click', async () => {
  setLoading(true);
  outputBox.innerHTML = '';
  try {
    const response = await chrome.runtime.sendMessage({ type: 'EXTRACT_CONTENT' });
    if (response.success) {
      const { title, url, content } = response.data;
      showText(`📄 ${title}\n🔗 ${url}\n\n${content.slice(0, 500)}...`);
    } else {
      showText(`Error: ${response.error}`);
    }
  } catch (err) {
    showText(`Something went wrong: ${err.message}`);
  } finally {
    setLoading(false);
  }
});
