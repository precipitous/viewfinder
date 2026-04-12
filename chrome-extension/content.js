// Viewfinder content script - adds a "Summarize" button to YouTube video pages

(function () {
  'use strict';

  let panel = null;

  function getVideoUrl() {
    return window.location.href;
  }

  function createPanel() {
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = 'viewfinder-panel';
    panel.innerHTML = `
      <button class="vf-close" id="vf-close">&times;</button>
      <h3>Viewfinder</h3>
      <div class="vf-meta" id="vf-meta"></div>
      <div class="vf-summary" id="vf-summary"></div>
    `;
    document.body.appendChild(panel);
    document.getElementById('vf-close').addEventListener('click', () => {
      panel.classList.remove('visible');
    });
    return panel;
  }

  function showPanel(meta, summary) {
    const p = createPanel();
    document.getElementById('vf-meta').textContent = meta;
    document.getElementById('vf-summary').innerHTML = summary;
    p.classList.add('visible');
  }

  function showStatus(msg) {
    const p = createPanel();
    document.getElementById('vf-meta').textContent = '';
    document.getElementById('vf-summary').innerHTML = `<div class="vf-status">${msg}</div>`;
    p.classList.add('visible');
  }

  async function summarize() {
    const btn = document.getElementById('viewfinder-btn');
    if (!btn || btn.classList.contains('loading')) return;

    btn.classList.add('loading');
    btn.textContent = 'Summarizing...';
    showStatus('Connecting to Viewfinder server...');

    try {
      const settings = await new Promise((resolve) => {
        chrome.storage.sync.get(['vf_server', 'vf_apikey'], resolve);
      });

      const server = settings.vf_server || 'http://localhost:8080';
      const apikey = settings.vf_apikey || '';

      const url = getVideoUrl();

      showStatus('Fetching transcript and generating summary...');

      const body = { url };
      if (apikey) body.api_key = apikey;

      const resp = await fetch(`${server}/api/ingest`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apikey ? { 'X-API-Key': apikey } : {}),
        },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        showStatus(`Error: ${err.detail || resp.statusText}`);
        return;
      }

      const data = await resp.json();
      const meta = [
        data.channel,
        `${data.word_count} words`,
        data.language,
        data.model,
      ].filter(Boolean).join(' | ');

      if (data.summary) {
        showPanel(meta, data.summary.replace(/\n/g, '<br>'));
      } else {
        showPanel(meta, `<em>Transcript only (${data.source})</em>`);
      }
    } catch (e) {
      showStatus(`Failed to connect: ${e.message}`);
    } finally {
      btn.classList.remove('loading');
      btn.textContent = 'Summarize';
    }
  }

  function injectButton() {
    if (document.getElementById('viewfinder-btn')) return;

    // Find the YouTube actions bar (subscribe button area)
    const target = document.querySelector(
      '#top-row #actions, ytd-menu-renderer.ytd-watch-metadata'
    );
    if (!target) return;

    const btn = document.createElement('button');
    btn.id = 'viewfinder-btn';
    btn.textContent = 'Summarize';
    btn.addEventListener('click', summarize);
    target.prepend(btn);
  }

  // YouTube is an SPA - watch for navigation
  const observer = new MutationObserver(() => {
    if (window.location.pathname === '/watch') {
      setTimeout(injectButton, 1000);
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Initial injection
  if (window.location.pathname === '/watch') {
    setTimeout(injectButton, 1500);
  }
})();
