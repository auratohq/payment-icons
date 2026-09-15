const $ = (id) => document.getElementById(id);
const PAGE = 60;
const state = { category: 'payment-methods', query: '', source: 'all', visible: PAGE, entries: [], index: null, selected: null };
const number = new Intl.NumberFormat('en-US');
const normalize = (value) => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const generated = (item) => item.source.kind.includes('generated');
const titleCase = (value) => value.replaceAll('_', ' ');
const categoryName = (id) => state.index.categories.find((c) => c.id === id)?.name || id;

async function json(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Could not load ${path} (${response.status}).`);
  return response.json();
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function toast(message) {
  $('toast').textContent = message;
  $('toast').classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('toast').classList.remove('visible'), 2400);
}

function renderCategories() {
  const categories = [{ id: 'all', name: 'All assets', count: state.index.assetCount }, ...state.index.categories];
  $('categories').replaceChildren(...categories.map((category) => {
    const button = element('button', 'category');
    button.type = 'button';
    button.dataset.category = category.id;
    button.setAttribute('aria-pressed', String(state.category === category.id));
    button.append(element('span', '', category.name), element('span', 'count', number.format(category.count)));
    button.addEventListener('click', () => {
      state.category = category.id;
      state.visible = PAGE;
      renderCategories();
      render();
    });
    return button;
  }));
}

function openDetail(item) {
  state.selected = item;
  $('detail-name').textContent = item.name;
  $('detail-category').textContent = categoryName(item.category).toUpperCase();
  $('detail-image').src = item.path;
  $('detail-image').alt = item.name;
  $('detail-format').textContent = `PNG · ${item.width} × ${item.height} · ${(item.bytes / 1024).toFixed(1)} KB`;
  $('detail-kind').textContent = titleCase(item.source.kind);
  $('detail-source-row').hidden = !item.source.url;
  if (item.source.url) $('detail-source').href = item.source.url;
  else $('detail-source').removeAttribute('href');
  $('detail-path').value = item.path;
  $('detail-sha').textContent = item.sha256;
  $('download-icon').href = item.path;
  $('download-icon').download = item.path.split('/').at(-1);
  $('detail').showModal();
}

function tile(item) {
  const button = element('button', 'tile' + (item.category === 'cards' ? ' card-art' : ''));
  button.type = 'button';
  button.setAttribute('aria-label', `View ${item.name}`);
  const preview = element('span', 'preview-surface');
  const image = element('img');
  image.src = item.path;
  image.alt = '';
  image.loading = 'lazy';
  image.decoding = 'async';
  image.width = item.width;
  image.height = item.height;
  image.addEventListener('error', () => {
    image.hidden = true;
    preview.append(element('span', 'tile-meta', 'Preview unavailable'));
  }, { once: true });
  preview.append(image);
  const text = element('span', 'tile-text');
  text.append(element('span', 'tile-name', item.name), element('span', 'tile-meta', item.path.split('/').at(-1)));
  button.append(preview, text);
  button.addEventListener('click', () => openDetail(item));
  return button;
}

function render() {
  const query = normalize(state.query.trim());
  const results = state.entries.filter((item) =>
    (state.category === 'all' || item.category === state.category) &&
    (!query || item.search.includes(query)) &&
    (state.source === 'all' || generated(item) === (state.source === 'generated'))
  );
  $('category-title').textContent = state.category === 'all' ? 'All assets' : categoryName(state.category);
  const shown = Math.min(state.visible, results.length);
  $('result-count').textContent = `${number.format(results.length)} assets · ${shown} shown`;
  $('grid').replaceChildren(...results.slice(0, shown).map(tile));
  $('empty').hidden = results.length !== 0;
  $('load-more').hidden = shown >= results.length;
  $('load-more').textContent = `Show ${Math.min(PAGE, results.length - shown)} more ↓`;
  const params = new URLSearchParams();
  if (state.category !== 'payment-methods') params.set('category', state.category);
  if (state.query) params.set('q', state.query);
  if (state.source !== 'all') params.set('source', state.source);
  history.replaceState(null, '', location.pathname + (params.size ? `?${params}` : '') + location.hash);
}

async function init() {
  try {
    if (location.protocol === 'file:') throw new Error('Start a local server: python -m http.server 8000, then open http://localhost:8000.');
    state.index = await json('catalog.json');
    const index = state.index;
    $('stats').replaceChildren(...[[index.primaryIconCount, 'icons'], [index.cardCount, 'cards'], [index.categories.length, 'categories']].map(([count, label]) => {
      const span = element('span');
      span.append(element('strong', '', number.format(count)), document.createTextNode(label));
      return span;
    }));
    const batches = await Promise.all(index.categories.map((category) => json(category.path)));
    state.entries = batches.flat().map((item) => ({ ...item, search: normalize(`${item.name} ${(item.aliases || []).join(' ')} ${item.path} ${item.category}`) }));
    state.entries.sort((a, b) => a.name.localeCompare(b.name, 'en') || a.id.localeCompare(b.id));
    const params = new URLSearchParams(location.search);
    const category = params.get('category');
    if (category === 'all' || index.categories.some((item) => item.id === category)) state.category = category;
    state.query = params.get('q') || '';
    if (['generated', 'other'].includes(params.get('source'))) state.source = params.get('source');
    $('search').value = state.query;
    $('source-filter').value = state.source;
    renderCategories();
    render();
    $('search').addEventListener('input', (event) => {
      state.query = event.target.value;
      // A search from the input searches the full collection; category selection can narrow it.
      state.category = 'all';
      state.visible = PAGE;
      renderCategories();
      render();
    });
    $('source-filter').addEventListener('change', (event) => { state.source = event.target.value; state.visible = PAGE; render(); });
    $('load-more').addEventListener('click', () => { state.visible += PAGE; render(); });
  } catch (error) {
    $('error').hidden = false;
    $('error').textContent = `${error.message} Reload to try again.`;
    $('result-count').textContent = 'Collection unavailable';
  }
}

document.querySelectorAll('[data-background]').forEach((button) => button.addEventListener('click', () => {
  document.documentElement.dataset.preview = button.dataset.background;
  document.querySelectorAll('[data-background]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
}));
$('close-detail').addEventListener('click', () => $('detail').close());
$('detail').addEventListener('click', (event) => { if (event.target === $('detail')) { const box = $('detail').getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) $('detail').close(); } });
$('copy-path').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(state.selected.path); toast('Repository path copied'); }
  catch { $('detail-path').focus(); $('detail-path').select(); toast('Select and copy the path'); }
});
init();
