#!/usr/bin/env python3
import os
import json
import sys
import urllib.request

GH_TOKEN = os.getenv("GH_TOKEN")
GH_USER = os.getenv("GH_USER")
OUT = os.getenv("OUT", "projects.json")
LIMIT = int(os.getenv("LIMIT", "8"))

if not GH_TOKEN or not GH_USER:
    print("GH_TOKEN and GH_USER must be set.", file=sys.stderr)
    sys.exit(1)

query = """
query($login: String!, $first: Int!) {
  user(login: $login) {
    pinnedItems(first: $first, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
          repositoryTopics(first: 12) {
            nodes {
              topic { name }
            }
          }
        }
      }
    }
  }
}
"""

variables = {"login": GH_USER, "first": LIMIT}
payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")

req = urllib.request.Request(
    "https://api.github.com/graphql",
    data=payload,
    headers={
        "Authorization": f"Bearer {GH_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "actions-bot"
    },
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))

if "errors" in data:
    print("GraphQL errors:", data["errors"], file=sys.stderr)
    sys.exit(1)

nodes = data["data"]["user"]["pinnedItems"]["nodes"]
items = []
for n in nodes:
    topics = [t["topic"]["name"] for t in n.get("repositoryTopics", {}).get("nodes", [])]
    items.append({
        "name": n["name"],
        "desc": n.get("description") or "",
        "url": n["url"],
        "topics": topics
    })

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f"Wrote {OUT} with {len(items)} items.")
