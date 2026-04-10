#!/usr/bin/env python3
"""
Step 3.6: Review Korean script and bullet points before voice generation.

- Script review: uses Gemini (65K output tokens, no truncation risk)
- Bullet review: uses GPT-4o via GitHub Models (short output, free)

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

try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("Missing: pip install google-genai")

SCRIPT_FILE     = "temp/korean_script.txt"
TICKER_MAP_FILE = "temp/ticker_map.json"

# GitHub Models (GPT-4o) — for bullet review (short output)
GH_MODELS_URL = "https://models.inference.ai.azure.com"
GPT_MODEL     = "gpt-4o"

# Gemini — for script review (long output)
# Model fallback chain — ordered by quality, with separate RPD quotas.
# NOTE: gemini-3.1-flash-lite-preview has 8K max output (truncates long text!)
#       so it goes LAST, after gemini-2.5-flash-lite which has 65K output.
GEMINI_MODELS = [
    "gemini-3-flash-preview",       # 65K output, 20 RPD
    "gemini-2.5-flash",             # 65K output, 20 RPD
    "gemini-2.5-flash-lite",        # 65K output, ~100 RPD
    "gemini-3.1-flash-lite-preview", # 8K output only — last resort
]

MAX_RETRIES = 3
RETRY_DELAY = 10


def call_gemini(gemini_client, prompt, min_chars=100):
    """Call Gemini with model fallback chain. For long-output tasks."""
    last_error = None
    for model in GEMINI_MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  [Gemini] {model} attempt {attempt}/{MAX_RETRIES} "
                      f"({len(prompt):,} chars)...", flush=True)
                cfg = types.GenerateContentConfig(
                    max_output_tokens=65536,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                )
                response = gemini_client.models.generate_content(
                    model=model, contents=prompt, config=cfg,
                )
                text = response.text.strip()
                if len(text) < min_chars:
                    raise ValueError(f"Too short: {len(text)} < {min_chars}")
                print(f"  ✅ {model}: {len(text):,} chars", flush=True)
                return text
            except Exception as e:
                last_error = e
                err_str = str(e)
                print(f"  Failed: {err_str[:200]}", flush=True)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"  ⚠️  Rate limited — skipping to next model", flush=True)
                    break
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        print(f"  All retries failed for {model}, trying next...", flush=True)
    raise RuntimeError(f"All Gemini models failed. Last: {last_error}")


def call_gpt(gpt_client, system_prompt, user_content, min_chars=100):
    """Call GPT-4o via GitHub Models. For short-output tasks (bullets)."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [GPT-4o] attempt {attempt}/{MAX_RETRIES} "
                  f"({len(user_content):,} chars)...", flush=True)
            response = gpt_client.chat.completions.create(
                model=GPT_MODEL,
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
    raise RuntimeError(f"All GPT-4o attempts failed. Last: {last_error}")


# ── Script review prompt ─────────────────────────────────────────────────────

SCRIPT_REVIEW_PROMPT = """\
You are a senior Korean broadcast news editor reviewing a script before it goes
to the voice recording booth. This script will be read aloud by a news anchor.

CRITICAL: This is an EDITING task, NOT a summarization task.
Preserve the overall length and detail of each story. Do NOT shorten,
compress, or summarize stories. Only make targeted fixes to specific issues.
The corrected script should be roughly the SAME LENGTH as the original.

Review the script and return a CORRECTED version. Fix ONLY these issues:

1. REPETITION (remove only truly duplicated content)
   - Remove sentences/facts that are EXACTLY repeated across different stories
   - Do NOT remove similar-but-different coverage of the same topic
   - Do NOT merge stories — keep each story as a separate entry

2. BROADCAST NATURALNESS (light touch only)
   - Fix only clearly unnatural phrasing — do not rewrite entire sentences
   - Ensure smooth flow between sentences — no abrupt topic jumps
   - Headlines (소제목) must remain as separate lines — do NOT merge them into body

3. TRANSITIONS
   - Remove unnecessary filler transitions like "다음 뉴스입니다"

4. DATA CONSISTENCY
   - If the same statistic appears in different stories, ensure the numbers match

5. OPENING & CLOSING
   - The opening line should be a natural greeting with date
   - The closing should end with "지금까지" pattern
   - Do NOT add or change the section tags ([시장개요], [뉴스], etc.)

6. ADVERTISEMENT REMOVAL
   - Remove ONLY clear advertisements — sponsor messages, product promotions, URLs
   - Do NOT remove actual news content even if it mentions a company

7. [리서치] SECTION — DO NOT TOUCH
   - The [리서치] section contains expert analysis from investment banks
     (Morgan Stanley, Goldman Sachs, JP Morgan, Barclays)
   - Do NOT edit, rephrase, shorten, or restructure [리서치] content
   - Preserve all analyst names, data points, forecasts, and reasoning
   - Only fix obvious typos or remove clear advertisements
   - The research tone is intentionally different from news — keep it as-is

8. FORMAT PRESERVATION (CRITICAL)
   - Keep ALL section tags exactly as they are: [시장개요], [뉴스], [리서치], [주요등락], [섹터분석], [국가별]
   - In [뉴스] and [리서치], each story must remain: headline on one line,
     body on next line(s), separated from other stories by a blank line
   - Do NOT merge, combine, or remove stories
   - Do NOT shorten story bodies — preserve all facts, quotes, and numbers

Return ONLY the corrected script. No commentary, no markdown, no explanation.

SCRIPT TO REVIEW:
"""


BULLETS_REVIEW_SYSTEM = """\
You are reviewing bullet points for a Korean financial news broadcast video overlay.
Each bullet appears on-screen alongside a chart during the news story.
The audience is general Korean investors, NOT finance professionals.

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

5. QUANTITY FOR 뉴스 sections
   - Keep the same number of bullets per section (do not add or remove)

6. JARGON DEFINITIONS FOR 리서치 sections (IMPORTANT)
   - For sections starting with "리서치:", ADD extra bullets that explain
     any technical/jargon terms used in the story body
   - Format: "📖 [term]: [1-line Korean definition]"
   - No character limit for these definition bullets
   - Add as many as needed — every jargon term should be explained
   - Examples:
     "📖 CLO: 대출채권을 묶어 만든 투자상품"
     "📖 수요 파괴: 가격이 너무 올라 소비가 줄어드는 현상"
     "📖 큐비트: 양자컴퓨터의 연산 단위로 0과 1을 동시에 처리"
     "📖 사모 대출: 은행이 아닌 민간 펀드가 기업에 직접 빌려주는 대출"
     "📖 환매 제한: 투자금 인출이 일시적으로 제한되는 조치"
     "📖 스프레드: 두 금리 사이의 차이"
     "📖 레버리지: 빌린 돈으로 투자 규모를 키우는 것"
   - Place these definition bullets AFTER the regular fact bullets

Return ONLY the corrected JSON object (same structure, same keys, updated bullets).
No markdown fences, no explanation."""


def _inline_diff(old_line, new_line):
    """Show word-level changes within a line. Returns formatted string."""
    sm = difflib.SequenceMatcher(None, old_line, new_line)
    old_parts, new_parts = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            old_parts.append(old_line[i1:i2])
            new_parts.append(new_line[j1:j2])
        elif op == 'replace':
            old_parts.append(f"«{old_line[i1:i2]}»")
            new_parts.append(f"→«{new_line[j1:j2]}»")
        elif op == 'delete':
            old_parts.append(f"«{old_line[i1:i2]}»")
        elif op == 'insert':
            new_parts.append(f"→«{new_line[j1:j2]}»")
    return ''.join(old_parts), ''.join(new_parts)


def show_tracked_changes(original, corrected):
    """Display changes with inline highlights showing exactly what changed."""
    orig_lines = original.splitlines()
    corr_lines = corrected.splitlines()

    sm = difflib.SequenceMatcher(None, orig_lines, corr_lines)

    print("\n── Tracked Changes ─────────────────────────────────", flush=True)
    has_changes = False

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for line in orig_lines[i1:i2]:
                print(f"  {line}", flush=True)
        elif op == 'replace':
            # Show inline diff for each pair of changed lines
            for k in range(max(i2 - i1, j2 - j1)):
                old = orig_lines[i1 + k] if i1 + k < i2 else ""
                new = corr_lines[j1 + k] if j1 + k < j2 else ""
                if old == new:
                    print(f"  {old}", flush=True)
                elif old and new:
                    old_fmt, new_fmt = _inline_diff(old, new)
                    print(f"  [-] {old_fmt}", flush=True)
                    print(f"  [+] {new_fmt}", flush=True)
                elif old:
                    print(f"  [-] {old}", flush=True)
                else:
                    print(f"  [+] {new}", flush=True)
            has_changes = True
        elif op == 'delete':
            for line in orig_lines[i1:i2]:
                print(f"  [REMOVED] {line}", flush=True)
            has_changes = True
        elif op == 'insert':
            for line in corr_lines[j1:j2]:
                print(f"  [ADDED] {line}", flush=True)
            has_changes = True

    if not has_changes:
        print("  (no changes)", flush=True)
    print("────────────────────────────────────────────────────\n", flush=True)


def review_script(gemini_client):
    """Review and correct the Korean script using Gemini (long output)."""
    print("\n📝 Step 3.6a: Reviewing Korean script (Gemini)...", flush=True)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        original = f.read()

    print(f"  Original: {len(original):,} chars", flush=True)

    prompt = SCRIPT_REVIEW_PROMPT + original
    corrected = call_gemini(gemini_client, prompt,
                            min_chars=int(len(original) * 0.4))

    # Validate that section tags are preserved
    required_tags = ["[시장개요]", "[뉴스]", "[주요등락]", "[섹터분석]", "[국가별]"]
    # [리서치] is optional — may not exist if no research sources available
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


def review_bullets(gpt_client):
    """Review and correct bullet points using GPT-4o (short output)."""
    print("\n📝 Step 3.6b: Reviewing bullet points (GPT-4o)...", flush=True)

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
    raw = call_gpt(gpt_client, BULLETS_REVIEW_SYSTEM, user_content, min_chars=10)

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


RESEARCH_JARGON_PROMPT = """\
You are a Korean financial education editor. Your job is to make investment
research accessible to general Korean investors who are NOT finance professionals.

Below is the [리서치] section from a Korean financial broadcast script.
For EACH sentence that contains technical jargon or complex financial terms,
add TWO lines immediately after it:

LINE 1: Define each jargon term in that sentence (plain Korean, one line)
LINE 2: Start with "쉽게 말해," and re-explain the whole sentence simply

FORMAT — three lines per complex sentence:
[original sentence unchanged]
[jargon term]은/는 [definition]. [another term]은/는 [definition].
쉽게 말해, [plain re-explanation of the whole sentence].

Example:
사모 대출 시장이 리테일 기구의 환매 제한과 기초 자산의 실적 변화라는 두 가지 도전에 직면했다고 분석했습니다.
사모 대출은 은행을 거치지 않는 민간 대출이며, 환매 제한은 투자금 인출을 일시적으로 막는 조치입니다.
쉽게 말해, 민간 대출 시장에서 투자자들이 돈을 빼려 하자 펀드들이 인출을 막고 있고, 대출받은 기업들의 실적도 흔들리고 있다는 뜻입니다.

Example:
CLO 시장처럼 이번 위기를 거치며 사모 대출은 금융 시스템 내에서 더욱 중요한 자산군으로 자리 잡을 전망입니다.
CLO는 대출채권을 묶어 만든 투자상품입니다.
쉽게 말해, 과거에도 대출채권 시장이 위기 후에 더 성장한 것처럼, 민간 대출도 이번 시련을 거쳐 오히려 더 커질 것이라는 전망입니다.

Rules:
- Do NOT change original sentences — keep them word-for-word
- Do NOT use arrows (→) or parentheses for definitions
- Do NOT put definitions inside the original sentence
- Skip sentences that are already simple and clear (no jargon)
- Non-[리서치] sections must be returned unchanged
- Return the COMPLETE script (all sections), not just [리서치]

IMPORTANT — Only define terms that a regular Korean investor watching
evening news would NOT understand. Only explain specialized/technical
terms that require finance expertise to understand.

Do NOT define any of these (too common, everyone knows):
인플레이션, GDP, 금리, 연준, Fed, 유가, 환율, IPO, ETF,
S&P 500, 나스닥, 다우, 국채, 채권, 주식, 배당, 시가총액,
금리 인상, 금리 인하, 성장 둔화, 재정 적자, 무역수지,
상승, 하락, 급등, 급락, 분기 실적, 보조금, 배럴,
자산군, 레버리지, 스프레드, 가격 재발견, 가치 사슬

SCRIPT:
"""


def review_research_jargon(gemini_client):
    """Add jargon definitions and easy explanations to [리서치] section."""
    print("\n📝 Step 3.6c: Adding jargon explanations to research (Gemini)...", flush=True)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        original = f.read()

    # Only process if [리서치] section exists
    if "[리서치]" not in original:
        print("  ⚠️  No [리서치] section found — skipping", flush=True)
        return False

    prompt = RESEARCH_JARGON_PROMPT + original
    corrected = call_gemini(gemini_client, prompt,
                            min_chars=int(len(original) * 0.9))

    # Validate all sections preserved
    required_tags = ["[시장개요]", "[뉴스]", "[리서치]"]
    missing = [t for t in required_tags if t not in corrected]
    if missing:
        print(f"  ⚠️  Missing tags after jargon pass: {missing} — keeping original", flush=True)
        return False

    # Show what was added
    original_lines = len(original.splitlines())
    corrected_lines = len(corrected.splitlines())
    added = corrected_lines - original_lines

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(corrected)

    print(f"  ✅ Jargon explanations added: {original_lines} → {corrected_lines} lines (+{added} explanation lines)",
          flush=True)
    return True


def main():
    # Gemini client for script review + jargon (long output)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        print("⚠️  GEMINI_API_KEY not set — skipping script review", flush=True)
        gemini_client = None
    else:
        gemini_client = genai.Client(api_key=gemini_key)

    # GPT-4o client for bullet review (short output)
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if not gh_token:
        print("⚠️  GITHUB_TOKEN not set — skipping bullet review", flush=True)
        gpt_client = None
    else:
        gpt_client = OpenAI(base_url=GH_MODELS_URL, api_key=gh_token)

    if not os.path.exists(SCRIPT_FILE):
        sys.exit(f"Script not found: {SCRIPT_FILE}")

    # Step 3.6a: Review script with Gemini (non-blocking on failure)
    if gemini_client:
        try:
            review_script(gemini_client)
        except Exception as e:
            print(f"  ⚠️  Script review failed — keeping original: {e}", flush=True)

    # Step 3.6b: Add jargon explanations to [리서치] (non-blocking)
    if gemini_client:
        try:
            review_research_jargon(gemini_client)
        except Exception as e:
            print(f"  ⚠️  Jargon review failed — keeping original: {e}", flush=True)

    # Step 3.6c: Review bullets with GPT-4o (non-blocking on failure)
    if gpt_client and os.path.exists(TICKER_MAP_FILE):
        try:
            review_bullets(gpt_client)
        except Exception as e:
            print(f"  ⚠️  Bullet review failed — keeping original: {e}", flush=True)
    elif not os.path.exists(TICKER_MAP_FILE):
        print(f"⚠️  {TICKER_MAP_FILE} not found — skipping bullet review", flush=True)

    print("\n✅ Review complete", flush=True)


if __name__ == "__main__":
    main()
