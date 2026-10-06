# gpww RSS feed

Builds a podcast-style RSS feed for https://gpww.differentdrum.ca/ and keeps it
updated automatically with GitHub Actions + GitHub Pages. No servers, no cost.

## One-time setup

1. Create a new **public** GitHub repository (e.g. `gpww-rss`).
2. Upload everything in this folder to it, keeping the structure:
   - `gen_feed.py`
   - `README.md`
   - `.github/workflows/update-feed.yml`
3. In the repo, go to **Settings -> Pages**. Under "Build and deployment" choose
   **Deploy from a branch**, pick branch `main` and folder `/docs`, then Save.
4. Go to the **Actions** tab, open **Update RSS feed**, and click **Run workflow**.
   (If GitHub asks you to enable workflows first, do that.)
   The first run fetches every episode page once (about a minute) and commits
   `episodes.json` and `docs/feed.xml`.
5. Your feed will be at:
   `https://<your-github-username>.github.io/<repo-name>/feed.xml`
   Paste that URL into your podcast app's "add podcast by URL" option.
   (Pages can take a minute or two to go live the first time.)

## How it keeps updating

The workflow runs once a day. Each run loads the site's home page (one request),
compares the episode list with `episodes.json`, and only fetches pages for episodes
it hasn't seen. Most days nothing changes and nothing is committed. When a new
weekly page appears, it adds that episode and commits the updated feed.

To check less often, edit the `cron` line in `.github/workflows/update-feed.yml`,
e.g. `"17 18 * * 1"` for Mondays only.

## If something breaks

- A failed run emails you (GitHub's default notification for workflows).
- "No episode links found" means the site layout changed; `parse_index` in
  `gen_feed.py` is the function to adjust.
- "no mp3 found yet" for an episode just means its page has no player yet; it is
  retried on the next run.
- Test locally with `python gen_feed.py` (Python 3.9+, no packages needed).

## Be kind to the site

The site's robots.txt asks automated tools to stay away, so this is meant for
personal use only: one home-page request a day, 1 second between requests, and
each episode page fetched once, ever. It also might be worth emailing
hello@differentdrum.ca to let them know.
