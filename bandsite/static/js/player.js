// YouTube player with speed choice and a loop for one section (for practising).
(() => {
  const holder = document.getElementById('yt-player');
  if (!holder) return;
  const videoId = holder.dataset.videoId;
  const controls = document.getElementById('player-controls');
  const hint = document.getElementById('loop-hint');
  const startTime = document.getElementById('loop-a-time');
  const endTime = document.getElementById('loop-b-time');
  const toggle = document.getElementById('loop-toggle');

  let player = null;
  let start = null;
  let end = null;
  let looping = false;
  let timer = null;

  const fmt = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m + ':' + String(s).padStart(2, '0');
  };
  const say = (text) => { hint.textContent = text; };

  function plainVideo() {
    // Fallback if the YouTube API doesn't load: a normal player without the extras.
    const iframe = document.createElement('iframe');
    iframe.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(videoId) + '?rel=0&playsinline=1';
    iframe.title = 'YouTube video';
    iframe.allow = 'encrypted-media; picture-in-picture; fullscreen';
    iframe.allowFullscreen = true;
    iframe.referrerPolicy = 'strict-origin-when-cross-origin';
    holder.replaceWith(iframe);
  }

  function watch() {
    clearInterval(timer);
    timer = setInterval(() => {
      if (!looping || start === null || end === null || !player || !player.getCurrentTime) return;
      const t = player.getCurrentTime();
      if (t >= end || t < start - 0.5) player.seekTo(start, true);
    }, 150);
  }

  function loopOff() {
    looping = false;
    toggle.setAttribute('aria-pressed', 'false');
  }

  function ready() {
    controls.hidden = false;
    const available = player.getAvailablePlaybackRates ? player.getAvailablePlaybackRates() : [];
    controls.querySelectorAll('[data-rate]').forEach((button) => {
      const rate = parseFloat(button.dataset.rate);
      if (available.length && !available.includes(rate)) button.disabled = true;
      button.addEventListener('click', () => {
        player.setPlaybackRate(rate);
        controls.querySelectorAll('[data-rate]').forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
      });
    });

    document.getElementById('loop-a').addEventListener('click', () => {
      start = player.getCurrentTime();
      startTime.textContent = fmt(start);
      if (end !== null && end <= start) { end = null; endTime.textContent = '–'; loopOff(); }
      say('Start set. Play to the end of the section, then set the end.');
    });
    document.getElementById('loop-b').addEventListener('click', () => {
      const t = player.getCurrentTime();
      if (start === null || t <= start) { say('Set the start first, then an end after it.'); return; }
      end = t;
      endTime.textContent = fmt(end);
      say('End set. Press Loop to repeat the section.');
    });
    toggle.addEventListener('click', () => {
      if (looping) { loopOff(); say('Loop off.'); return; }
      if (start === null || end === null) { say('For the loop you need a start and an end.'); return; }
      looping = true;
      toggle.setAttribute('aria-pressed', 'true');
      player.seekTo(start, true);
      player.playVideo();
      say('Looping ' + fmt(start) + ' to ' + fmt(end) + '.');
    });
    document.getElementById('loop-clear').addEventListener('click', () => {
      start = null; end = null;
      startTime.textContent = '–'; endTime.textContent = '–';
      loopOff();
      say('Section cleared.');
    });
    watch();
  }

  window.onYouTubeIframeAPIReady = () => {
    player = new YT.Player('yt-player', {
      host: 'https://www.youtube-nocookie.com',
      videoId,
      width: '100%',
      height: '100%',
      playerVars: { rel: 0, playsinline: 1 },
      events: { onReady: ready },
    });
  };

  const script = document.createElement('script');
  script.src = 'https://www.youtube.com/iframe_api';
  script.onerror = plainVideo;
  document.head.appendChild(script);
  setTimeout(() => { if (!player) plainVideo(); }, 6000);
})();
