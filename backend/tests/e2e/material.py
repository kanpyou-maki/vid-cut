"""E2E の素材: 台本（script.py）の区間でだけ音が鳴る、十数秒の録画ファイルを ffmpeg で作る。"""

import subprocess
from pathlib import Path

from tests.e2e.script import DURATION_MS, LINES

_SIZE = "320x180"
_FPS = 30
_AUDIO_RATE = 48_000


def make_lesson(dest: Path, tone_hz: int) -> None:
    """dest に素材を書く。音はステレオ（書き出しがステレオを前提にしている）。"""
    seconds = DURATION_MS / 1000
    # volume の enable は 1024 サンプル単位でしか切り替わらないため、サンプル単位の式で作る
    speaking = "+".join(
        f"between(t\\,{line.span.start_ms / 1000}\\,{line.span.end_ms / 1000})" for line in LINES
    )
    video = f"testsrc2=s={_SIZE}:r={_FPS}:d={seconds}"
    audio = f"aevalsrc='0.4*sin(2*PI*{tone_hz}*t)*({speaking})':s={_AUDIO_RATE}:d={seconds}"
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    args += ["-f", "lavfi", "-i", video, "-f", "lavfi", "-i", audio]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2"]
    subprocess.run([*args, str(dest.resolve())], check=True, capture_output=True)
