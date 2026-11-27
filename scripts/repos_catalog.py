#!/usr/bin/env python3
"""Build api/repos.json from public GitHub repositories and their README summaries, and 🗓️ the weekly note
(docs/weekly-view.md: the pull requests merged last week, as Markdown the front page draws)."""

import argparse, base64, json, os, re, urllib.error, urllib.parse, urllib.request
from datetime import datetime, time, timedelta, timezone

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


# fetch-guard: every GitHub API call ends within a deadline.
TIMEOUT_SECONDS = 30


def _get_json(url):
    request = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
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
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
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
        if stripped.startswith(("```", "~~~")):
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


def pages_url(owner, repo):
    """The repository's GitHub Pages root when it has one (``has_pages``); the user site is the owner's root."""
    if not repo.get("has_pages"):
        return None
    name = repo["name"]
    return f"https://{owner}.github.io/" if name.lower() == f"{owner}.github.io".lower() else f"https://{owner}.github.io/{name}/"


def build(owner):
    entries = []
    for repo in fetch_all_repos(owner):
        if repo.get("fork"):
            continue
        name = repo["name"]
        readme_text, readme_url = fetch_readme(owner, name)
        heading, summary = extract_heading_and_summary(readme_text)
        entry = {
            "name": name,
            "url": repo.get("html_url"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "stars": repo.get("stargazers_count", 0),
            "updatedAt": repo.get("updated_at"),
            "homepage": repo.get("homepage") or None,
            "pages": pages_url(owner, repo),
            "readmeHeading": heading,
            "readmeSummary": summary,
            "readmeUrl": readme_url,
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


# ── 🗓️ The weekly note: last week's merged pull requests of this repository, as plain Markdown ──
JST = timezone(timedelta(hours=9))
WEEKDAYS = "月火水木金土日"


def last_week(now=None):
    """The Monday of the last complete week (Monday to Sunday, Japan time): the note changes once a week."""
    today = (now or datetime.now(JST)).astimezone(JST).date()
    return today - timedelta(days=today.weekday() + 7)


def _merged_query(repository, monday):
    start = datetime.combine(monday, time.min, JST)
    return f"repo:{repository} is:pr is:merged merged:{start.isoformat()}..{(start + timedelta(days=7, seconds=-1)).isoformat()}"


def fetch_merged(repository, monday):
    """The pull requests of ``owner/name`` merged in the week that starts on ``monday`` (GitHub's REST search, 100 a page)."""
    query, pulls = urllib.parse.quote(_merged_query(repository, monday), safe=""), []
    for page in range(1, 11):
        items = _get_json(f"{API_ROOT}/search/issues?q={query}&per_page=100&page={page}")["items"]
        pulls += [{"number": item["number"], "title": item["title"], "url": item["html_url"], "merged": item["pull_request"]["merged_at"],
                   "labels": [label["name"] for label in item["labels"]]} for item in items]
        if len(items) < 100:
            break
    return pulls


def weekly_note(pulls, monday, repository, limit=20):
    """🗓️ The week as Markdown: how many were merged each day and under each label (tables of numbers: the front page draws
    them as bars), then the newest ``limit`` with their links. Ordinary Markdown, so it reads the same on GitHub."""
    day = lambda at: f"{monday + timedelta(days=at):%m-%d}（{WEEKDAYS[at]}）"
    merged = lambda pull: datetime.fromisoformat(pull["merged"].replace("Z", "+00:00")).astimezone(JST)
    per_day = [sum((merged(pull).date() - monday).days == at for pull in pulls) for at in range(7)]
    labels = {}
    for pull in pulls:
        for name in pull["labels"] or ["（なし）"]:
            labels[name] = labels.get(name, 0) + 1
    cell = lambda text: " ".join(str(text).split()).replace("|", "\\|")
    lines = [f"# 🗓️ {monday:%Y-%m-%d}（月）〜 {monday + timedelta(days=6):%m-%d}（日）", "",
             f"この週にマージした PR は {len(pulls)} 本です。", "", "## 📊 日ごと", "", "| 日付（JST） | PR |", "|---|---:|",
             *(f"| {day(at)} | {count} |" for at, count in enumerate(per_day))]
    if pulls:
        newest = sorted(pulls, key=merged, reverse=True)
        lines += ["", "## 🏷️ ラベルごと", "", "| ラベル | PR |", "|---|---:|",
                  *(f"| {cell(name)} | {count} |" for name, count in sorted(labels.items(), key=lambda item: (-item[1], item[0]))),
                  "", "## 🧾 マージした PR", "",       # "](" is opened up so a title cannot write a link of its own
                  *(f"- [#{pull['number']}]({pull['url']}) {' '.join(pull['title'].split()).replace('](', '] (')}" for pull in newest[:limit])]
        if len(newest) > limit:
            search = f"https://github.com/{repository}/pulls?q=" + urllib.parse.quote(_merged_query(repository, monday).split(" ", 1)[1], safe="")
            lines += ["", f"ほか {len(newest) - limit} 本は [GitHub の一覧]({search}) にあります。"]
    lines += ["", "🤖 このノートは `scripts/repos_catalog.py --weekly` が、毎週月曜に前の週の分を作り直します。"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="myon-bioinformatics")
    parser.add_argument("--output", default="api/repos.json")
    parser.add_argument("--weekly", metavar="FILE", help="🗓️ also write last week's merged pull requests as Markdown (docs/weekly-view.md)")
    args = parser.parse_args(argv)

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(build(args.owner), output, ensure_ascii=False, indent=2)
        output.write("\n")
    if args.weekly:
        repository, monday = os.environ.get("GITHUB_REPOSITORY") or f"{args.owner}/{args.owner}.github.io", last_week()
        try:
            note = weekly_note(fetch_merged(repository, monday), monday, repository)
        except (urllib.error.URLError, KeyError, ValueError) as error:      # the catalog is refreshed all the same; the note stays as it was
            print(f"⏸ weekly note: {type(error).__name__}")
        else:
            with open(args.weekly, "w", encoding="utf-8") as output:
                output.write(note)


if __name__ == "__main__":
    main()
