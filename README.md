# Daily News Digest

Fetches RSS feeds across AI, Cloud, and DevOps topics, summarizes the last 24 hours of articles with Claude, and posts a digest page to Notion — designed to be run by cron.

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- A [Notion integration token](https://www.notion.so/my-integrations) with access to your Gallery View database
- The ID of the Notion database (Gallery View) where digest entries will be created

## Installation

**1. Clone the repo and create a virtual environment**

```bash
git clone <your-repo-url> daily-news-ingest
cd daily-news-ingest
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

**2. Set up your environment variables**

```bash
cp .env.example .env
nano .env
```

Fill in all three values:

```
ANTHROPIC_API_KEY=sk-ant-...
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

To find your `NOTION_DATABASE_ID`: open your Gallery View in Notion, click `···` → **Copy link**, and pull the 32-character hex ID from the URL. It will be the ID segment that appears *before* any `?v=` query parameter — that part is the database ID, not a view ID.

Make sure your Notion integration has been granted access to the database (**Share** → invite the integration by name).

## Testing

Run these in order to verify each layer before scheduling:

```bash
# 1. Confirm feeds are reachable and returning articles — no API calls, free
venv/bin/python main.py --feeds-only

# 2. Confirm Claude summarizes correctly — uses Anthropic API, prints output to terminal
venv/bin/python main.py --dry-run

# 3. Full run — posts a real digest page to Notion
venv/bin/python main.py
```

## Scheduling on a Raspberry Pi

**1. Set the system timezone to Central Time**

```bash
sudo timedatectl set-timezone America/Chicago
timedatectl  # confirm
```

**2. Open your crontab**

```bash
crontab -e
```

**3. Add this line to run at 8 AM CT every day**

```
0 8 * * * cd /home/pi/daily-news-ingest && /home/pi/daily-news-ingest/venv/bin/python main.py >> /home/pi/daily-news-ingest/digest.log 2>&1
```

Replace `/home/pi` with your actual home directory if your username differs (`echo ~` to check).

**Why full paths?** Cron runs without your shell's `PATH`, so the explicit venv Python path and `cd` are required. The `cd` also ensures `python-dotenv` finds the `.env` file.

**Check the log after the first scheduled run:**

```bash
tail -f ~/daily-news-ingest/digest.log
```

## RSS Feeds

Feeds are hardcoded in `main.py` under the `FEEDS` dict, organized by category:

| Category | Sources |
|----------|---------|
| AI | OpenAI, HuggingFace, Towards Data Science, MIT News, MIT Tech Review, DeepMind, Meta AI, NVIDIA |
| Cloud | AWS, Azure, Google Cloud, InfoQ, The Register, Microsoft Cloud |
| DevOps | Kubernetes, GitHub, GitLab, HashiCorp, DevOps.com, CDF, The New Stack |

To add or remove a feed, edit the `FEEDS` dict and re-run `--feeds-only` to confirm it resolves correctly.
