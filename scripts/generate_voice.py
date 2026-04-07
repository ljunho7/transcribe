"""
Step 4: Split Korean script by section and generate one MP3 per section/story.
Output: temp/audio/01_시장개요.mp3, 02_주요등락.mp3, ..., 05_story_001.mp3, etc.
"""

import asyncio, os, re, time, subprocess
from pathlib import Path

# Edge TTS — free neural Korean voices, no API key needed
try:
    import edge_tts
    TTS_ENGINE = "edge"
except ImportError:
    try:
        from gtts import gTTS
        TTS_ENGINE = "gtts"
    except ImportError:
        raise ImportError("Install edge-tts or gTTS: pip install edge-tts")

SCRIPT_FILE = "temp/korean_script.txt"
AUDIO_DIR   = Path("temp/audio")

# Edge TTS voice — ko-KR-SunHiNeural (female, news anchor style)
# Alternative: ko-KR-InJoonNeural (male)
EDGE_VOICE  = "ko-KR-SunHiNeural"
EDGE_RATE   = "+10%"   # slightly faster than default (natural news pace)

# gTTS fallback settings
GTTS_LANG   = "ko"
GTTS_SPEED  = 1.5      # playback speed multiplier for gTTS only

PAUSE_SECTION = 1.5  # seconds of silence between market sections
PAUSE_STORY   = 1.0  # seconds of silence between news stories


# ── Korean TTS normalization ─────────────────────────────────────────────────
# Maps English terms and symbols to Korean pronunciation for natural TTS output.

_TERM_MAP = {
    # Indices & Markets
    "S&P 500":  "에스앤피 오백",
    "S&P500":   "에스앤피 오백",
    "S&P":      "에스앤피",
    "NASDAQ":   "나스닥",
    "Nasdaq":   "나스닥",
    "DOW":      "다우",
    "NYSE":     "뉴욕증권거래소",
    "SOX":      "필라델피아 반도체",
    "DXY":      "달러인덱스",
    "VIX":      "빅스",
    "ETF":      "이티에프",
    "KOSPI":    "코스피",
    "KOSDAQ":   "코스닥",
    # Economic terms
    "GDP":      "지디피",
    "CPI":      "소비자물가지수",
    "PCE":      "개인소비지출",
    "PPI":      "생산자물가지수",
    "Fed":      "연준",
    "FED":      "연준",
    "FOMC":     "연방공개시장위원회",
    "IMF":      "아이엠에프",
    "ECB":      "유럽중앙은행",
    "OPEC":     "오펙",
    "OPEC+":    "오펙플러스",
    "IEA":      "국제에너지기구",
    "WTI":      "서부텍사스산 중질유",
    "LNG":      "엘엔지",
    "IPO":      "기업공개",
    "M&A":      "인수합병",
    "ESG":      "이에스지",
    "AI":       "에이아이",
    "CEO":      "최고경영자",
    "CFO":      "최고재무책임자",
    "ICE":      "이민세관집행국",
    "SEC":      "증권거래위원회",
    "NASA":     "나사",
    "AP":       "에이피",
    "FT":       "파이낸셜타임스",
    # Units
    "bp":       "베이시스포인트",
    "bps":      "베이시스포인트",
    # Currencies (as standalone)
    "USD":      "달러",
    "EUR":      "유로",
    "JPY":      "엔",
    "KRW":      "원",
    "GBP":      "파운드",
    "CNY":      "위안",
}


def _num_to_korean(n_str):
    """Convert a number string to Korean reading. Handles integers and decimals."""
    DIGITS = {
        '0': '영', '1': '일', '2': '이', '3': '삼', '4': '사',
        '5': '오', '6': '육', '7': '칠', '8': '팔', '9': '구',
    }
    UNITS = ['', '십', '백', '천']
    BIG_UNITS = ['', '만', '억', '조']

    # Handle decimal
    if '.' in n_str:
        integer_part, decimal_part = n_str.split('.', 1)
        int_ko = _num_to_korean(integer_part)
        dec_ko = ''.join(DIGITS.get(c, c) for c in decimal_part)
        return f"{int_ko}점{dec_ko}"

    # Remove commas
    n_str = n_str.replace(',', '')
    if not n_str or not n_str.isdigit():
        return n_str

    n = int(n_str)
    if n == 0:
        return '영'

    # Group into 4-digit chunks (만, 억, 조)
    chunks = []
    while n > 0:
        chunks.append(n % 10000)
        n //= 10000

    parts = []
    for i, chunk in enumerate(chunks):
        if chunk == 0:
            continue
        chunk_str = ''
        for j in range(4):
            digit = (chunk // (10 ** j)) % 10
            if digit == 0:
                continue
            if digit == 1 and j > 0:
                chunk_str = UNITS[j] + chunk_str
            else:
                chunk_str = DIGITS[str(digit)] + UNITS[j] + chunk_str
        parts.append(chunk_str + BIG_UNITS[i])

    return ''.join(reversed(parts))


def normalize_for_tts(text):
    """Normalize Korean text for natural TTS reading."""
    # 1. Replace known English terms (longest first to avoid partial matches)
    for eng, kor in sorted(_TERM_MAP.items(), key=lambda x: -len(x[0])):
        text = text.replace(eng, kor)

    # 2. Currency: "$1,234.56" → "천이백삼십사점오육 달러"
    #    Handle "$N달러" (remove redundant 달러 after conversion)
    def _dollar_replace(m):
        return _num_to_korean(m.group(1)) + ' 달러'
    text = re.sub(r'\$([0-9,]+(?:\.[0-9]+)?)달러', _dollar_replace, text)
    text = re.sub(r'\$([0-9,]+(?:\.[0-9]+)?)', _dollar_replace, text)

    # 3. Percentage: "3.5%" → "삼점오 퍼센트"
    def _pct_replace(m):
        return _num_to_korean(m.group(1)) + ' 퍼센트'
    text = re.sub(r'([0-9,]+(?:\.[0-9]+)?)%', _pct_replace, text)

    # 4. Standalone numbers with commas or decimals (e.g., "6,611.83", "21,996")
    #    Only convert if followed by Korean text or end of word (not mid-English)
    def _num_replace(m):
        return _num_to_korean(m.group(1))
    text = re.sub(r'(?<![A-Za-z])([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?)(?![A-Za-z])', _num_replace, text)

    # 5. Simple numbers before Korean units: "10년" → "십년", "206,000배럴"
    def _num_unit_replace(m):
        return _num_to_korean(m.group(1)) + m.group(2)
    text = re.sub(r'([0-9,]+(?:\.[0-9]+)?)(년|월|일|시|분|배럴|갤런|달러|원|조|억|만)', _num_unit_replace, text)

    return text

SECTION_ORDER = ["[시장개요]", "[주요등락]", "[섹터분석]", "[국가별]", "[뉴스]"]
SECTION_NAMES = {
    "[시장개요]": "시장개요",
    "[주요등락]": "주요등락",
    "[섹터분석]": "섹터분석",
    "[국가별]":   "국가별",
    "[뉴스]":     "뉴스",
}


def parse_sections(script):
    """Split script into {tag: text} dict in order."""
    sections = {}
    current_tag = None
    current_lines = []

    for line in script.split("\n"):
        stripped = line.strip()
        if stripped in SECTION_ORDER:
            if current_tag and current_lines:
                sections[current_tag] = "\n".join(current_lines).strip()
            current_tag = stripped
            current_lines = []
        else:
            if current_tag:
                current_lines.append(line)

    if current_tag and current_lines:
        sections[current_tag] = "\n".join(current_lines).strip()

    return sections


def parse_news_stories(news_text):
    """Split [뉴스] section into individual stories."""
    stories = []
    current_headline = None
    current_body = []

    for line in news_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        is_headline = (
            5 < len(line) < 35
            and not line.endswith("다.")
            and not line.endswith("다")
            and not line.endswith(".")
        )

        if is_headline and current_headline is None:
            # First headline — treat preceding text as intro
            stories.append({"headline": "뉴스 브리핑", "text": line})
            current_headline = line
            current_body = []
        elif is_headline:
            if current_body:
                stories.append({
                    "headline": current_headline,
                    "text": "\n".join(current_body)
                })
            current_headline = line
            current_body = []
        else:
            current_body.append(line)

    if current_headline and current_body:
        stories.append({
            "headline": current_headline,
            "text": "\n".join(current_body)
        })

    return stories


def append_silence(audio_path, seconds):
    """Append silence to an audio file using FFmpeg."""
    if seconds <= 0:
        return
    tmp = audio_path.with_suffix(".withpause.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-af", f"apad=pad_dur={seconds}",
        "-q:a", "2",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        tmp.rename(audio_path)
    else:
        try:
            tmp.unlink()
        except Exception:
            pass


async def _edge_tts(text, path):
    """Generate audio using Edge TTS (neural voice)."""
    communicate = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE)
    await communicate.save(str(path))


def _gtts_fallback(text, path):
    """Generate audio using gTTS (robotic but reliable fallback)."""
    from gtts import gTTS
    tts = gTTS(text=text, lang=GTTS_LANG, slow=False)
    tts.save(str(path))
    # Speed up gTTS output (it's slow by default)
    if GTTS_SPEED != 1.0:
        tmp = path.with_suffix(".tmp.mp3")
        path.rename(tmp)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(tmp),
            "-filter:a", f"atempo={GTTS_SPEED}",
            "-q:a", "2",
            str(path)
        ], capture_output=True, check=True)
        tmp.unlink()


def tts_to_file(text, path, retries=3, pause=0):
    """Generate TTS audio with retry and optional trailing pause.
    Uses Edge TTS (neural) with gTTS as fallback."""
    text = normalize_for_tts(text.strip())
    if not text:
        print(f"  ⚠️  Empty text for {path.name}, skipping", flush=True)
        return False

    for attempt in range(1, retries+1):
        try:
            if TTS_ENGINE == "edge":
                asyncio.run(_edge_tts(text, path))
                engine_label = f"Edge/{EDGE_VOICE}"
            else:
                _gtts_fallback(text, path)
                engine_label = f"gTTS/{GTTS_SPEED}x"

            if pause > 0:
                append_silence(path, pause)
            size = path.stat().st_size
            print(f"  ✅ {path.name}  ({len(text):,} chars, {size:,} bytes, {engine_label}"
                  f"{f', +{pause}s pause' if pause else ''})", flush=True)
            return True
        except Exception as e:
            print(f"  ⚠️  TTS attempt {attempt} failed ({TTS_ENGINE}): {e}", flush=True)
            # If Edge TTS fails, try gTTS fallback on last attempt
            if attempt == retries and TTS_ENGINE == "edge":
                try:
                    print(f"  ↪ Falling back to gTTS...", flush=True)
                    _gtts_fallback(text, path)
                    if pause > 0:
                        append_silence(path, pause)
                    size = path.stat().st_size
                    print(f"  ✅ {path.name}  ({len(text):,} chars, {size:,} bytes, gTTS fallback"
                          f"{f', +{pause}s pause' if pause else ''})", flush=True)
                    return True
                except Exception as e2:
                    print(f"  ⚠️  gTTS fallback also failed: {e2}", flush=True)
            if attempt < retries:
                time.sleep(5)
    return False


def generate_voice():
    os.makedirs(AUDIO_DIR, exist_ok=True)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        script = f.read()

    sections = parse_sections(script)
    print(f"📝 Sections found: {list(sections.keys())}", flush=True)

    manifest = []  # ordered list of (audio_path, section_tag, headline)

    for i, tag in enumerate(SECTION_ORDER):
        text = sections.get(tag, "")
        if not text:
            print(f"  ⚠️  Missing section: {tag}", flush=True)
            continue

        if tag == "[뉴스]":
            stories = parse_news_stories(text)
            print(f"\n📰 [뉴스]: {len(stories)} stories", flush=True)
            for j, story in enumerate(stories):
                fname = AUDIO_DIR / f"05_story_{j+1:03d}.mp3"
                full_text = f"{story['headline']}\n{story['text']}"
                ok = tts_to_file(full_text, fname, pause=PAUSE_STORY)
                if ok:
                    manifest.append({
                        "audio":    str(fname),
                        "section":  "[뉴스]",
                        "headline": story["headline"],
                    })
        else:
            fname = AUDIO_DIR / f"{i+1:02d}_{SECTION_NAMES[tag]}.mp3"
            print(f"\n🎙️  {tag}", flush=True)
            ok = tts_to_file(text, fname, pause=PAUSE_SECTION)
            if ok:
                manifest.append({
                    "audio":   str(fname),
                    "section": tag,
                    "headline": "",
                })

    # Save manifest for assemble_video.py
    import json
    manifest_path = AUDIO_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Generated {len(manifest)} audio files → {AUDIO_DIR}", flush=True)


if __name__ == "__main__":
    generate_voice()
