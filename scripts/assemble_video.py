"""
Step 5: Combine assets/background.jpg + temp/korean_audio.mp3 into a YouTube-ready MP4
        using FFmpeg. No video recording needed — just a static branded image.
"""

import subprocess
import os
from datetime import datetime


BACKGROUND = "assets/background.jpg"
AUDIO = "temp/korean_audio.mp3"
OUTPUT = "temp/output.mp4"


def assemble_video():
    if not os.path.exists(BACKGROUND):
        raise FileNotFoundError(
            f"Background image not found: {BACKGROUND}\n"
            "Please add a branded JPG image at assets/background.jpg"
        )
    if not os.path.exists(AUDIO):
        raise FileNotFoundError(f"Audio file not found: {AUDIO}")

    print("[FFmpeg] Assembling video...")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", BACKGROUND,          # Static image input
        "-i", AUDIO,               # Korean audio input
        "-c:v", "libx264",         # Video codec
        "-tune", "stillimage",     # Optimised for still image
        "-c:a", "aac",             # Audio codec
        "-b:a", "192k",            # Audio bitrate
        "-pix_fmt", "yuv420p",     # Required for broad compatibility
        "-vf", "scale=1920:1080",  # Force 1080p output
        "-shortest",               # End when audio ends
        OUTPUT,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-2000:])
        raise RuntimeError("FFmpeg failed. See error above.")

    size_mb = os.path.getsize(OUTPUT) / (1024 * 1024)
    print(f"✅ Video saved to {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    assemble_video()
