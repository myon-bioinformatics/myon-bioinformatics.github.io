#!/usr/bin/env python3
"""Build api/repos.json from public GitHub repositories and their README summaries."""

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_ROOT = "https://api.github.com"
SUMMARY_LIMIT = 300
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
HR_RE = re.compile(r"^\s*([-*_])\1{2,}\s*$")


def _headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "repos-api-builder",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url):
    request = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def fetch_all_repos(owner):
    repos = []
    page = 1
    while True:
        url = f"{API_ROOT}/users/{owner}/repos?per_page=100&page={page}&type=owner"
        batch = _get_json(url)
        if not batch:
            return repos
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def fetch_readme(owner, name):
    """Return (markdown_text, raw_download_url), or (None, None) for no README."""
    url = f"{API_ROOT}/repos/{owner}/{name}/readme"
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        raise

    if payload.get("encoding") != "base64":
        return None, None
    text = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
    return text, payload.get("download_url")


def _is_noise_line(line):
    stripped = line.strip()
    if HR_RE.match(stripped) or stripped.startswith("|"):
        return True
    without_media = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", stripped)
    without_media = re.sub(r"!\[.*?\]\(.*?\)", "", without_media)
    without_html = re.sub(r"<[^>]+>", "", without_media)
    return not without_html.strip()


def extract_heading_and_summary(readme_text):
    """Extract the first H1-H3 heading and the first meaningful following paragraph."""
    if not readme_text:
        return None, None

    lines = readme_text.splitlines()
    heading = next(
        ((match.group(2).strip(), index) for index, line in enumerate(lines)
         if (match := HEADING_RE.match(line))),
        None,
    )
    if heading is None:
        return None, None

    title, heading_index = heading
    paragraph = []
    in_code_block = False
    for line in lines[heading_index + 1:]:
        stripped = line.strip()
        if stripped.startswith(("\`\`\`", "~~~")):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if HEADING_RE.match(line):
            break
        if not _is_noise_line(line):
            paragraph.append(stripped.lstrip("> ").strip())

    if not paragraph:
        return title, None

    summary = re.sub(r"\s+", " ", " ".join(paragraph)).strip()
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[:SUMMARY_LIMIT].rstrip() + "…"
    return title, summary or None


def build(owner):
    entries = []
    for repo in fetch_all_repos(owner):
        if repo.get("fork"):
            continue
        name = repo["name"]
        heading, summary = extract_heading_and_summary(fetch_readme(owner, name)[0])
        entry = {
            "name": name,
            "url": repo.get("html_url"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "stars": repo.get("stargazers_count", 0),
            "updatedAt": repo.get("updated_at"),
            "homepage": repo.get("homepage") or None,
            "readmeHeading": heading,
            "readmeSummary": summary,
            "readmeUrl": fetch_readme(owner, name)[1],
        }
        if repo.get("archived"):
            entry["archived"] = True
        entries.append(entry)

    entries.sort(key=lambda entry: entry["name"].lower())
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner": owner,
        "count": len(entries),
        "repos": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="myon-bioinformatics")
    parser.add_argument("--output", default="api/repos.json")
    args = parser.parse_args()

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(build(args.owner), output, ensure_ascii=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
