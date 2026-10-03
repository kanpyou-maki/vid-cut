"""言い直しの判定のテスト用: 決まった出力を返す偽の言語モデルと、小さな解析結果。"""

import json
from collections.abc import Sequence

from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, SpeechChunk, Token
from vidcut.pipeline.analysis_result import Analysis

CHUNK_STEP_MS = 2_000
CHUNK_MS = 1_000


class FakeModel:
    """LanguageModel の偽の実装。outputs を順に返し、例外はその場で送出する。"""

    def __init__(self, outputs: Sequence[str | Exception]) -> None:
        self._outputs = list(outputs)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._outputs:
            raise AssertionError("言語モデルが想定より多く呼ばれました")
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def delete_output(*items: dict[str, object]) -> str:
    return json.dumps({"delete": list(items)}, ensure_ascii=False)


def make_analysis(rid: str, texts: Sequence[str]) -> Analysis:
    """チャンク i は 2i 秒から 1 秒間。texts[i] を 1 文字ずつのトークンにする（空ならなし）。

    無音の削除候補を 1 つ持つ（判定をやり直しても残る候補）。
    """
    chunks = tuple(
        SpeechChunk(
            id=f"{rid}-c{i:04d}",
            recording_id=rid,
            span=Interval(i * CHUNK_STEP_MS, i * CHUNK_STEP_MS + CHUNK_MS),
        )
        for i in range(len(texts))
    )
    tokens = tuple(
        Token(
            id=f"{chunk.id}-t{j:03d}",
            recording_id=rid,
            chunk_id=chunk.id,
            text=char,
            span=Interval(chunk.span.start_ms + j, chunk.span.start_ms + j + 1),
            asr_confidence=0.9,
            align_score=0.9,
        )
        for chunk, text in zip(chunks, texts, strict=True)
        for j, char in enumerate(text)
    )
    silence = CutSuggestion(
        id=f"{rid}-silence-0000",
        recording_id=rid,
        span=Interval(CHUNK_MS, CHUNK_STEP_MS),
        kind=CutKind.SILENCE,
        reason="無音 1.0 秒",
    )
    return Analysis(
        recording_id=rid,
        silences=(),
        chunks=chunks,
        tokens=tokens,
        suggestions=(silence,),
        review_marks=(),
    )
