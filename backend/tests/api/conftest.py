from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.pipeline.fakes import FakeAligner, FakeMediaTool, FakeTranscriber, FakeVad
from tests.pipeline.judge_fakes import FakeModel
from vidcut.api.app import ApiSettings, create_app
from vidcut.api.security import TOKEN_HEADER, local_guard
from vidcut.bootstrap import Api, MlTools, build_api, build_app

TOKEN = "test-token-" + "x" * 32
BASE_URL = "http://127.0.0.1:8765"
NOTHING_TO_DELETE = '{"delete": []}'
"""偽の言語モデルの既定の応答（言い直しなし）。"""
MAX_JUDGEMENTS_PER_RUN = 20
"""run_worker 1 回で偽の言語モデルが答えられる判定の回数（超えるとテストが失敗する）。"""


@dataclass(frozen=True)
class ApiEnv:
    app: FastAPI
    client: TestClient
    api: Api
    workspace: Path
    home: Path
    media: FakeMediaTool

    def video(self, name: str) -> Path:
        """ホームの Movies に動画ファイルを作る（中身は名前ごとに違う）。"""
        path = self.home / "Movies" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        return path.resolve()

    def run_worker(self, *judge_outputs: str | Exception) -> None:
        """worker プロセスの代わりに、積まれたジョブをすべて処理する（ML と判定は偽の実装）。"""
        outputs = judge_outputs or (NOTHING_TO_DELETE,) * MAX_JUDGEMENTS_PER_RUN
        app = build_app(
            self.workspace,
            media=self.media,
            ml=MlTools(vad=FakeVad(), transcriber=FakeTranscriber(), aligner=FakeAligner()),
            model=FakeModel(list(outputs)),
        )
        try:
            app.worker().run_until_idle()
        finally:
            app.close()

    def data(self, method: str, url: str, **kwargs: Any) -> Any:
        """成功した応答の data。"""
        response = self.client.request(method, url, **kwargs)
        body = response.json()
        assert response.status_code == 200, body
        assert (body["success"], body["error"]) == (True, None)
        return body["data"]

    def error(self, status: int, method: str, url: str, **kwargs: Any) -> str:
        """失敗した応答の error（利用者に見せる文）。"""
        response = self.client.request(method, url, **kwargs)
        body = response.json()
        assert response.status_code == status, body
        assert (body["success"], body["data"]) == (False, None)
        assert isinstance(body["error"], str) and body["error"]
        return str(body["error"])

    def imported(self, *names: str) -> list[dict[str, Any]]:
        """動画を取り込み、解析と判定まで済ませて、レクチャーの一覧を返す。"""
        paths = [str(self.video(name)) for name in names]
        self.data("POST", "/api/imports", json={"paths": paths})
        self.run_worker()
        lectures: list[dict[str, Any]] = self.data("GET", "/api/lectures")
        return lectures


def build_env(tmp_path: Path, media: FakeMediaTool | None = None) -> ApiEnv:
    """ホームは tmp_path/home、ワークスペースはその下の VidCut。"""
    home = tmp_path / "home"
    home.mkdir()
    workspace = home / "VidCut"
    media_tool = media or FakeMediaTool()
    api = build_api(workspace, media=media_tool)
    app = create_app(api, ApiSettings(guard=local_guard(TOKEN, port=8765), home=home))
    client = TestClient(
        app, base_url=BASE_URL, headers={TOKEN_HEADER: TOKEN}, raise_server_exceptions=False
    )
    return ApiEnv(app=app, client=client, api=api, workspace=workspace, home=home, media=media_tool)


@pytest.fixture
def env(tmp_path: Path) -> ApiEnv:
    return build_env(tmp_path)
