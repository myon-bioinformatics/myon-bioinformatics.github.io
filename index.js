const DEFAULT_VIEW_MODE = 'modern';
const VIEW_MODE_KEY = 'site:view-mode';
const VIEW_MODE_BASE_KEY = 'site:view-mode-base';
const VALID_VIEW_MODES = new Set(['modern', 'xml-like', 'json', 'markdown', 'github-like']);

let sharedData = null;
let configuredViewMode = DEFAULT_VIEW_MODE;

function normalizeViewMode(mode) {
  return VALID_VIEW_MODES.has(mode) ? mode : DEFAULT_VIEW_MODE;
}

function readStoredViewMode(configuredMode) {
  try {
    const base = localStorage.getItem(VIEW_MODE_BASE_KEY);
    if (base !== configuredMode) return null;
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

function clearElement(element) {
  if (element) element.replaceChildren();
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function externalLink(url, text = url) {
  const link = element('a', null, text);
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}

function applyViewMode(mode) {
  const normalized = normalizeViewMode(mode);
  document.body.dataset.viewMode = normalized;
  const selector = document.getElementById('view-mode-select');
  if (selector && selector.value !== normalized) selector.value = normalized;
  if (sharedData) renderPortfolio(normalized, sharedData);
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

async function loadSharedData() {
  const [profileRes, projectsRes] = await Promise.all([
    fetch('./profile.json', { cache: 'no-store' }),
    fetch('./projects.json', { cache: 'no-store' }),
  ]);

  if (!profileRes.ok) throw new Error(`profile.json HTTP ${profileRes.status}`);
  if (!projectsRes.ok) throw new Error(`projects.json HTTP ${projectsRes.status}`);

  const [profile, projects] = await Promise.all([profileRes.json(), projectsRes.json()]);
  return { profile, projects };
}

function renderWebProfile(root, profile) {
  root.dataset.renderer = 'web';

  const tabs = element('div', 'tabs');
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', 'Profile sections');

  const panelWrap = element('div', 'profile-panels');
  const sections = [
    ['about', 'About'],
    ['skills', 'Skills'],
    ['career', 'Career'],
  ];
  const panels = {};
  let skillsAnimated = false;

  function activateTab(key) {
    tabs.querySelectorAll('.tab-btn').forEach((button) => {
      const active = button.id === `tab-${key}`;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    Object.entries(panels).forEach(([panelKey, panel]) => {
      const active = panelKey === key;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
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

  sections.forEach(([key, label], index) => {
    const button = element('button', `tab-btn${index === 0 ? ' active' : ''}`, label);
    button.type = 'button';
    button.id = `tab-${key}`;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', String(index === 0));
    button.setAttribute('aria-controls', `panel-${key}`);
    button.addEventListener('click', () => activateTab(key));
    tabs.appendChild(button);

    const panel = element('div', `tab-panel${index === 0 ? ' active' : ''}`);
    panel.id = `panel-${key}`;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', `tab-${key}`);
    panel.hidden = index !== 0;
    panels[key] = panel;
    panelWrap.appendChild(panel);
  });

  panels.about.appendChild(element('p', 'about-text', profile.about));

  profile.skills.forEach(({ category, items }) => {
    const group = element('div', 'skill-group');
    group.appendChild(element('h4', 'skill-category', category));

    items.forEach(({ name, level }) => {
      const row = element('div', 'skill-row');
      row.appendChild(element('span', 'skill-label', name));

      const track = element('div', 'skill-bar-track');
      const fill = element('div', 'skill-bar-fill');
      fill.dataset.level = level;
      fill.style.width = '0%';
      track.appendChild(fill);
      row.appendChild(track);
      group.appendChild(row);
    });

    panels.skills.appendChild(group);
  });

  const timeline = element('ol', 'timeline');
  profile.career.forEach(({ year, title, desc }) => {
    const item = element('li', 'timeline-item');
    item.appendChild(element('span', 'tl-year', year));

    const body = element('div', 'tl-body');
    body.appendChild(element('strong', null, title));
    body.appendChild(element('p', null, desc));
    item.appendChild(body);
    timeline.appendChild(item);
  });
  panels.career.appendChild(timeline);

  root.appendChild(tabs);
  root.appendChild(panelWrap);
}

function renderWebProjects(root, projects) {
  root.dataset.renderer = 'web';
  root.className = 'grid';

  projects.forEach(({ name, desc, url, topics = [] }) => {
    const card = element('article', 'card');
    const title = element('h3');
    title.appendChild(externalLink(url, name));
    card.appendChild(title);
    card.appendChild(element('p', null, desc || ''));

    const badges = element('div', 'badges');
    topics.slice(0, 6).forEach((topic) => badges.appendChild(element('span', 'tag', topic)));
    card.appendChild(badges);

    const shields = element('img');
    shields.loading = 'lazy';
    shields.alt = 'GitHub stars';
    shields.src = `https://img.shields.io/github/stars/myon-bioinformatics/${encodeURIComponent(name)}?style=social`;
    shields.style.marginTop = '6px';
    card.appendChild(shields);
    root.appendChild(card);
  });
}

function xmlLine(parent, indent, parts) {
  const line = element('div', 'xml-line');
  line.style.setProperty('--indent', indent);
  parts.forEach((part) => {
    if (part instanceof Node) line.appendChild(part);
    else line.appendChild(document.createTextNode(part));
  });
  parent.appendChild(line);
}

function xmlTag(text, kind = 'tag') {
  return element('span', `xml-${kind}`, text);
}

function renderXmlProfile(root, profile) {
  root.dataset.renderer = 'xml';
  root.className = 'notation-root xml-renderer';
  xmlLine(root, 0, [xmlTag('<Profile>')]);
  xmlLine(root, 1, [xmlTag('<About>'), document.createTextNode(profile.about), xmlTag('</About>')]);
  xmlLine(root, 1, [xmlTag('<Skills>')]);
  profile.skills.forEach(({ category, items }) => {
    xmlLine(root, 2, [xmlTag(`<SkillGroup category="${category}">`)]);
    items.forEach(({ name, level }) => {
      xmlLine(root, 3, [xmlTag(`<Skill name="${name}" level="${level}" />`)]);
    });
    xmlLine(root, 2, [xmlTag('</SkillGroup>')]);
  });
  xmlLine(root, 1, [xmlTag('</Skills>')]);
  xmlLine(root, 1, [xmlTag('<Career>')]);
  profile.career.forEach(({ year, title, desc }) => {
    xmlLine(root, 2, [xmlTag(`<Entry year="${year}">`)]);
    xmlLine(root, 3, [xmlTag('<Title>'), title, xmlTag('</Title>')]);
    xmlLine(root, 3, [xmlTag('<Description>'), desc, xmlTag('</Description>')]);
    xmlLine(root, 2, [xmlTag('</Entry>')]);
  });
  xmlLine(root, 1, [xmlTag('</Career>')]);
  xmlLine(root, 0, [xmlTag('</Profile>')]);
}

function renderXmlProjects(root, projects) {
  root.dataset.renderer = 'xml';
  root.className = 'notation-root xml-renderer';
  xmlLine(root, 0, [xmlTag('<Projects>')]);
  projects.forEach(({ name, desc, url, topics = [] }) => {
    xmlLine(root, 1, [xmlTag(`<Project name="${name}">`)]);
    xmlLine(root, 2, [xmlTag('<Description>'), desc || '', xmlTag('</Description>')]);
    const urlLink = externalLink(url, url);
    xmlLine(root, 2, [xmlTag('<Url>'), urlLink, xmlTag('</Url>')]);
    xmlLine(root, 2, [xmlTag('<Topics>')]);
    topics.forEach((topic) => xmlLine(root, 3, [xmlTag('<Topic>'), topic, xmlTag('</Topic>')]));
    xmlLine(root, 2, [xmlTag('</Topics>')]);
    xmlLine(root, 1, [xmlTag('</Project>')]);
  });
  xmlLine(root, 0, [xmlTag('</Projects>')]);
}

function appendJsonValue(parent, value, indent = 0, key = null, trailingComma = false) {
  const line = element('div', 'json-line');
  line.style.setProperty('--indent', indent);
  if (key !== null) {
    line.appendChild(element('span', 'json-key', `"${key}"`));
    line.appendChild(document.createTextNode(': '));
  }

  if (Array.isArray(value)) {
    line.appendChild(element('span', 'json-punctuation', '['));
    parent.appendChild(line);
    value.forEach((item, index) => appendJsonValue(parent, item, indent + 1, null, index < value.length - 1));
    const close = element('div', 'json-line');
    close.style.setProperty('--indent', indent);
    close.appendChild(element('span', 'json-punctuation', `]${trailingComma ? ',' : ''}`));
    parent.appendChild(close);
    return;
  }

  if (value && typeof value === 'object') {
    line.appendChild(element('span', 'json-punctuation', '{'));
    parent.appendChild(line);
    const entries = Object.entries(value);
    entries.forEach(([childKey, childValue], index) => {
      appendJsonValue(parent, childValue, indent + 1, childKey, index < entries.length - 1);
    });
    const close = element('div', 'json-line');
    close.style.setProperty('--indent', indent);
    close.appendChild(element('span', 'json-punctuation', `}${trailingComma ? ',' : ''}`));
    parent.appendChild(close);
    return;
  }

  if (typeof value === 'string') {
    if (/^https?:\/\//.test(value)) {
      line.appendChild(document.createTextNode('"'));
      line.appendChild(externalLink(value, value));
      line.appendChild(document.createTextNode('"'));
    } else {
      line.appendChild(element('span', 'json-string', JSON.stringify(value)));
    }
  } else {
    line.appendChild(element('span', 'json-number', String(value)));
  }
  if (trailingComma) line.appendChild(element('span', 'json-punctuation', ','));
  parent.appendChild(line);
}

function renderJsonProfile(root, profile) {
  root.dataset.renderer = 'json';
  root.className = 'notation-root json-renderer';
  appendJsonValue(root, profile);
}

function renderJsonProjects(root, projects) {
  root.dataset.renderer = 'json';
  root.className = 'notation-root json-renderer';
  appendJsonValue(root, projects);
}

function renderMarkdownProfile(root, profile) {
  root.dataset.renderer = 'markdown';
  root.className = 'notation-root markdown-renderer';

  root.appendChild(element('h3', 'md-heading', '### About'));
  root.appendChild(element('p', 'about-text', profile.about));

  root.appendChild(element('h3', 'md-heading', '### Skills'));
  profile.skills.forEach(({ category, items }) => {
    root.appendChild(element('h4', 'md-heading', `#### ${category}`));
    const list = element('ul', 'md-list');
    items.forEach(({ name, level }) => list.appendChild(element('li', null, `${name} — ${level}%`)));
    root.appendChild(list);
  });

  root.appendChild(element('h3', 'md-heading', '### Career'));
  const career = element('ul', 'md-list');
  profile.career.forEach(({ year, title, desc }) => {
    const item = element('li');
    const strong = element('strong', null, `${year} — ${title}`);
    item.appendChild(strong);
    item.appendChild(document.createTextNode(`: ${desc}`));
    career.appendChild(item);
  });
  root.appendChild(career);
}

function renderMarkdownProjects(root, projects) {
  root.dataset.renderer = 'markdown';
  root.className = 'notation-root markdown-renderer';

  projects.forEach(({ name, desc, url, topics = [] }) => {
    const heading = element('h3', 'md-heading');
    heading.appendChild(document.createTextNode('### '));
    heading.appendChild(externalLink(url, name));
    root.appendChild(heading);
    root.appendChild(element('p', null, desc || ''));
    const list = element('ul', 'md-list');
    list.appendChild(element('li', null, `Topics: ${topics.join(', ')}`));
    const sourceItem = element('li');
    sourceItem.appendChild(document.createTextNode('Source: '));
    sourceItem.appendChild(externalLink(url, url));
    list.appendChild(sourceItem);
    root.appendChild(list);
  });
}

const PROFILE_RENDERERS = {
  modern: renderWebProfile,
  'github-like': renderWebProfile,
  'xml-like': renderXmlProfile,
  json: renderJsonProfile,
  markdown: renderMarkdownProfile,
};

const PROJECT_RENDERERS = {
  modern: renderWebProjects,
  'github-like': renderWebProjects,
  'xml-like': renderXmlProjects,
  json: renderJsonProjects,
  markdown: renderMarkdownProjects,
};

function renderPortfolio(mode, data) {
  const profileRoot = document.getElementById('profile-render-root');
  const projectsRoot = document.getElementById('projects-render-root');
  if (!profileRoot || !projectsRoot) return;

  clearElement(profileRoot);
  clearElement(projectsRoot);
  profileRoot.className = '';
  projectsRoot.className = '';

  PROFILE_RENDERERS[mode](profileRoot, data.profile);
  PROJECT_RENDERERS[mode](projectsRoot, data.projects);
}

function renderLoadError(error) {
  const profileRoot = document.getElementById('profile-render-root');
  const projectsRoot = document.getElementById('projects-render-root');
  if (profileRoot) profileRoot.textContent = 'Failed to load profile.';
  if (projectsRoot) projectsRoot.textContent = 'Failed to load projects. Please refresh.';
  console.error(error);
}

(async () => {
  configuredViewMode = await readConfiguredViewMode();
  const selectedMode = normalizeViewMode(readStoredViewMode(configuredViewMode) || configuredViewMode);
  initViewModeSelector(selectedMode, configuredViewMode);

  try {
    sharedData = await loadSharedData();
    renderPortfolio(selectedMode, sharedData);
  } catch (error) {
    renderLoadError(error);
  }
})();
