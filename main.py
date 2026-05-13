#!/usr/bin/env python3
"""Daily news digest: fetch RSS feeds, summarize with Claude, write to Notion."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import anthropic
import feedparser
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_PARENT_PAGE_ID = os.environ["NOTION_PARENT_PAGE_ID"]

FEEDS: dict[str, list[str]] = {
    "AI": [
        "https://openai.com/blog/rss.xml",
        "https://huggingface.co/blog/feed.xml",
        "https://towardsdatascience.com/feed",
        "https://www.technologyreview.com/feed/",
        "https://deepmind.google/blog/rss.xml",
        "https://ai.meta.com/blog/rss/",
        "https://news.mit.edu/topic/artificial-intelligence2/rss.xml",
        "https://feeds.feedburner.com/nvidiablog",
    ],
    "Cloud": [
        "https://aws.amazon.com/blogs/aws/feed/",
        "https://azure.microsoft.com/en-us/blog/feed/",
        "https://cloud.google.com/blog/rss/",
        "https://www.infoq.com/cloud/rss",
        "https://www.theregister.com/cloud/headlines.atom",
        "https://cloudblogs.microsoft.com/feed/",
    ],
    "DevOps": [
        "https://kubernetes.io/feed.xml",
        "https://github.blog/feed/",
        "https://about.gitlab.com/atom.xml",
        "https://devops.com/feed/",
        "https://www.hashicorp.com/blog/feed.xml",
        "https://cd.foundation/blog/feed/",
        "https://thenewstack.io/feed/",
    ],
}

MAX_DESC_CHARS = 600
MAX_ARTICLES_PER_CATEGORY = 15
NOTION_RT_LIMIT = 1990  # Notion rich_text content character limit

USER_PROFILE = """
I am a college student about to graduate with a degree in Information Technology Infrastructure,
focused on AI and Cloud. I have completed AI internships and am actively pursuing AWS certifications
(Solutions Architect Associate and AI Practitioner). My career goal is to move into a cloud
infrastructure role after graduation, then grow into an AI Solutions Architect role within a few years.

Prioritize articles that are relevant to:
- AWS services, announcements, best practices, and certification-relevant topics (SAA, AI Practitioner)
- Agentic AI, AI agents, and what AI practitioners and architects need to know right now
- Cloud infrastructure: architecture, networking, storage, compute, cost optimization
- AI/ML in general — models, platforms, tools, trends shaping the industry
- DevOps fundamentals and practices worth knowing for someone building cloud exposure
- Broader IT industry news that would interest an IT professional early in their career

I enjoy a mix of technical deep-dives and higher-level industry trend pieces. Skip articles that are
purely marketing fluff, unrelated to tech, or too niche to matter for someone at my career stage.
For each article you include, briefly note (in 1 sentence) why it is relevant to my goals and how it could assist me in my career development.
"""


def fetch_recent_articles() -> dict[str, list[dict]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result: dict[str, list[dict]] = {}

    for category, urls in FEEDS.items():
        articles: list[dict] = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
            except Exception as exc:
                print(f"  [warn] failed to parse {url}: {exc}", file=sys.stderr)
                continue

            for entry in feed.entries:
                parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if parsed is None:
                    continue
                pub_dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                desc = (entry.get("summary") or entry.get("description") or "").strip()
                articles.append({
                    "title": (entry.get("title") or "").strip(),
                    "url": entry.get("link", ""),
                    "description": desc[:MAX_DESC_CHARS],
                })

        result[category] = articles[:MAX_ARTICLES_PER_CATEGORY]
        print(f"  {category}: {len(result[category])} article(s)")

    return result


def build_prompt(articles: dict[str, list[dict]]) -> str:
    lines = [
        "You are a personal news curator for a specific reader. Your job is to review all available",
        "articles and select only the ones most worth the reader's time based on their profile.",
        "",
        "Reader profile:",
        USER_PROFILE.strip(),
        "",
        "Instructions:",
        "- From all the articles provided, select only the ones that genuinely match the reader's interests.",
        "- Skip articles that are low-value, pure marketing, or irrelevant to their career path.",
        "- There is no minimum or maximum — include as many or as few as are actually worth reading.",
        "- For each selected article, write 2–3 sentences of detail plus one sentence explaining why",
        "  it is relevant to this reader's goals specifically. Include the article URL.",
        "- For each category, also write a short paragraph (2–4 sentences) summarizing the overall",
        "  themes across the selected articles.",
        "",
        "Return ONLY a JSON object (no markdown fences, no extra commentary) with this exact structure:",
        '{"AI":{"summary":"...","bullets":[{"text":"...","url":"..."}]},'
        '"Cloud":{"summary":"...","bullets":[...]},'
        '"DevOps":{"summary":"...","bullets":[...]}}',
        "",
        "Omit a category key entirely if no articles from that category are worth including.",
        "",
        "Articles to evaluate:",
        "",
    ]

    for category, items in articles.items():
        lines.append(f"### {category}")
        if not items:
            lines.append("(no recent articles)")
            lines.append("")
            continue
        for item in items:
            lines.append(f"- {item['title']}")
            lines.append(f"  URL: {item['url']}")
            if item["description"]:
                lines.append(f"  Excerpt: {item['description']}")
        lines.append("")

    return "\n".join(lines)


def call_claude(articles: dict[str, list[dict]]) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = build_prompt(articles)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON despite instructions
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Remove opening fence (``` or ```json) and closing fence
        lines = [l for l in lines if not l.startswith("```")]
        raw = "\n".join(lines).strip()

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Notion block helpers
# ---------------------------------------------------------------------------

def _rt(content: str, url: str | None = None) -> dict:
    """Single rich_text node, optionally linked."""
    node: dict = {"type": "text", "text": {"content": content[:NOTION_RT_LIMIT]}}
    if url:
        node["text"]["link"] = {"url": url[:2000]}
    return node


def _paragraph_blocks(text: str) -> list[dict]:
    """Split long text across multiple paragraph blocks."""
    chunks = [text[i : i + NOTION_RT_LIMIT] for i in range(0, max(len(text), 1), NOTION_RT_LIMIT)]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_rt(chunk)]},
        }
        for chunk in chunks
    ]


def _bullet_block(text: str, url: str) -> dict:
    rt_nodes = [_rt(text[:NOTION_RT_LIMIT])]
    if url:
        rt_nodes.append(_rt(f" ({url[:500]})", url=url))
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rt_nodes},
    }


def _heading2_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [_rt(text)]},
    }


def build_blocks(digest: dict) -> list[dict]:
    blocks: list[dict] = []
    for category in ("AI", "Cloud", "DevOps"):
        data = digest.get(category)
        if not data:
            continue
        blocks.append(_heading2_block(category))
        summary = (data.get("summary") or "").strip()
        if summary:
            blocks.extend(_paragraph_blocks(summary))
        for item in data.get("bullets", []):
            blocks.append(_bullet_block(item.get("text", ""), item.get("url", "")))
    return blocks


# ---------------------------------------------------------------------------
# Notion page creation
# ---------------------------------------------------------------------------

def create_notion_page(title: str, blocks: list[dict]) -> str:
    notion = Client(auth=NOTION_API_KEY)

    page = notion.pages.create(
        parent={"page_id": NOTION_PARENT_PAGE_ID},
        properties={"title": [{"type": "text", "text": {"content": title}}]},
        children=blocks[:100],  # Notion API max 100 blocks per request
    )

    page_id: str = page["id"]
    page_url: str = page.get("url", page_id)

    remaining = blocks[100:]
    while remaining:
        notion.blocks.children.append(
            block_id=page_id,
            children=remaining[:100],
        )
        remaining = remaining[100:]

    return page_url


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily news digest — fetch, summarize, and post to Notion.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--feeds-only",
        action="store_true",
        help="Fetch RSS feeds and print article counts/titles. No API calls.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch feeds and call Claude, but print the digest instead of posting to Notion.",
    )
    return parser.parse_args()


def _print_digest(digest: dict) -> None:
    for category in ("AI", "Cloud", "DevOps"):
        data = digest.get(category)
        if not data:
            continue
        print(f"\n{'=' * 60}")
        print(f"  {category}")
        print(f"{'=' * 60}")
        print(data.get("summary", ""))
        for item in data.get("bullets", []):
            print(f"\n  • {item.get('text', '')}")
            if item.get("url"):
                print(f"    {item['url']}")


def main() -> None:
    args = parse_args()
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"Digest — {today}"
    print(f"=== {title} ===")

    # --feeds-only: test feed fetching without touching any API
    if args.feeds_only:
        print("Fetching RSS feeds (feeds-only mode)...\n")
        articles = fetch_recent_articles()
        for category, items in articles.items():
            print(f"\n{category} ({len(items)} article(s)):")
            for item in items:
                print(f"  - {item['title']}")
                print(f"    {item['url']}")
        print("\nFeeds OK — no API calls made.")
        return

    print("Fetching RSS feeds...")
    articles = fetch_recent_articles()

    total = sum(len(v) for v in articles.values())
    if total == 0:
        print("No articles found in the last 24 hours — nothing to publish.")
        return

    print(f"Calling Claude ({total} article(s) total)...")
    digest = call_claude(articles)

    # --dry-run: print Claude's output, skip Notion
    if args.dry_run:
        print("\n--- Claude output (dry run — Notion page NOT created) ---")
        _print_digest(digest)
        blocks = build_blocks(digest)
        print(f"\n{len(blocks)} Notion block(s) would be created.")
        return

    print("Building Notion blocks...")
    blocks = build_blocks(digest)
    if not blocks:
        print("Claude returned no usable content — nothing to publish.")
        return

    print(f"Creating Notion page ({len(blocks)} block(s))...")
    location = create_notion_page(title, blocks)
    print(f"Done: {location}")


if __name__ == "__main__":
    main()
