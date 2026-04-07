#!/usr/bin/env python3
"""
Step 3.7: Review Korean script and bullet points before voice generation.

Uses GitHub Models (GPT-4o) — free, no extra API key needed on GitHub Actions.
Reads temp/korean_script.txt and temp/ticker_map.json, sends them to GPT-4o
for quality review, and overwrites with corrected versions.

Non-blocking: if review fails, the original files are kept intact.

Usage:
    python review_script.py
"""

import difflib
import json
import os
import re
import sys
import time

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Missing: pip install openai")

SCRIPT_FILE     = "temp/korean_script.txt"
TICKER_MAP_FILE = "temp/ticker_map.json"

GH_MODELS_URL = "https://models.inference.ai.azure.com"
MODEL         = "gpt-4o"
MAX_RETRIES   = 3
RETRY_DELAY   = 10


def call_gpt(client, system_prompt, user_content, min_chars=100):
    """Call GPT-4o via GitHub Models with retries."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [GPT-4o] attempt {attempt}/{MAX_RETRIES} "
                  f"({len(user_content):,} chars)...", flush=True)
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_content},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            text = response.choices[0].message.content.strip()
            if len(text) < min_chars:
                raise ValueError(f"Too short: {len(text)} < {min_chars}")
            print(f"  ✅ GPT-4o: {len(text):,} chars", flush=True)
            return text
        except Exception as e:
            last_error = e
            err_str = str(e)
            print(f"  Failed: {err_str[:200]}", flush=True)
            if "429" in err_str or "rate" in err_str.lower():
                print(f"  ⚠️  Rate limited — waiting {RETRY_DELAY * attempt}s", flush=True)
                time.sleep(RETRY_DELAY * attempt)
            elif attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    raise RuntimeError(f"All attempts failed. Last: {last_error}")


# ── Script review prompt ─────────────────────────────────────────────────────

SCRIPT_REVIEW_SYSTEM = """\
You are a senior Korean broadcast news editor reviewing a script before it goes
to the voice recording booth. This script will be read aloud by a news anchor.

Review the script and return a CORRECTED version. Fix these issues:

1. REPETITION
   - Remove sentences/facts that appear more than once across different stories
   - Remove redundant restatements within the same story
   - If two stories overlap significantly, merge the duplicate content into one

2. BROADCAST NATURALNESS
   - The text must sound natural when read aloud by a Korean news anchor
   - Replace stiff written-language patterns with spoken-language equivalents
   - Ensure smooth flow between sentences — no abrupt topic jumps
   - Headlines (소제목) should NOT be read aloud; the body should begin naturally
     and incorporate the topic without literally stating the headline

3. TRANSITIONS
   - Remove unnecessary filler transitions like "다음 뉴스입니다"
   - Each story should stand on its own without explicit segue phrases

4. DATA CONSISTENCY
   - If the same statistic appears in different stories, ensure the numbers match
   - Flag any obviously wrong numbers (e.g. "S&P 500이 50% 상승" for a weekly return)

5. OPENING & CLOSING
   - The opening line should be a natural greeting with date
   - The closing should end with "지금까지" pattern
   - Do NOT add or change the section tags ([시장개요], [뉴스], etc.)

6. ADVERTISEMENT REMOVAL
   - Remove ANY translated sponsor messages, product promotions, or service pitches
   - Remove podcast app promotions, subscription pitches, website URLs
   - Common ad patterns to remove:
     * "~의 지원/후원을 받습니다", "~에서 제공합니다"
     * Company pitches (IBM, Chase, Hartford, Odoo, TrueStage, CARE, etc.)
     * "~에서 자세히 알아보세요", "~를 방문하세요", "~닷컴"
     * Credit score services, insurance products, business software ads
     * "쇼 노트의 링크를 사용하여" or similar podcast self-references
   - If an entire story is just an ad, remove the story completely

7. FORMAT PRESERVATION (CRITICAL)
   - Keep ALL section tags exactly as they are: [시장개요], [주요등락], [섹터분석], [국가별], [뉴스]
   - In [뉴스], each story must remain: headline on one line, body on next line(s),
     separated from other stories by a blank line
   - Do NOT merge stories that cover genuinely different topics

Return ONLY the corrected script. No commentary, no markdown, no explanation."""


BULLETS_REVIEW_SYSTEM = """\
You are reviewing bullet points for a Korean financial news broadcast video overlay.
Each bullet appears on-screen alongside a chart during the news story.

Review and fix each section's bullets:

1. MEANINGFUL CONTENT
   - Each bullet must convey a specific fact or data point, not just a topic label
   - BAD: "테슬라" or "시장 동향" (just topic names)
   - GOOD: "테슬라 17% 급등" or "S&P 500 3% 상승" (specific facts)

2. LENGTH
   - Each bullet must be ≤ 20 Korean characters
   - If too long, shorten while keeping the key fact

3. RELEVANCE
   - Bullets must match the content of their section
   - Remove bullets that don't relate to the story

4. NO DUPLICATION
   - No repeated bullets within a section
   - No two bullets saying the same thing in different words

5. QUANTITY
   - Keep the same number of bullets per section (do not add or remove)

Return ONLY the corrected JSON object (same structure, same keys, updated bullets).
No markdown fences, no explanation."""


def show_tracked_changes(original, corrected):
    """Display changes like tracked changes — full text with deletions/additions highlighted."""
    orig_lines = original.splitlines(keepends=True)
    corr_lines = corrected.splitlines(keepends=True)

    diff = list(difflib.ndiff(orig_lines, corr_lines))

    print("\n── Tracked Changes ─────────────────────────────────", flush=True)
    has_changes = False
    for line in diff:
        code = line[0]
        text = line[2:].rstrip('\n')
        if code == ' ':
            # Unchanged line
            print(f"  {text}", flush=True)
        elif code == '-':
            # Deleted (strikethrough-style)
            print(f"  [-] {text}", flush=True)
            has_changes = True
        elif code == '+':
            # Added
            print(f"  [+] {text}", flush=True)
            has_changes = True
        # Skip '?' hint lines from ndiff

    if not has_changes:
        print("  (no changes)", flush=True)
    print("────────────────────────────────────────────────────\n", flush=True)


def review_script(client):
    """Review and correct the Korean script."""
    print("\n📝 Step 3.7a: Reviewing Korean script...", flush=True)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        original = f.read()

    print(f"  Original: {len(original):,} chars", flush=True)

    corrected = call_gpt(client, SCRIPT_REVIEW_SYSTEM, original,
                         min_chars=int(len(original) * 0.4))

    # Validate that section tags are preserved
    required_tags = ["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]", "[뉴스]"]
    missing = [t for t in required_tags if t not in corrected]
    if missing:
        print(f"  ⚠️  Corrected script missing tags: {missing} — keeping original", flush=True)
        return False

    # Show tracked changes
    show_tracked_changes(original, corrected)

    # Write corrected version
    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(corrected)

    delta = len(corrected) - len(original)
    print(f"  ✅ Script reviewed: {len(original):,} → {len(corrected):,} chars ({delta:+,})",
          flush=True)
    return True


def review_bullets(client):
    """Review and correct bullet points in ticker_map.json."""
    print("\n📝 Step 3.7b: Reviewing bullet points...", flush=True)

    with open(TICKER_MAP_FILE, "r", encoding="utf-8") as f:
        ticker_map = json.load(f)

    # Extract only news sections with bullets
    news_bullets = {}
    for section, data in ticker_map.items():
        bullets = data.get("bullets", [])
        if bullets:
            news_bullets[section] = bullets

    if not news_bullets:
        print("  ⚠️  No bullet points to review", flush=True)
        return True

    print(f"  Reviewing bullets for {len(news_bullets)} sections", flush=True)

    user_content = json.dumps(news_bullets, ensure_ascii=False, indent=2)
    raw = call_gpt(client, BULLETS_REVIEW_SYSTEM, user_content, min_chars=10)

    # Parse corrected bullets
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        corrected = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON parse error — keeping original bullets: {e}", flush=True)
        return False

    # Merge corrected bullets back into ticker_map
    changes = 0
    for section, new_bullets in corrected.items():
        if section in ticker_map and isinstance(new_bullets, list):
            old = ticker_map[section].get("bullets", [])
            if new_bullets != old:
                ticker_map[section]["bullets"] = new_bullets
                changes += 1
                print(f"    ✏️  {section[:40]}: {old} → {new_bullets}", flush=True)

    if changes:
        with open(TICKER_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(ticker_map, f, ensure_ascii=False, indent=2)
        print(f"  ✅ Updated bullets in {changes} section(s)", flush=True)
    else:
        print(f"  ✅ Bullets look good — no changes needed", flush=True)

    return True


def main():
    # GitHub Actions provides GITHUB_TOKEN automatically.
    # For local testing, use a personal access token.
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("GITHUB_TOKEN not set — required for GitHub Models API")

    if not os.path.exists(SCRIPT_FILE):
        sys.exit(f"Script not found: {SCRIPT_FILE}")

    client = OpenAI(base_url=GH_MODELS_URL, api_key=token)

    # Review script (non-blocking on failure)
    try:
        review_script(client)
    except Exception as e:
        print(f"  ⚠️  Script review failed — keeping original: {e}", flush=True)

    # Review bullets (non-blocking on failure)
    if os.path.exists(TICKER_MAP_FILE):
        try:
            review_bullets(client)
        except Exception as e:
            print(f"  ⚠️  Bullet review failed — keeping original: {e}", flush=True)
    else:
        print(f"⚠️  {TICKER_MAP_FILE} not found — skipping bullet review", flush=True)

    print("\n✅ Review complete", flush=True)


if __name__ == "__main__":
    main()
