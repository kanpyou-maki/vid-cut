#!/usr/bin/env python3
"""Udemy 録画の無音・言い直しを自動カットする。

使い方: python3 udemy_cut.py 入力.mov [-o 出力.mp4]

流れ:
  1. 音声抽出 → 無音検出で「発話チャンク」に分割（カット点は必ず無音の中になる）
  2. チャンクごとに whisper.cpp で文字起こし
  3. claude -p にチャンク一覧を渡し、言い直し・言い損じのチャンクを判定
  4. 残すチャンクを前後に余白を付けてつなぎ、ffmpeg で書き出す
中間ファイルは <出力名>_work/ に残し、再実行時は再利用する（--redo で判定からやり直し）。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

WHISPER_CLI = Path.home() / "Projects/whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = Path.home() / "Projects/whisper.cpp/models/ggml-medium.bin"

SILENCE_DB = -40      # これより小さい音を無音とみなす
SILENCE_MIN = 0.3     # この秒数以上続く無音で区切る
PAD_BEFORE = 0.15     # 残すチャンクの前に付ける余白（秒）
PAD_AFTER = 0.25      # 後ろに付ける余白（秒）
FPS = 60              # 出力フレームレート

JUDGE_PROMPT = """\
以下は Udemy 講座の録画を無音で区切った発話チャンクの一覧です（id, 開始秒, 終了秒, 文字起こし）。
文字起こしは Whisper によるもので、誤変換や句読点の欠落があります。

講師は録画中に言い直しをしています。完成動画に不要なチャンクの id を判定してください。

削除対象:
- 言い直し: 同じ内容をもう一度話し直している場合、**最後に話した版を残し**、それより前の版を削除する。
  言い直しは直後とは限らず、数チャンク後に戻って話し直すこともある。
  一部だけ重なっている場合は、前の版のうち後の版と重複する範囲のチャンクを削除する。
- 言い損じ: 途中で途切れた文、噛んだ断片、内容として成立しない短い発話。
- 独り言・フィラーだけのチャンク（「えー」「あれ」「もう一回」など）、無音やノイズの誤認識。

削除しないもの:
- 講義として意味のある発話。強調のための意図的な繰り返し（言い回しを変えて畳みかける等）。
- 判断に迷うものは残す（誤って内容を消すほうが害が大きい）。

チャンクは文の途中で切れていることが多い。前後のチャンクとつなげて文として読んだうえで判断すること。
削除した結果、残ったチャンクをつなげて自然な講義になるかを最後に確認すること。

出力は次の JSON のみ（前置き・コードブロック不要）:
{"delete": [{"id": 3, "reason": "id 5 で言い直し"}, ...]}

チャンク一覧:
"""


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def media_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def detect_speech(wav, duration):
    """silencedetect の結果を反転して発話区間 [(start, end)] を返す。"""
    err = run(["ffmpeg", "-i", str(wav), "-af",
               f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"],
              capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    speech, cursor = [], 0.0
    for s, e in zip(starts, ends + [duration]):
        if s - cursor > 0.1:
            speech.append((cursor, s))
        cursor = e
    if duration - cursor > 0.1:
        speech.append((cursor, duration))
    return speech


def transcribe_chunks(wav, speech, work):
    """チャンクごとに切り出して whisper.cpp に一括で渡す（モデル読み込みは1回）。"""
    cdir = work / "chunks"
    cdir.mkdir(exist_ok=True)
    files = []
    for i, (s, e) in enumerate(speech):
        f = cdir / f"{i:04d}.wav"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
             "-i", str(wav), "-c:a", "pcm_s16le", str(f)])
        files.append(f)
    cmd = [str(WHISPER_CLI), "-m", str(WHISPER_MODEL), "-l", "ja", "-np", "-otxt"]
    for f in files:
        cmd += ["-f", str(f)]
    run(cmd, capture_output=True)
    chunks = []
    for i, ((s, e), f) in enumerate(zip(speech, files)):
        txt = Path(str(f) + ".txt")
        text = txt.read_text().strip().replace("\n", " ") if txt.exists() else ""
        chunks.append({"id": i, "start": round(s, 3), "end": round(e, 3), "text": text})
    return chunks


def judge(chunks):
    listing = "\n".join(f'{c["id"]}\t{c["start"]:.1f}\t{c["end"]:.1f}\t{c["text"]}' for c in chunks)
    out = run(["claude", "-p", "--output-format", "text"], input=JUDGE_PROMPT + listing,
              capture_output=True, text=True).stdout
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        sys.exit(f"判定結果を JSON として読めません:\n{out}")
    return json.loads(m.group(0))["delete"]


def keep_ranges(chunks, deleted_ids, duration):
    ranges = []
    for c in chunks:
        if c["id"] in deleted_ids:
            continue
        s = max(0.0, c["start"] - PAD_BEFORE)
        e = min(duration, c["end"] + PAD_AFTER)
        if ranges and s <= ranges[-1][1]:
            ranges[-1][1] = e
        else:
            ranges.append([s, e])
    return ranges


def render(src, ranges, dst):
    """trim/atrim + concat で1回だけ再エンコードする。つなぎ目は音声を短くフェード。"""
    # 画面録画は可変フレームレート（静止中はフレームがほぼ無い）なので、
    # 先に固定フレームレート化しないと区間頭のフレームが欠けて音ズレする
    parts = [f"[0:v]fps={FPS},split={len(ranges)}" + "".join(f"[s{i}]" for i in range(len(ranges)))]
    labels = []
    for i, (s, e) in enumerate(ranges):
        fade = min(0.03, (e - s) / 4)
        parts.append(f"[s{i}]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={fade:.3f},afade=t=out:st={e - s - fade:.3f}:d={fade:.3f}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(ranges)}:v=1:a=1[v][a]")
    script = dst.with_suffix(".filter.txt")
    script.write_text(";\n".join(parts))
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
         "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
         "-c:v", "h264_videotoolbox", "-q:v", "60", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(dst)])
    script.unlink()


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--redo", action="store_true", help="判定をやり直す（文字起こしは再利用）")
    args = ap.parse_args()

    src = args.input.resolve()
    dst = args.output or src.with_name(src.stem + "_cut.mp4")
    work = dst.with_name(dst.stem + "_work")
    work.mkdir(exist_ok=True)
    duration = media_duration(src)

    chunks_json = work / "chunks.json"
    if chunks_json.exists():
        chunks = json.loads(chunks_json.read_text())
    else:
        wav = work / "audio.wav"
        print("音声を抽出・無音検出中…")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(wav)])
        speech = detect_speech(wav, duration)
        print(f"{len(speech)} チャンクを文字起こし中…")
        chunks = transcribe_chunks(wav, speech, work)
        chunks_json.write_text(json.dumps(chunks, ensure_ascii=False, indent=1))

    judge_json = work / "judge.json"
    if judge_json.exists() and not args.redo:
        deletes = json.loads(judge_json.read_text())
    else:
        print("言い直しを判定中（claude -p）…")
        deletes = judge(chunks)
        judge_json.write_text(json.dumps(deletes, ensure_ascii=False, indent=1))

    reasons = {d["id"]: d.get("reason", "") for d in deletes}
    ranges = keep_ranges(chunks, set(reasons), duration)

    report = [f"入力: {src.name}  {fmt(duration)} → 出力 {fmt(sum(e - s for s, e in ranges))}", ""]
    for c in chunks:
        mark = f"✂ {reasons[c['id']]}" if c["id"] in reasons else " "
        report.append(f"{c['id']:3d} {fmt(c['start'])}-{fmt(c['end'])} {c['text']}")
        if c["id"] in reasons:
            report.append(f"      {mark}")
    report_path = dst.with_suffix(".report.txt")
    report_path.write_text("\n".join(report) + "\n")

    print(f"{len(ranges)} 区間をつないで書き出し中…")
    render(src, ranges, dst)
    print(f"完了: {dst}\nカット一覧: {report_path}")


if __name__ == "__main__":
    main()
