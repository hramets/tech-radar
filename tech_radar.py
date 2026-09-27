from datetime import datetime, timedelta, timezone
import feedparser
import requests
from openai import OpenAI
import os


# Telegram allows 4096 characters per message; keep a margin for emoji,
# which Telegram counts as two characters.
TELEGRAM_MAX_LEN = 4000


def split_message(text, limit=TELEGRAM_MAX_LEN):
    """Split text into chunks under the limit, preferring paragraph and line breaks."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text.strip():
        chunks.append(text)
    return chunks


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
        "https://tldr.tech/ai/rss",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://simonwillison.net/atom/everything/",
        "https://blogs.nvidia.com/feed/"
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

    news_text = "\n".join(news)

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

    # Get responses from GPT
    response_news = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": news_prompt}]
    )
    news_summary = response_news.choices[0].message.content

    # Send to Telegram
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    print(f"\n📤 Sending to Telegram...")
    
    # Send News (split into several messages if it exceeds Telegram's limit)
    news_message = f"📰 AI Tech Radar - NEWS\n\n{news_summary}"

    for part in split_message(news_message):
        try:
            tg_response = requests.post(telegram_url, data={"chat_id": CHAT_ID, "text": part})
        except Exception as e:
            raise RuntimeError(f"❌ Error sending news: {e}")
        if not tg_response.ok:
            raise RuntimeError(f"❌ Telegram rejected message ({tg_response.status_code}): {tg_response.text}")


if __name__ == "__main__":
    main()