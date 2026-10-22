const DEFAULT_VIEW_MODE = 'modern';
const VIEW_MODE_KEY = 'site:view-mode';
const VIEW_MODE_BASE_KEY = 'site:view-mode-base';
const VALID_VIEW_MODES = new Set(['modern', 'xml-like', 'json', 'markdown', 'github-like']);

let sharedData = null;
let configuredViewMode = DEFAULT_VIEW_MODE;
let currentTagFilter = 'all';
let currentSearchQuery = '';
let controlsInitialized = false;

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

function getCurrentMode() {
  return normalizeViewMode(document.body.dataset.viewMode || configuredViewMode);
}

function applyViewMode(mode) {
  const normalized = normalizeViewMode(mode);
  document.body.dataset.viewMode = normalized;
  document.body.dataset.uiTheme = normalized === 'modern' ? 'modern' : normalized === 'github-like' ? 'github-like' : 'plain';
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

function shuffleItems(items) {
  const shuffled = [...items];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

// Public, non-archived repositories only. The full candidate pool is collected
// first, then shuffled so each page load shows a fresh order.
function buildProjectCatalog(catalog, curated) {
  if (!Array.isArray(catalog?.repos)) throw new Error('Invalid repository catalog');
  const overrides = new Map(curated.map((project) => [project.name, project]));
  const candidates = catalog.repos
    .filter((repo) => repo.archived !== true)
    .map((repo) => {
      const project = overrides.get(repo.name);
      return {
        name: repo.name,
        desc: project?.desc || repo.description || repo.readmeSummary || 'Explore the source and README on GitHub.',
        url: repo.url,
        topics: [...new Set([...(project?.topics || []), ...(repo.topics || [])])],
        archived: false,
      };
    });
  return shuffleItems(candidates);
}

async function loadSharedData() {
  const [profileRes, catalogRes, curated] = await Promise.all([
    fetch('./profile.json', { cache: 'no-store' }),
    fetch('./api/repos.json', { cache: 'no-store' }),
    fetch('./projects.json', { cache: 'no-store' })
      .then((res) => res.ok ? res.json() : [])
      .catch(() => []),
  ]);

  if (!profileRes.ok) throw new Error(`profile.json HTTP ${profileRes.status}`);
  if (!catalogRes.ok) throw new Error(`api/repos.json HTTP ${catalogRes.status}`);

  const [profile, catalog] = await Promise.all([profileRes.json(), catalogRes.json()]);
  return { profile, projects: buildProjectCatalog(catalog, Array.isArray(curated) ? curated : []) };
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
  root.className = 'ui-grid';

  if (!projects || projects.length === 0) {
    const emptyMsg = element('div', 'empty-projects-msg', 'No projects match your filter.');
    root.appendChild(emptyMsg);
    return;
  }

  projects.forEach(({ name, desc, url, topics = [], archived }) => {
    const card = element('article', 'ui-card');
    const title = element('h3', 'ui-title');
    title.appendChild(externalLink(url, name));
    card.appendChild(title);
    if (archived) card.appendChild(element('span', 'ui-tag project-status', 'Archived'));
    card.appendChild(element('p', 'ui-muted', desc || ''));

    const badges = element('div', 'project-topics');
    topics.slice(0, 6).forEach((topic) => {
      const tagSpan = element('span', 'ui-tag', topic);
      tagSpan.dataset.topic = topic;
      tagSpan.style.cursor = 'pointer';
      tagSpan.title = `Filter by ${topic}`;
      tagSpan.addEventListener('click', (e) => {
        e.stopPropagation();
        setTagFilter(topic);
      });
      badges.appendChild(tagSpan);
    });
    card.appendChild(badges);

    const footer = element('div', 'project-card-actions');
    const shields = element('img');
    shields.loading = 'lazy';
    shields.alt = 'GitHub stars';
    shields.src = `https://img.shields.io/github/stars/myon-bioinformatics/${encodeURIComponent(name)}?style=social`;
    footer.appendChild(shields);

    const copyBtn = element('button', 'ui-button project-copy', 'Copy URL');
    copyBtn.type = 'button';
    copyBtn.setAttribute('aria-label', `Copy repository URL for ${name}`);
    copyBtn.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(url);
        } else {
          const textarea = document.createElement('textarea');
          textarea.value = url;
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand('copy');
          document.body.removeChild(textarea);
        }
        copyBtn.textContent = 'Copied!';
        copyBtn.classList.add('copied');
        setTimeout(() => {
          copyBtn.textContent = 'Copy URL';
          copyBtn.classList.remove('copied');
        }, 1500);
      } catch (err) {
        console.error('Copy failed:', err);
      }
    });
    footer.appendChild(copyBtn);

    card.appendChild(footer);
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
  if (!projects || projects.length === 0) {
    xmlLine(root, 1, [document.createTextNode('<!-- No projects match your filter -->')]);
  } else {
    projects.forEach(({ name, desc, url, topics = [], archived }) => {
      xmlLine(root, 1, [xmlTag(`<Project name="${name}">`)]);
      if (archived) xmlLine(root, 2, [xmlTag('<Status>'), 'Archived', xmlTag('</Status>')]);
      xmlLine(root, 2, [xmlTag('<Description>'), desc || '', xmlTag('</Description>')]);
      const urlLink = externalLink(url, url);
      xmlLine(root, 2, [xmlTag('<Url>'), urlLink, xmlTag('</Url>')]);
      xmlLine(root, 2, [xmlTag('<Topics>')]);
      topics.forEach((topic) => xmlLine(root, 3, [xmlTag('<Topic>'), topic, xmlTag('</Topic>')]));
      xmlLine(root, 2, [xmlTag('</Topics>')]);
      xmlLine(root, 1, [xmlTag('</Project>')]);
    });
  }
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

  if (!projects || projects.length === 0) {
    root.appendChild(element('p', null, 'No projects match your filter.'));
    return;
  }

  projects.forEach(({ name, desc, url, topics = [], archived }) => {
    const heading = element('h3', 'md-heading');
    heading.appendChild(document.createTextNode('### '));
    heading.appendChild(externalLink(url, name));
    root.appendChild(heading);
    root.appendChild(element('p', null, desc || ''));
    const list = element('ul', 'md-list');
    if (archived) list.appendChild(element('li', null, 'Status: Archived'));
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

function getFilteredProjects(projects) {
  if (!Array.isArray(projects)) return [];
  const facets = {};
  if (currentTagFilter !== 'all') facets.topic = currentTagFilter;
  return WebUICollections.filterItems(projects, {
    query: currentSearchQuery,
    text: project => [project.name, project.desc, ...(project.topics || [])],
    facets,
    facetValues: { topic: project => project.topics || [] },
  });
}

function updateProjectsCount(filteredCount, totalCount) {
  const countEl = document.getElementById('projects-count');
  if (!countEl) return;
  if (filteredCount === totalCount) {
    countEl.textContent = `Showing all ${totalCount} projects`;
  } else if (filteredCount > 0) {
    countEl.textContent = `Showing ${filteredCount} of ${totalCount} projects`;
  } else {
    countEl.textContent = 'No matching projects found.';
  }
}

function setTagFilter(tag) {
  currentTagFilter = tag;
  const tagBtns = document.querySelectorAll('#project-tags-filter .tag-btn');
  tagBtns.forEach((btn) => {
    const active = btn.dataset.tag === tag;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  if (sharedData) {
    renderPortfolio(getCurrentMode(), sharedData);
  }
}

function initProjectControls(projects) {
  if (controlsInitialized || !projects) return;
  controlsInitialized = true;

  const searchInput = document.getElementById('project-search-input');
  const searchClear = document.getElementById('project-search-clear');
  const tagsContainer = document.getElementById('project-tags-filter');
  // Keep input entered while the catalog was still loading.
  currentSearchQuery = searchInput?.value || '';
  if (searchClear) searchClear.hidden = !currentSearchQuery;

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      currentSearchQuery = searchInput.value;
      if (searchClear) searchClear.hidden = !currentSearchQuery;
      if (sharedData) {
        renderPortfolio(getCurrentMode(), sharedData);
      }
    });
  }

  if (searchClear) {
    searchClear.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      currentSearchQuery = '';
      searchClear.hidden = true;
      if (sharedData) {
        renderPortfolio(getCurrentMode(), sharedData);
      }
    });
  }

  if (tagsContainer) {
    const uniqueTopics = Array.from(new Set(projects.flatMap((p) => p.topics || []))).sort();
    const allTags = ['all', ...uniqueTopics];

    allTags.forEach((tag) => {
      const label = tag === 'all' ? 'All' : tag;
      const btn = element('button', `tag-btn${tag === currentTagFilter ? ' active' : ''}`, label);
      btn.type = 'button';
      btn.dataset.tag = tag;
      btn.setAttribute('aria-pressed', String(tag === currentTagFilter));
      btn.addEventListener('click', () => setTagFilter(tag));
      tagsContainer.appendChild(btn);
    });
  }
}

let aiHighlightsPool = [];
let displayedAiHighlights = [];

const FALLBACK_AI_HIGHLIGHTS = [
  {
    name: 'ollama/ollama',
    desc: 'Get up and running with Llama 3.3, DeepSeek-R1, Gemma 2, and other large language models.',
    url: 'https://github.com/ollama/ollama',
    stars: null,
    language: 'Go',
  },
  {
    name: 'vllm-project/vllm',
    desc: 'A high-throughput and memory-efficient inference and serving engine for LLMs.',
    url: 'https://github.com/vllm-project/vllm',
    stars: null,
    language: 'Python',
  },
  {
    name: 'langchain-ai/langchain',
    desc: 'Building applications with LLMs through composability.',
    url: 'https://github.com/langchain-ai/langchain',
    stars: null,
    language: 'Python',
  },
  {
    name: 'huggingface/transformers',
    desc: 'State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.',
    url: 'https://github.com/huggingface/transformers',
    stars: null,
    language: 'Python',
  },
];

async function fetchAiHighlights() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2000);
  let live = false;
  try {
    const res = await fetch('https://api.github.com/search/repositories?q=topic:ai+stars:>1000&sort=updated&order=desc&per_page=12', {
      headers: { Accept: 'application/vnd.github.v3+json' }, signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    aiHighlightsPool = items.filter(item => {
      try {
        const url = new URL(item.html_url);
        return url.protocol === 'https:' && url.hostname === 'github.com' && typeof item.full_name === 'string';
      } catch { return false; }
    }).map(item => ({
      name: item.full_name, desc: item.description || '', url: item.html_url,
      stars: Number.isFinite(item.stargazers_count) ? item.stargazers_count : null,
      language: item.language || 'Code',
    }));
    live = aiHighlightsPool.length > 0;
  } catch {
    aiHighlightsPool = [];
  } finally {
    clearTimeout(timeoutId);
  }
  if (!live) aiHighlightsPool = [...FALLBACK_AI_HIGHLIGHTS];
  const status = document.getElementById('ai-highlights-status');
  if (status) status.textContent = live
    ? 'Recently updated AI projects from the public GitHub API.'
    : 'Curated examples — live GitHub data is unavailable.';
  pickRandomAiHighlights();
  renderAiHighlights(getCurrentMode());
}

function highlightStars(stars) {
  return stars == null ? 'Curated example' : `★ ${stars.toLocaleString()} stars`;
}

function pickRandomAiHighlights(count = 3) {
  if (!aiHighlightsPool || aiHighlightsPool.length === 0) {
    aiHighlightsPool = [...FALLBACK_AI_HIGHLIGHTS];
  }
  const shuffled = [...aiHighlightsPool];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  displayedAiHighlights = shuffled.slice(0, Math.min(count, shuffled.length));
}

function renderAiHighlights(mode) {
  const root = document.getElementById('ai-highlights-render-root');
  if (!root) return;
  clearElement(root);

  if (mode === 'xml-like') {
    root.dataset.renderer = 'xml';
    root.className = 'notation-root xml-renderer';
    xmlLine(root, 0, [xmlTag('<AiHighlights>')]);
    displayedAiHighlights.forEach(({ name, desc, url, stars, language }) => {
      xmlLine(root, 1, [xmlTag(`<Highlight name="${name}" stars="${stars}" language="${language}">`)]);
      xmlLine(root, 2, [xmlTag('<Description>'), desc, xmlTag('</Description>')]);
      xmlLine(root, 2, [xmlTag('<Url>'), externalLink(url, url), xmlTag('</Url>')]);
      xmlLine(root, 1, [xmlTag('</Highlight>')]);
    });
    xmlLine(root, 0, [xmlTag('</AiHighlights>')]);
  } else if (mode === 'json') {
    root.dataset.renderer = 'json';
    root.className = 'notation-root json-renderer';
    appendJsonValue(root, displayedAiHighlights);
  } else if (mode === 'markdown') {
    root.dataset.renderer = 'markdown';
    root.className = 'notation-root markdown-renderer';
    displayedAiHighlights.forEach(({ name, desc, url, stars, language }) => {
      const heading = element('h3', 'md-heading');
      heading.appendChild(document.createTextNode('### '));
      heading.appendChild(externalLink(url, name));
      root.appendChild(heading);
      root.appendChild(element('p', null, desc));
      const list = element('ul', 'md-list');
      list.appendChild(element('li', null, `${highlightStars(stars)} • ${language}`));
      root.appendChild(list);
    });
  } else {
    root.dataset.renderer = 'web';
    root.className = 'grid';
    displayedAiHighlights.forEach(({ name, desc, url, stars, language }) => {
      const card = element('article', 'card ai-card');
      const title = element('h3');
      title.appendChild(externalLink(url, name));
      card.appendChild(title);
      card.appendChild(element('p', null, desc));

      const meta = element('div', 'ai-meta');
      const starTag = element('span', 'tag', highlightStars(stars));
      const langTag = element('span', 'tag', language);
      meta.appendChild(starTag);
      meta.appendChild(langTag);
      card.appendChild(meta);

      root.appendChild(card);
    });
  }
}

function renderPortfolio(mode, data) {
  const profileRoot = document.getElementById('profile-render-root');
  const projectsRoot = document.getElementById('projects-render-root');
  if (!profileRoot || !projectsRoot) return;

  clearElement(profileRoot);
  clearElement(projectsRoot);
  profileRoot.className = '';
  projectsRoot.className = '';

  PROFILE_RENDERERS[mode](profileRoot, data.profile);

  const filteredProjects = getFilteredProjects(data.projects);
  updateProjectsCount(filteredProjects.length, data.projects.length);
  PROJECT_RENDERERS[mode](projectsRoot, filteredProjects);

  renderAiHighlights(mode);
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

  const refreshBtn = document.getElementById('ai-highlights-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      pickRandomAiHighlights();
      renderAiHighlights(getCurrentMode());
    });
  }

  try {
    sharedData = await loadSharedData();
    initProjectControls(sharedData.projects);
    pickRandomAiHighlights();
    renderPortfolio(getCurrentMode(), sharedData);
    void fetchAiHighlights();
  } catch (error) {
    renderLoadError(error);
  }
})();

