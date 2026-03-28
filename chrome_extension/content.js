// content.js — injected into every page
// Extracts readable text content from the current tab

function extractPageContent() {
  // Remove noisy elements before extracting
  const noisyTags = ['script', 'style', 'noscript', 'svg', 'img', 'nav', 'footer', 'header'];
  
  // Clone body so we don't mutate the real page
  const bodyClone = document.body.cloneNode(true);
  noisyTags.forEach(tag => {
    bodyClone.querySelectorAll(tag).forEach(el => el.remove());
  });

  // Get clean text
  const rawText = bodyClone.innerText || bodyClone.textContent || '';

  // Collapse whitespace and trim
  const cleanText = rawText
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 8000); // cap at 8000 chars to stay within API limits

  return {
    url: window.location.href,
    title: document.title,
    content: cleanText,
    timestamp: Date.now()
  };
}

// Listen for messages from popup or background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'EXTRACT_CONTENT') {
    const pageData = extractPageContent();
    sendResponse({ success: true, data: pageData });
  }
  return true; // keep message channel open for async
});
