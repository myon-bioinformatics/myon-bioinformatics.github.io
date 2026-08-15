import { readFile } from 'node:fs/promises';

const readJson = async (path) => JSON.parse(await readFile(path, 'utf8'));

const [profile, projects, repoPayload, registry] = await Promise.all([
  readJson('profile.json'),
  readJson('projects.json'),
  readJson('api/repos.json'),
  readJson('services.json'),
]);

const errors = [];
const repos = new Map(repoPayload.repos.map((repo) => [repo.name, repo]));
const services = registry.services || {};

for (const project of projects) {
  const repo = repos.get(project.name);
  if (!repo) {
    errors.push(`projects.json references unknown repository: ${project.name}`);
    continue;
  }

  // Repository URL is a compatibility field only; descriptions/topics are curated presentation data.
  if (project.url && project.url !== repo.url) {
    errors.push(`project URL drift for ${project.name}: ${project.url} != ${repo.url}`);
  }
}

const requiredUrls = [
  ['account.github', services.account?.github?.url],
  ['portfolio.pages', services.portfolio?.pages?.url],
  ['portfolio.profileData', services.portfolio?.profileData?.url],
  ['portfolio.projectsData', services.portfolio?.projectsData?.url],
  ['portfolio.repositoryCatalog', services.portfolio?.repositoryCatalog?.url],
];
for (const [key, url] of requiredUrls) {
  if (!url) errors.push(`services.json is missing required service URL: ${key}`);
}

if (services.portfolio?.repositoryCatalog?.url !== 'https://myon-bioinformatics.github.io/api/repos.json') {
  errors.push('portfolio.repositoryCatalog must point to the canonical repos.json endpoint');
}

// profile.json keeps compatibility URLs for current renderers; services.json owns the canonical values.
if (profile.links?.portfolio !== services.portfolio?.pages?.url) {
  errors.push('profile.links.portfolio must match services.portfolio.pages.url');
}
if (profile.links?.github !== services.account?.github?.url) {
  errors.push('profile.links.github must match services.account.github.url');
}

const allowedKinds = new Set(['external-profile', 'static-data', 'repository', 'pages', 'mcp-stub']);
const validateEntry = (path, entry) => {
  if (!entry || typeof entry !== 'object') return;
  if ('url' in entry) {
    if (!allowedKinds.has(entry.kind)) errors.push(`unknown service kind at ${path}: ${entry.kind}`);
    if (!entry.url) errors.push(`missing URL at ${path}`);
    return;
  }
  for (const [key, value] of Object.entries(entry)) validateEntry(`${path}.${key}`, value);
};
validateEntry('services', services);

for (const [repoName, projectServices] of Object.entries(services.projects || {})) {
  const repo = repos.get(repoName);
  if (!repo) {
    errors.push(`services.json references unknown repository: ${repoName}`);
    continue;
  }

  if (projectServices.repository?.url && projectServices.repository.url !== repo.url) {
    errors.push(`repository service URL drift for ${repoName}: ${projectServices.repository.url} != ${repo.url}`);
  }

  for (const [serviceName, service] of Object.entries(projectServices)) {
    if (service.kind === 'pages' || service.kind === 'mcp-stub') {
      const expectedPrefix = `https://myon-bioinformatics.github.io/${repoName}/`;
      if (!service.url.startsWith(expectedPrefix)) {
        errors.push(`${serviceName} URL for ${repoName} must be under ${expectedPrefix}`);
      }
    }
  }
}

if (errors.length) {
  console.error('SSOT validation failed:');
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`SSOT validation passed: ${projects.length} curated projects, ${repos.size} repositories, ${Object.keys(services.projects || {}).length} registered project service groups.`);
