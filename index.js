const DEFAULT_VIEW_MODE = 'modern';
const VIEW_MODE_KEY = 'site:view-mode';
// Tracks which config value was in effect when the user last picked a mode.
// If site.config.json changes, the stored user choice is treated as stale and
// discarded so the new config value takes effect for all visitors.
const VIEW_MODE_BASE_KEY = 'site:view-mode-base';
const VALID_VIEW_MODES = new Set(['modern', 'xml-like', 'json', 'markdown', 'github-like']);

function normalizeViewMode(mode) {
  return VALID_VIEW_MODES.has(mode) ? mode : DEFAULT_VIEW_MODE;
}

/**
 * Returns the user's stored mode only when it was saved against the same
 * configuredMode that is currently active.  Returns null when stale.
 */
function readStoredViewMode(configuredMode) {
  try {
    const base = localStorage.getItem(VIEW_MODE_BASE_KEY);
    if (base !== configuredMode) return null; // config changed → ignore stale choice
    return localStorage.getItem(VIEW_MODE_KEY);
  } catch {
    return null;
  }
}

function saveViewMode(mode, configuredMode) {
  try {
    localStorage.setItem(VIEW_MODE_KEY, mode);
    localStorage.setItem(VIEW_MODE_BASE_KEY, configuredMode);
  } catch {
    // ignore storage failures
  }
}

function applyViewMode(mode) {
  const normalized = normalizeViewMode(mode);
  document.body.dataset.viewMode = normalized;
  const selector = document.getElementById('view-mode-select');
  if (selector && selector.value !== normalized) selector.value = normalized;
}

async function readConfiguredViewMode() {
  try {
    const res = await fetch('./site.config.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const config = await res.json();
    return normalizeViewMode(config?.defaultViewMode);
  } catch {
    return DEFAULT_VIEW_MODE;
  }
}

function initViewModeSelector(initialMode, configuredMode) {
  const selector = document.getElementById('view-mode-select');
  applyViewMode(initialMode);
  if (!selector) return;

  selector.addEventListener('change', () => {
    const nextMode = normalizeViewMode(selector.value);
    applyViewMode(nextMode);
    saveViewMode(nextMode, configuredMode);
  });
}

async function renderProfile() {
  const panels = {
    about: document.getElementById('panel-about'),
    skills: document.getElementById('panel-skills'),
    career: document.getElementById('panel-career'),
  };
  const buttons = document.querySelectorAll('#profile .tab-btn');
  if (!panels.about) return;

  let skillsAnimated = false;

  function activateTab(key) {
    buttons.forEach((b) => {
      const active = b.id === `tab-${key}`;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
    });
    Object.entries(panels).forEach(([k, el]) => {
      const show = k === key;
      el.classList.toggle('active', show);
      el.hidden = !show;
    });

    if (key === 'skills' && !skillsAnimated) {
      skillsAnimated = true;
      requestAnimationFrame(() => {
        panels.skills.querySelectorAll('.skill-bar-fill').forEach((bar) => {
          bar.style.width = `${bar.dataset.level}%`;
        });
      });
    }
  }

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.id.replace('tab-', '');
      activateTab(key);
    });
  });

  try {
    const res = await fetch('./profile.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { about, skills, career } = await res.json();

    const aboutEl = document.createElement('p');
    aboutEl.className = 'about-text';
    aboutEl.textContent = about;
    panels.about.appendChild(aboutEl);

    skills.forEach(({ category, items }) => {
      const group = document.createElement('div');
      group.className = 'skill-group';

      const cat = document.createElement('h4');
      cat.className = 'skill-category';
      cat.textContent = category;
      group.appendChild(cat);

      items.forEach(({ name, level }) => {
        const row = document.createElement('div');
        row.className = 'skill-row';

        const label = document.createElement('span');
        label.className = 'skill-label';
        label.textContent = name;

        const track = document.createElement('div');
        track.className = 'skill-bar-track';

        const fill = document.createElement('div');
        fill.className = 'skill-bar-fill';
        fill.dataset.level = level;
        fill.style.width = '0%';

        track.appendChild(fill);
        row.appendChild(label);
        row.appendChild(track);
        group.appendChild(row);
      });

      panels.skills.appendChild(group);
    });

    const timeline = document.createElement('ol');
    timeline.className = 'timeline';
    career.forEach(({ year, title, desc }) => {
      const item = document.createElement('li');
      item.className = 'timeline-item';

      const yearEl = document.createElement('span');
      yearEl.className = 'tl-year';
      yearEl.textContent = year;

      const body = document.createElement('div');
      body.className = 'tl-body';

      const strong = document.createElement('strong');
      strong.textContent = title;

      const p = document.createElement('p');
      p.textContent = desc;

      body.appendChild(strong);
      body.appendChild(p);
      item.appendChild(yearEl);
      item.appendChild(body);
      timeline.appendChild(item);
    });
    panels.career.appendChild(timeline);
  } catch (error) {
    panels.about.textContent = 'Failed to load profile.';
    console.error(error);
  }
}

async function renderProjects() {
  const grid = document.getElementById('project-grid');
  if (!grid) return;

  try {
    const res = await fetch('./projects.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();

    const frag = document.createDocumentFragment();

    items.forEach(({ name, desc, url, topics = [] }) => {
      const card = document.createElement('article');
      card.className = 'card';

      const title = document.createElement('h3');
      const link = document.createElement('a');
      link.href = url;
      link.textContent = name;
      link.rel = 'noopener noreferrer';
      link.target = '_blank';
      title.appendChild(link);

      const p = document.createElement('p');
      p.textContent = desc || '';

      const badges = document.createElement('div');
      badges.className = 'badges';
      topics.slice(0, 6).forEach((topic) => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = topic;
        badges.appendChild(span);
      });

      const shields = document.createElement('img');
      shields.loading = 'lazy';
      shields.alt = 'GitHub stars';
      shields.src = `https://img.shields.io/github/stars/myon-bioinformatics/${encodeURIComponent(name)}?style=social`;
      shields.style.marginTop = '6px';

      card.appendChild(title);
      card.appendChild(p);
      card.appendChild(badges);
      card.appendChild(shields);
      frag.appendChild(card);
    });

    grid.textContent = '';
    grid.appendChild(frag);
  } catch (error) {
    grid.textContent = 'Failed to load projects. Please refresh.';
    console.error(error);
  }
}

(async () => {
  const configuredMode = await readConfiguredViewMode();
  // readStoredViewMode returns the user's choice only when it was saved while
  // the same configuredMode was active; if site.config.json has changed since
  // then, it returns null so the new config value takes effect for all visitors.
  const selectedMode = normalizeViewMode(readStoredViewMode(configuredMode) || configuredMode);
  initViewModeSelector(selectedMode, configuredMode);
  await Promise.all([renderProfile(), renderProjects()]);
})();
