# Daily News Digest

Fetches RSS feeds across AI, Cloud, and DevOps topics, uses Claude to curate and summarize only the articles most relevant to your interests, and creates a new entry in a Notion Gallery View database every day — designed to be run by cron.

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- A [Notion connection token](https://www.notion.so/my-integrations) with access to your Gallery View database
- The ID of the Notion database (Gallery View) where digest entries will be created

## Installation

**1. Clone the repo and create a virtual environment**

```bash
git clone https://github.com/Programming-Mellow/daily-news-ingest.git
cd daily-news-ingest
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

**2. Set up your environment variables**

```bash
cp .env.example .env
nano .env
```

Fill in all four values:

```
ANTHROPIC_API_KEY=sk-ant-...
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_TITLE_PROP=Name
```

**Finding your `NOTION_DATABASE_ID`:**
1. Open your Gallery View in Notion
2. Click `···` → **Open as full page**
3. Copy the URL from your browser — it looks like:
   ```
   https://www.notion.so/abc123...?v=xyz456...
   ```
4. The database ID is the 32-character hex string **before** `?v=` — the part after is a view ID and will not work

**Setting `NOTION_TITLE_PROP`:**
This is the name of the title column in your database. Open any existing entry in your Gallery View — it's the bold field at the top of the card. Notion defaults this to `Name`. Set it to whatever yours is actually called.

**Integrating Connections with your Notion page:**
Your Notion integration must have access to the database before it can create entries:
1. Open the Notion developer console and locate your connections
2. Click **Manage** then **Content Access**
3. Add your Notion page into the **Content Access** menu

## Testing

Run these in order to verify each layer before scheduling:

```bash
# 1. Confirm feeds are reachable and returning articles — no API calls, free
venv/bin/python main.py --feeds-only

# 2. Confirm Notion credentials and database ID are correct — no feed or Claude calls
venv/bin/python main.py --notion-test

# 3. Confirm Claude curates correctly — uses Anthropic API, prints output to terminal only
venv/bin/python main.py --dry-run

# 4. Full run — fetches feeds, calls Claude, posts a real digest entry to Notion
venv/bin/python main.py
```

## Personalization

Claude curates articles based on a reader profile defined in the `USER_PROFILE` constant near the top of `main.py`. It selects only the articles genuinely worth your time and adds a sentence to each one explaining why it is relevant to your goals. Articles that are low-value or off-topic are skipped entirely.

To update your profile, edit the `USER_PROFILE` string in `main.py`.

## Article Deduplication

After each successful run, the script writes a `seen_urls.json` file to the project directory. On the next run, any article URL already in that file is filtered out before being sent to Claude — preventing duplicate summaries and unnecessary API spend.

The file is created automatically on first use and is ignored by git (see `.gitignore`), so each person who clones the repo starts with a clean slate and won't accidentally commit their own URL history.

If you ever want to force a full re-digest — for example after a long gap between runs — just delete `seen_urls.json` and the next run will treat all articles as new.

## Scheduling on a Raspberry Pi

**1. Set the system timezone to Central Time (or whichever timezone you are in)**

```bash
sudo timedatectl set-timezone America/Chicago
timedatectl  # confirm
```

**2. Open your crontab**

```bash
crontab -e
```

**3. Add this line to run at 8 AM CT every day (or whichever time you desire)**

```
0 8 * * * cd /home/[USER PATH]/daily-news-ingest/daily-news-ingest && /home/[USER PATH]/daily-news-ingest/venv/bin/python main.py >> /home/[USER PATH]/daily-news-ingest/digest.log 2>&1
```

**Check the log after the first scheduled run:**

```bash
tail -f ~/[USER PATH]/daily-news-ingest/digest.log
```

## CI / GitHub Actions

A lightweight workflow at `.github/workflows/feed-check.yml` runs automatically on every push and pull request. It installs dependencies and executes `python main.py --feeds-only`, which confirms that every RSS feed URL is reachable and returning entries without making any API calls or incurring any cost.

No secrets are required for this job — `--feeds-only` never touches the Anthropic or Notion APIs. If a feed URL goes dead or returns a parse error, the warning is surfaced in the Actions log so you can update it before the next scheduled digest run.

## RSS Feeds

Feeds are hardcoded in `main.py` under the `FEEDS` dict, organized by category:

| Category | Sources |
|----------|---------|
| AI | OpenAI, HuggingFace, Towards Data Science, MIT News, MIT Tech Review, DeepMind, Meta AI, NVIDIA |
| Cloud | AWS, Azure, Google Cloud, InfoQ, The Register, Microsoft Cloud |
| DevOps | Kubernetes, GitHub, GitLab, HashiCorp, DevOps.com, CDF, The New Stack |

To add or remove a feed, edit the `FEEDS` dict and re-run `--feeds-only` to confirm it resolves correctly.
