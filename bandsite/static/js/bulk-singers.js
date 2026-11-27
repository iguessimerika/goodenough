// Song list: select several songs and add/remove singers for all of them at once.
(() => {
  const form = document.getElementById('bulk-form');
  if (!form) return;
  const boxes = Array.from(document.querySelectorAll('input[name="song_ids"][form="bulk-form"]'));
  const all = document.getElementById('bulk-all');
  const count = document.getElementById('bulk-count');
  const clear = document.getElementById('bulk-clear');

  function update() {
    const selected = boxes.filter((b) => b.checked).length;
    form.hidden = selected === 0;
    count.textContent = selected === 1 ? '1 song selected' : selected + ' songs selected';
    if (all) {
      all.checked = selected > 0 && selected === boxes.length;
      all.indeterminate = selected > 0 && selected < boxes.length;
    }
    boxes.forEach((b) => b.closest('.song-row').classList.toggle('is-selected', b.checked));
  }

  boxes.forEach((b) => b.addEventListener('change', update));
  if (all) {
    all.addEventListener('change', () => {
      boxes.forEach((b) => { b.checked = all.checked; });
      update();
    });
  }
  clear.addEventListener('click', () => {
    boxes.forEach((b) => { b.checked = false; });
    update();
  });
  form.addEventListener('submit', (event) => {
    if (!form.querySelector('input[name="singers"]:checked')) {
      event.preventDefault();
      count.textContent = 'Choose at least one singer first';
      form.querySelector('input[name="singers"]').focus();
    }
  });

  update();
})();
