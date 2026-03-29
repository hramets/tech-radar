from datetime import datetime, timedelta, timezone
import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import os


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
            repos.append(repo_info)
        except Exception as e:
            continue

    return repos


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    OPENAI_KEY = os.getenv("OPENAI_KEY")

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

    github_projects = get_github_trending()

    news_text = "\n".join(news)
    github_text = "\n".join(github_projects)

    prompt = f"""
    News:
    {news_text}

    GitHub:
    {github_text}
    USE ONLY THE INFORMATION PROVIDED ABOVE. DO NOT MAKE UP ANY NEWS OR PROJECTS.
    You are a tech radar assistant. Your job is to analyze the latest news and GitHub projects in technology and AI, Data, ML, and summarize the most important ones for a tech-savvy audience.
    Select important news from this list.
    Make two sections: "News" and "GitHub".
    News should be labeled with categories like "AI", "Cloud", "Security", "Data", "Startups", "Government", "Ethics", "Hardware", "Software".
    Every news item should have:
        1. datetime
        2. title
        3. a two-line summary
        4. a category label
        5. a link to the original article
        6. a brief explanation of why it matters
    Every github project should have:
        1. name
        2. a one-line description
        3. a link to the project
        4. a brief explanation of why it matters

    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    summary = response.choices[0].message.content

    message = f"🧠 AI Tech Radar\n\n{summary}"

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": message}
    )

if __name__ == "__main__":
    main()