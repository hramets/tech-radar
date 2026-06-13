from datetime import datetime, timedelta, timezone
import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import os
import json


# File that remembers which repos were already sent, so we don't repeat them.
SEEN_FILE = "seen_repos.json"
# Don't show the same repo again within this many days.
DEDUP_DAYS = 30


def load_seen_repos():
    """Load the {repo_name: ISO-date} map of repos already sent, pruning old entries."""
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            seen = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_DAYS)
    pruned = {}
    for name, date_str in seen.items():
        try:
            seen_date = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue
        if seen_date >= cutoff:
            pruned[name] = date_str
    return pruned


def save_seen_repos(seen):
    """Persist the {repo_name: ISO-date} map of repos already sent."""
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


def get_github_trending(since="daily"):
    """
    Get GitHub trending repositories.
    
    Args:
        since: Time period filter - 'daily' (today), 'weekly' (this week), or 'monthly' (this month)
    """
    url = f"https://github.com/trending?since={since}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    repos = []

    for article in soup.find_all("article", class_="Box-row"):
        try:
            # Get repo name and link
            h2 = article.find("h2")
            if not h2:
                continue
            
            link_elem = h2.find("a")
            if not link_elem:
                continue
            
            repo_name = link_elem.get("href", "").strip("/")
            repo_url = f"https://github.com{link_elem.get('href', '')}"
            
            # Get description
            description = ""
            desc_elem = article.find("p", class_="col-9")
            if desc_elem:
                description = desc_elem.get_text(strip=True)
            
            # Get stars
            stars = ""
            star_elem = article.find("span", class_="d-inline-block float-sm-right")
            if star_elem:
                stars = star_elem.get_text(strip=True)
            
            repo_info = f"{repo_name}\nDescription: {description}\nStars: {stars}\nURL: {repo_url}"
            repos.append({"name": repo_name, "info": repo_info})
        except Exception as e:
            continue

    return repos


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    OPENAI_KEY = os.getenv("OPENAI_KEY")
    
    # Validate environment variables
    if not OPENAI_KEY:
        raise ValueError("OPENAI_KEY environment variable is not set!")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")
    if not CHAT_ID:
        raise ValueError("CHAT_ID environment variable is not set!")

    client = OpenAI(api_key=OPENAI_KEY)

    feeds = [
        "https://venturebeat.com/category/ai/feed/",
        "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "https://tldr.tech/ai/rss"
    ]

    utc_now = datetime.now(timezone.utc)
    yesterday_start = (utc_now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)

    news = []

    for feed in feeds:
        parsed = feedparser.parse(feed)
        for entry in parsed.entries:
            entry_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            # Filter only yesterday's news
            if yesterday_start <= entry_date < yesterday_end:
                to_add = f"Fetched news: Datetime: {entry_date.strftime('%Y-%m-%d %H:%M:%S')} - {entry.title} ({entry.title_detail['value']})\nSUMMARY: {entry.summary_detail['value']}\nLink: {entry.link}"
                news.append(to_add)

    # Get trending repos, then drop any we've already sent recently.
    seen_repos = load_seen_repos()
    all_github_projects = get_github_trending()
    github_projects = [p for p in all_github_projects if p["name"] not in seen_repos]

    news_text = "\n".join(news)
    github_text = "\n".join(p["info"] for p in github_projects)

    # Send News to GPT separately
    news_prompt = f"""
    Analyze the following AI/Tech news and summarize the most important items.
    
    News:
    {news_text}
    
    USE ONLY THE INFORMATION PROVIDED ABOVE. DO NOT MAKE UP ANY NEWS.
    You are a tech radar assistant. Summarize the most important news items.
    News should be labeled with categories like "AI", "Cloud", "Security", "Data", "Startups", "Government", "Ethics", "Hardware", "Software".
    Every news item should have:
        1. datetime
        2. title
        3. a two-line summary
        4. a category label
        5. a link to the original article
        6. a brief explanation of why it matters
    """

    # Send GitHub to GPT separately
    github_prompt = f"""
    Analyze the following GitHub trending projects and summarize the most important ones.
    
    GitHub Projects:
    {github_text}
    
    USE ONLY THE INFORMATION PROVIDED ABOVE. DO NOT MAKE UP ANY PROJECTS.
    You are a tech radar assistant. Summarize the most important GitHub projects.
    Every github project should have:
        1. name
        2. a one-line description
        3. a link to the project
        4. a brief explanation of why it matters
    """

    # Get responses from GPT
    response_news = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": news_prompt}]
    )
    news_summary = response_news.choices[0].message.content

    if github_projects:
        response_github = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": github_prompt}]
        )
        github_summary = response_github.choices[0].message.content
    else:
        github_summary = "No new trending projects today."

    # Send to Telegram
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    print(f"\n📤 Sending to Telegram...")
    
    # Send News
    news_message = f"📰 AI Tech Radar - NEWS\n\n{news_summary}"
    telegram_data = {"chat_id": CHAT_ID, "text": news_message}
    
    try:
        tg_response = requests.post(telegram_url, data=telegram_data)
    except Exception as e:
        raise RuntimeError(f"❌ Error sending news: {e}")
    
    # Send GitHub
    github_message = f"⭐ AI Tech Radar - GITHUB\n\n{github_summary}"
    telegram_data = {"chat_id": CHAT_ID, "text": github_message}
    
    try:
        tg_response = requests.post(telegram_url, data=telegram_data)
    except Exception as e:
        raise RuntimeError(f"❌ Error sending github: {e}")

    # Remember the repos we just sent so they aren't repeated next runs.
    today = datetime.now(timezone.utc).isoformat()
    for project in github_projects:
        seen_repos[project["name"]] = today
    save_seen_repos(seen_repos)


if __name__ == "__main__":
    main()