# 🇰🇷 Korean News Podcast Bot

Automatically fetches English news podcasts, transcribes them, summarizes + translates to Korean, generates a voice-over, and uploads a daily video to YouTube — fully automated via GitHub Actions at zero cost.

---

## 📁 Project Structure

```
├── .github/workflows/daily_pipeline.yml  ← Cron schedule & pipeline
├── scripts/
│   ├── fetch_rss.py           ← Download latest podcast MP3s
│   ├── transcribe.py          ← Groq Whisper transcription
│   ├── summarize_translate.py ← Gemini summarize + Korean translation
│   ├── generate_voice.py      ← Edge TTS Korean voice
│   ├── assemble_video.py      ← FFmpeg: image + audio → MP4
│   └── upload_youtube.py      ← YouTube Data API upload
├── assets/
│   └── background.jpg         ← Your branded static image (add this!)
├── sources.json               ← Podcast RSS feed list
└── requirements.txt
```

---

## ⚙️ One-Time Setup

### 1. Add your background image
Place a branded 1920×1080 JPG at `assets/background.jpg`.

### 2. Get free API keys

| Service | Where to get | Free tier |
|---|---|---|
| **Groq** | console.groq.com | 7,200s audio/day |
| **Gemini** | aistudio.google.com | 1M tokens/day |
| **YouTube** | console.cloud.google.com | Free (OAuth) |

### 3. Generate a YouTube refresh token (once only)

Run this locally:
```bash
pip install google-auth-oauthlib
python get_youtube_token.py
```
Follow the browser OAuth flow. Copy the printed refresh token.

### 4. Add GitHub Secrets

Go to your repo → **Settings → Secrets → Actions** and add:

```
GROQ_API_KEY
GEMINI_API_KEY
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

### 5. Push to GitHub

Make sure the repository is **public** (required for free GitHub Actions minutes).

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

## ▶️ Running Manually

Trigger anytime via **GitHub → Actions → Daily Korean News Podcast → Run workflow**.

Or locally:
```bash
pip install -r requirements.txt
python scripts/fetch_rss.py
python scripts/transcribe.py       # needs GROQ_API_KEY env var
python scripts/summarize_translate.py  # needs GEMINI_API_KEY env var
python scripts/generate_voice.py
python scripts/assemble_video.py
python scripts/upload_youtube.py   # needs YOUTUBE_* env vars
```

---

## ➕ Adding More Podcast Sources

Edit `sources.json`:
```json
[
  {
    "name": "WSJ What's News",
    "rss": "https://video-api.wsj.com/podcast/rss/wsj/whats-news"
  },
  {
    "name": "Your Next Podcast",
    "rss": "https://example.com/podcast.rss"
  }
]
```

To find any podcast's RSS feed, search it on **podnews.net** and look for the RSS link at the bottom of the page.

---

## ⏰ Schedule

The pipeline runs daily at **6:00 AM UTC (3:00 PM KST)** via cron.
To change the time, edit the cron expression in `.github/workflows/daily_pipeline.yml`.
