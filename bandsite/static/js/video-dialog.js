(() => {
  const dialog = document.getElementById('video-dialog');
  const frame = document.getElementById('video-frame');
  const title = document.getElementById('video-title');
  if (!dialog || !frame) return;

  function close() {
    frame.src = 'about:blank';
    if (dialog.open) dialog.close();
  }

  document.querySelectorAll('[data-video]').forEach((button) => {
    button.addEventListener('click', () => {
      title.textContent = button.dataset.title || '';
      frame.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(button.dataset.video) + '?autoplay=1&rel=0&playsinline=1';
      dialog.showModal();
    });
  });
  document.getElementById('video-close').addEventListener('click', close);
  dialog.addEventListener('close', () => { frame.src = 'about:blank'; });
  dialog.addEventListener('click', (e) => { if (e.target === dialog) close(); });
})();
