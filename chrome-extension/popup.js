// Save/load Viewfinder settings
document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.sync.get(['vf_server', 'vf_apikey'], (data) => {
    document.getElementById('server').value = data.vf_server || 'http://localhost:8080';
    document.getElementById('apikey').value = data.vf_apikey || '';
  });

  document.getElementById('save').addEventListener('click', () => {
    const server = document.getElementById('server').value.trim().replace(/\/$/, '');
    const apikey = document.getElementById('apikey').value.trim();
    chrome.storage.sync.set({ vf_server: server, vf_apikey: apikey }, () => {
      const status = document.getElementById('status');
      status.textContent = 'Settings saved!';
      status.classList.add('saved');
      setTimeout(() => { status.textContent = ''; }, 2000);
    });
  });
});
