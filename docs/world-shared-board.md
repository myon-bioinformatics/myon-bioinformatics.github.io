# Shared world board prototype

Opt in with `board.shared_issue = "OWNER/REPOSITORY/NUMBER"` in an existing
`web-ui-world/1` spec. Omit it to keep the old board. Runtime stays in
`scripts/world.py`, using Python stdlib and generated browser JavaScript. No server,
secret token, OAuth handler, network POST, or new runtime dependency is added.
The default world example connects to [public board #110](https://github.com/myon-bioinformatics/PySaiyanWeBoo/issues/110). It still sends no API request until the visitor clicks refresh.

The bulletin is a reusable PSWB component, not a World requirement. A page
builder can append `issue_bulletin_html("OWNER/REPOSITORY/NUMBER")`, load
`js/issue-bulletin.js` from `write_site()`, and call `bindIssueBulletin(panel)`
on its returned `<details>` element. The validated issue identifier constructs
both GitHub URLs; no arbitrary feed URL or credentials are accepted. A second
public Issue with the same contract needs only a new identifier. World remains
one caller via its existing `board.shared_issue` field.

Other providers can reuse `bulletin_html(post_url, title=..., notice=..., post_label=...)`
and `bindBulletin(panel, read)`. The caller supplies a trusted absolute HTTPS
post link and implements `read(signal, observeHeaders)` in code, not as a URL
in untrusted data. Return `{lines: [{author, time, text}], more: boolean}` in
display order, forward the abort signal to I/O, call `observeHeaders` with
response headers when available, and reject on errors. The UI keeps the
manual refresh and text limits. A different feed format needs its own adapter;
GitHub Discussions has no built-in reader, and no token or backend is added.

The board includes an expandable shared section and a separate-tab GitHub link.
The current world, villagers, player, clock, countdown and local Post stay open.
Without JavaScript the GitHub link still works. Users enter their shared message
on GitHub itself; local Post is never silently copied or submitted to GitHub.

| Action/data | Scope and lifetime |
| --- | --- |
| Existing Post | Current page DOM only, maximum 5 notes; disappears on reload |
| Shared display | Public GitHub comment body (60 code points, whitespace normalized), login and creation timestamp; kept in DOM until refresh/reload |
| GitHub posting | Login required, subject to issue lock, account and repository interaction restrictions; final submission happens on GitHub |
| Published comment | Full original text, username and timestamp publicly accessible on GitHub, potentially indexed/copied; persists until deleted on GitHub |
| Browser storage | No app localStorage, IndexedDB, service worker, token or persistent draft; fetch uses no-store and credentials omitted |

Do not post private rendezvous details, contact information or secrets. This is
public asynchronous messaging, not private chat, instant delivery or a presence
system. The app does not manage GitHub's own login cookies or drafts. Public read
requests disclose the requesting IP to GitHub. GitHub links suppress referrers.
HTML/Markdown in comments is displayed as plain text; images and links are not
rendered. The full original remains available through the GitHub issue.

## API and refresh bounds

A click makes one anonymous GET to
`https://api.github.com/repos/OWNER/REPOSITORY/issues/NUMBER/comments?per_page=100`.
There is no initial fetch, polling, pagination traversal or background request.
The first 100 comments are considered, the last up to five valid comments from
that page displayed newest first. **After 100 comments this is not the newest
five in the issue**; a pagination notice directs readers to GitHub. This small
prototype deliberately bounds response/page work rather than claiming a live feed.
For long-lived use, pagination/latest-feed support is a follow-up before rollout.

Clicks are throttled for at least 120 seconds per mounted board, including errors.
Concurrent requests are ignored, timeout is 10 seconds. Retry-After (seconds) and
X-RateLimit-Reset when remaining is zero extend the wait. Failed requests retain
previous text and announce failure. Reloads and multiple tabs do not coordinate
budgets; a shared NAT/IP can exhaust its budget even at this cadence.

GitHub documents anonymous REST access as 60 requests per hour **per originating
IP**, shared with other anonymous requests. No token is embedded to raise it.
Reading public comments needs no login; private targets fail anonymously.
The read URL depends on the Issue number, not its open/closed status. A closed
but unlocked Issue can remain a bulletin; do not lock it if public comments
should continue. An archived repository or interaction restrictions can still
limit posting. The app never attempts a write on a visitor's behalf.

Primary references (checked 2026-11-03):
- https://docs.github.com/en/rest/issues/comments#list-issue-comments
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- https://docs.github.com/en/communities/moderating-comments-and-conversations

## Verification and activation

`PYTHONPATH=. python -m pytest -q tests/test_worlds.py`
checks validation, opt-in compatibility, Node 26 projection and interaction,
text-only comments, malformed API payloads, cooldown and failure retention.
`python tests/world_browser.py SharedBoardTests` uses
Playwright Chromium at 320, 390 and 1280 px, with mocked API responses only. It checks
no automatic fetch, anonymous GET, HTML injection, posting link, local notes,
rate limit failures, retained shared display and reload cleanup. The dedicated
Shared world board workflow provisions Node 26 and runs both commands.

Local verification: 72 tests passed (plus one subtest) on Node 26.13.0,
including the existing copied single-file Node launcher tests, motion numerical
parity and both DOM harnesses. The official Node archive SHA-256 was checked.
Chromium download returned invalid/truncated archives locally; real-browser QA
must be checked in CI. No real comment was posted.

Activation was approved by the owner on 2026-11-03 (Japan time). Public issue
[World 共有電光掲示板（公開） #110](https://github.com/myon-bioinformatics/PySaiyanWeBoo/issues/110)
was created with public visibility, login, privacy, deletion/moderation and
non-realtime notices. The default world example now sets
`board.shared_issue = "myon-bioinformatics/PySaiyanWeBoo/110"`; generated front-page HTML
uses the same destination. Other worlds opt in individually; remove this field
to disable the shared section. Repository visibility is unchanged. Test `/123`
remains intercepted fixture data only.

The pre-activation head `5823530f` passed all five CI workflows, including desktop
and mobile Chromium shared-board tests. Activation changes only the example
configuration, generated page and documentation; the workflow rechecks them.
