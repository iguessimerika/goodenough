// "New song": asks for a YouTube link first and fills in title, artist and link.
(() => {
  const dialog = document.getElementById('yt-dialog');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const form = document.getElementById('yt-form');
  const input = document.getElementById('yt-url');
  const error = document.getElementById('yt-error');
  const submit = document.getElementById('yt-submit');
  const fields = {
    title: document.getElementById('title'),
    artist: document.getElementById('artist'),
    youtube: document.getElementById('youtube_url'),
  };

  function showMessage(text, kind) {
    const main = document.querySelector('main.content');
    let list = main.querySelector('.flashes');
    if (!list) {
      list = document.createElement('ul');
      list.className = 'flashes';
      list.setAttribute('role', 'status');
      main.prepend(list);
    }
    const item = document.createElement('li');
    item.className = 'flash ' + kind;
    item.textContent = text;
    list.append(item);
  }

  function finish(focusField) {
    dialog.close();
    (focusField || fields.title).focus();
  }

  function setBusy(busy) {
    submit.disabled = busy;
    input.disabled = busy;
    submit.textContent = busy ? 'Checking…' : 'Continue';
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const url = input.value.trim();
    error.hidden = true;
    if (!url) {
      error.textContent = 'Paste a link, or choose Skip.';
      error.hidden = false;
      input.focus();
      return;
    }

    setBusy(true);
    let data = null;
    try {
      const response = await fetch(dialog.dataset.lookup + '?url=' + encodeURIComponent(url), {
        headers: { Accept: 'application/json' },
      });
      if (response.ok) data = await response.json();
    } catch (e) {
      data = null; // network trouble: treated like "no details found"
    }
    setBusy(false);

    if (data && data.valid === false) {
      error.textContent = "I don't recognise that YouTube link. Copy the address from the address bar or use Share.";
      error.hidden = false;
      input.focus();
      return;
    }

    fields.youtube.value = url;
    if (data && data.found) {
      fields.title.value = data.title || '';
      fields.artist.value = data.artist || '';
      showMessage('Title and artist were filled in from YouTube. Please check them before saving.', 'ok');
      finish(fields.title);
    } else {
      showMessage("Couldn't get the details from YouTube (the video may be private or unavailable). The link is filled in – please enter title and artist yourself.", 'error');
      finish(fields.title);
    }
  });

  document.getElementById('yt-skip').addEventListener('click', () => finish(fields.title));
  dialog.addEventListener('cancel', () => setTimeout(() => fields.title.focus(), 0));

  dialog.showModal();
  input.focus();
})();
