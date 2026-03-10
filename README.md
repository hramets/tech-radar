# AI News Radar Bot

A Telegram bot that automatically collects AI, ML, and data-related news from multiple sources, summarizes the most important items using OpenAI, and sends a daily digest to your Telegram chat.  

The bot is fully automated using **GitHub Actions** — no server or local computer is needed.


## Features

- Aggregates news from:
  - RSS feeds (VentureBeat, MIT Technology Review, TLDR AI, etc.)
  - GitHub Trending projects
- Uses OpenAI API to summarize and select the **most important items**
- Sends daily digest to your **Telegram chat**
- Fully automated with **GitHub Actions** (daily cron job)
- Supports manual run from GitHub