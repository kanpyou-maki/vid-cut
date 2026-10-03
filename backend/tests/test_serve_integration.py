"""実物の `vidcut serve`（uvicorn と worker の子プロセス）を起動して確かめる。

TestClient は HTTP のパーサを通らないので、本文の長さの食い違いや重複したヘッダーなど、
パーサが関わる点はここで確かめる（M6 PR 2 のレビューからの持ち越し）。
"""

import contextlib
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from vidcut.api.frontend import TOKEN_META
from vidcut.api.security import TOKEN_HEADER
from vidcut.serve import FRONTEND_DIST_ENV, WORKSPACE_ENV

pytestmark = [
    pytest.mark.integration,
    # 子プロセスの確認に pgrep、待ち受けの確認に lsof を使う（macOS / Linux）
    pytest.mark.skipif(
        shutil.which("pgrep") is None or shutil.which("lsof") is None,
        reason="pgrep と lsof が必要",
    ),
]

STARTUP_TIMEOUT_S = 30.0
SHUTDOWN_TIMEOUT_S = 15.0
# 環境変数のプロキシ設定（http_proxy など）を使わず、直接つなぐ
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
INDEX = "<!doctype html><html><head><title>vid-cut</title></head><body></body></html>"


@dataclass(frozen=True)
class Server:
    process: subprocess.Popen[bytes]
    port: int
    log: Path
    token: str

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self.port}"

    def get(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
        request = urllib.request.Request(f"http://{self.host}{path}", headers=headers or {})
        try:
            with DIRECT.open(request, timeout=10) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def raw(self, request: bytes) -> bytes:
        """HTTP の要求をそのままのバイト列で送り、最初の応答を返す。"""
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as connection:
            connection.sendall(request)
            return connection.recv(65536)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def read_page(port: int) -> str | None:
    try:
        with DIRECT.open(f"http://127.0.0.1:{port}/", timeout=2) as response:
            return str(response.read().decode())
    except OSError:
        return None


def start_server(root: Path) -> Server:
    """一時ワークスペースで `vidcut serve` を起動し、画面を返すようになるまで待つ。"""
    dist = root / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    log = root / "serve.log"
    port = free_port()
    env = {**os.environ, WORKSPACE_ENV: str(root / "ws"), FRONTEND_DIST_ENV: str(dist)}
    with log.open("wb") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "vidcut.cli", "serve", "--port", str(port)],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,  # 後始末で、worker の子プロセスごと止められるようにする
        )
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        page = None
        while page is None:
            assert process.poll() is None, log.read_text(encoding="utf-8")
            assert time.monotonic() < deadline, "サーバーが時間内に起動しませんでした"
            page = read_page(port)
            time.sleep(0.1)
        found = re.search(rf'<meta name="{TOKEN_META}" content="([^"]+)"', page)
        assert found is not None
    except BaseException:
        kill_group(process)
        raise
    return Server(process=process, port=port, log=log, token=found.group(1))


def kill_group(process: subprocess.Popen[bytes]) -> None:
    """サーバーと、その子プロセス（worker）をまとめて強制終了する。テストの後始末用。"""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def worker_pid(server: Server) -> int:
    children = subprocess.run(
        ["pgrep", "-P", str(server.process.pid)], capture_output=True, text=True, check=False
    ).stdout.split()
    assert len(children) == 1, (children, server.log.read_text(encoding="utf-8"))
    return int(children[0])


def wait_until_gone(pid: int, what: str) -> None:
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(what)


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    started = start_server(tmp_path_factory.mktemp("serve"))
    try:
        yield started
    finally:
        kill_group(started.process)


def status_line(response: bytes) -> str:
    return response.split(b"\r\n", 1)[0].decode()


def post(server: Server, extra_headers: list[str], body: bytes) -> bytes:
    lines = [
        "POST /api/imports HTTP/1.1",
        f"Host: {server.host}",
        f"{TOKEN_HEADER}: {server.token}",
        "Content-Type: application/json",
        "Connection: close",
        *extra_headers,
    ]
    return server.raw("\r\n".join(lines).encode() + b"\r\n\r\n" + body)


class TestRealServer:
    def test_page_token_opens_the_api(self, server: Server) -> None:
        status, body = server.get("/api/lectures", {TOKEN_HEADER: server.token})
        assert (status, '"success":true' in body) == (200, True)
        assert server.get("/api/lectures")[0] == 401

    def test_listens_on_loopback_only(self, server: Server) -> None:
        listening = subprocess.run(
            ["lsof", "-nP", "-iTCP", f"-iTCP:{server.port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        assert f"127.0.0.1:{server.port}" in listening
        assert f"*:{server.port}" not in listening

    def test_body_longer_than_declared_is_not_read_as_one_request(self, server: Server) -> None:
        # 宣言した長さ（2 バイト）だけが本文になる。残りを本文として処理しない
        response = post(server, ["Content-Length: 2"], b'{}{"paths": ["/etc/hosts"]}')
        assert status_line(response).startswith("HTTP/1.1 422")

    def test_declared_length_over_the_limit_is_refused_before_reading(self, server: Server) -> None:
        response = post(server, ["Content-Length: 5000000"], b"")
        assert status_line(response).startswith("HTTP/1.1 413")

    def test_chunked_body_is_refused(self, server: Server) -> None:
        response = post(server, ["Transfer-Encoding: chunked"], b"2\r\n{}\r\n0\r\n\r\n")
        assert status_line(response).startswith("HTTP/1.1 411")

    def test_repeated_host_header_is_refused(self, server: Server) -> None:
        request = (
            f"GET /api/lectures HTTP/1.1\r\nHost: evil.example\r\nHost: {server.host}\r\n"
            f"{TOKEN_HEADER}: {server.token}\r\nConnection: close\r\n\r\n"
        )
        assert status_line(server.raw(request.encode())).startswith("HTTP/1.1 400")

    def test_other_host_is_refused(self, server: Server) -> None:
        status, body = server.get("/", {"Host": "evil.example"})
        assert status == 403
        assert server.token not in body

    def test_token_in_a_proxy_url_does_not_reach_the_log(self, server: Server) -> None:
        status, _ = server.get(f"/api/recordings/unknown/proxy?token={server.token}")
        assert status == 404  # トークンは通り、録画ファイルがない（この 404 はログに出る）
        # 次の要求に応えた時点で、前の要求のログは書き終わっている
        assert server.get("/api/lectures", {TOKEN_HEADER: server.token})[0] == 200
        log = server.log.read_text(encoding="utf-8")
        assert "/api/recordings/unknown/proxy" in log
        assert server.token not in log


class TestShutdown:
    """止め方ごとに、自分のサーバーを起動して確かめる。"""

    def test_sigterm_stops_the_server_and_the_worker(self, tmp_path: Path) -> None:
        server = start_server(tmp_path)
        try:
            worker = worker_pid(server)
            server.process.send_signal(signal.SIGTERM)
            assert server.process.wait(timeout=SHUTDOWN_TIMEOUT_S) == 0
            wait_until_gone(worker, "サーバーを止めても worker が残っています")
        finally:
            kill_group(server.process)

    def test_worker_exits_by_itself_when_the_server_is_killed(self, tmp_path: Path) -> None:
        # 強制終了では後始末が走らない。worker が親の終了に気づいて、自分で止まる
        server = start_server(tmp_path)
        try:
            worker = worker_pid(server)
            server.process.kill()
            server.process.wait(timeout=SHUTDOWN_TIMEOUT_S)
            wait_until_gone(worker, "サーバーを強制終了したあと、worker が残っています")
        finally:
            kill_group(server.process)
