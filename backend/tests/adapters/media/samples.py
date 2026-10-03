"""integration テスト用の人工素材の生成と計測（スパイク S-1 と同じ作り。ADR-002）。

画面録画を模して、画面が変わったフレームだけを持つ可変フレームレートの素材を作る。
FLASH_TIMES_S の各時刻から 0.1 秒、白い画面とビープが同時に出る。最後の変化は 2.6 秒で、
映像はそこで終わるが、音声は DURATION_S まで続く（「映像が音声より先に終わる」問題の再現）。
"""

import array
import json
import subprocess
from pathlib import Path

FPS = 60
DURATION_S = 4.0
FLASH_TIMES_S = (0.5, 1.5, 2.5)
_FLASH_ON = "lt(t\\,3)*gte(mod(t\\,1)\\,0.5)*lt(mod(t\\,1)\\,0.6)"
_BEEP_ON = "lt(t\\,3)*gte(mod(t\\,1)\\,0.5)*lt(mod(t\\,1)\\,0.6)"
_RAW_AUDIO_RATE = 48_000


def make_vfr_source(dest: Path, *, audio_offset_s: float = 0.0) -> Path:
    """audio_offset_s だけ音声の開始を遅らせる（実素材は 51ms 遅れて始まる）。"""
    video = f"color=black:s=160x120:r={FPS}:d={DURATION_S},"
    video += f"drawbox=enable='{_FLASH_ON}':color=white:t=fill,mpdecimate"
    # volume の enable は 1024 サンプル単位でしか切り替わらないため、サンプル単位の式で作る
    audio = f"aevalsrc='0.5*sin(2*PI*1000*t)*{_BEEP_ON}':s={_RAW_AUDIO_RATE}:d={DURATION_S}"
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", video]
    args += ["-itsoffset", str(audio_offset_s), "-f", "lavfi", "-i", audio]
    args += ["-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0"]
    args += ["-c:a", "aac", str(dest)]
    subprocess.run(args, check=True, capture_output=True)
    return dest


def stream_info(path: Path, stream: str) -> dict[str, str]:
    args = ["ffprobe", "-v", "error", "-select_streams", stream, "-show_streams", "-of", "json"]
    out = subprocess.run([*args, str(path)], check=True, capture_output=True, text=True).stdout
    info: dict[str, str] = json.loads(out)["streams"][0]
    return info


def frame_brightness(path: Path) -> list[float]:
    """映像の各フレームの平均の明るさ（0〜255）。"""
    args = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0"]
    args += ["-vf", "scale=8:8,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(args, check=True, capture_output=True).stdout
    return [sum(raw[i : i + 64]) / 64 for i in range(0, len(raw), 64)]


def white_frame_starts(path: Path) -> list[int]:
    """暗い画面から白い画面に切り替わったフレーム番号。"""
    bright = [value > 128 for value in frame_brightness(path)]
    return [i for i, on in enumerate(bright) if on and (i == 0 or not bright[i - 1])]


def beep_starts_s(path: Path, *, rate: int = _RAW_AUDIO_RATE) -> list[float]:
    """無音からビープに切り替わった時刻（秒）。先頭の空白も含めタイムラインの時刻で測る。"""
    args = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0"]
    args += ["-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(rate)]
    args += ["-f", "s16le", "-"]
    raw = subprocess.run(args, check=True, capture_output=True).stdout
    loud = [abs(sample) > 3000 for sample in array.array("h", raw)]
    window = rate // 100  # 10ms 以内の途切れは同じビープとみなす
    starts: list[float] = []
    last_loud = -window
    for index, on in enumerate(loud):
        if on:
            if index - last_loud >= window:
                starts.append(index / rate)
            last_loud = index
    return starts
