import { readFile } from 'node:fs/promises';

const readJson = async (path) => JSON.parse(await readFile(path, 'utf8'));

const [projects, repoPayload, services] = await Promise.all([
  readJson('projects.json'),
  readJson('api/repos.json'),
  readJson('services.json'),
]);

const errors = [];
const repos = new Map(repoPayload.repos.map((repo) => [repo.name, repo]));

for (const project of projects) {
  const repo = repos.get(project.name);
  if (!repo) {
    errors.push(`projects.json references unknown repository: ${project.name}`);
    continue;
  }

  // Transitional compatibility check. Repository URL is owned by repos.json.
  // projects.json may still carry url until all renderers are migrated.
  if (project.url && project.url !== repo.url) {
    errors.push(`project URL drift for ${project.name}: ${project.url} != ${repo.url}`);
  }
}

const requiredServices = ['portfolio', 'profile', 'projects', 'repositories'];
for (const key of requiredServices) {
  if (!services.services?.[key]?.url) {
    errors.push(`services.json is missing required service URL: ${key}`);
  }
}

if (services.services?.repositories?.url !== 'https://myon-bioinformatics.github.io/api/repos.json') {
  errors.push('repositories service must point to the canonical repos.json endpoint');
}

if (errors.length) {
  console.error('SSOT validation failed:');
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`SSOT validation passed: ${projects.length} curated projects, ${repos.size} repositories, ${Object.keys(services.services || {}).length} services.`);
