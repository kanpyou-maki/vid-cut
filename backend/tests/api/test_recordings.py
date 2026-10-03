from tests.api.conftest import TOKEN, ApiEnv
from vidcut.api.security import TOKEN_HEADER


def recording_id(env: ApiEnv) -> str:
    (lecture,) = env.imported("a.mov")
    return str(lecture["recordings"][0]["id"])


class TestProxy:
    def test_serves_the_proxy_video(self, env: ApiEnv) -> None:
        response = env.client.get(f"/api/recordings/{recording_id(env)}/proxy")
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"
        assert response.headers["accept-ranges"] == "bytes"
        assert response.content == b"proxy"

    def test_serves_a_byte_range_for_seeking(self, env: ApiEnv) -> None:
        url = f"/api/recordings/{recording_id(env)}/proxy"
        response = env.client.get(url, headers={"Range": "bytes=1-3"})
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 1-3/5"
        assert response.content == b"rox"
        assert env.client.get(url, headers={"Range": "bytes=10-"}).status_code == 416

    def test_video_element_passes_the_token_in_the_query(self, env: ApiEnv) -> None:
        url = f"/api/recordings/{recording_id(env)}/proxy"
        headers = {TOKEN_HEADER: ""}
        assert env.client.get(url, params={"token": TOKEN}, headers=headers).status_code == 200
        assert env.client.get(url, headers=headers).status_code == 401

    def test_before_the_proxy_is_made(self, env: ApiEnv) -> None:
        added = env.data("POST", "/api/imports", json={"paths": [str(env.video("a.mov"))]})
        env.error(404, "GET", f"/api/recordings/{added['added'][0]['id']}/proxy")

    def test_unknown_recording_creates_no_directory(self, env: ApiEnv) -> None:
        env.error(404, "GET", "/api/recordings/nope/proxy")
        assert not (env.workspace / "recordings" / "nope").exists()


class TestPeaks:
    def test_returns_waveform_peaks(self, env: ApiEnv) -> None:
        data = env.data("GET", f"/api/recordings/{recording_id(env)}/peaks")
        assert data == {"per_second": 100, "values": [0.0, 0.5, 1.0]}

    def test_before_the_peaks_are_made(self, env: ApiEnv) -> None:
        added = env.data("POST", "/api/imports", json={"paths": [str(env.video("a.mov"))]})
        env.error(404, "GET", f"/api/recordings/{added['added'][0]['id']}/peaks")

    def test_unknown_recording(self, env: ApiEnv) -> None:
        env.error(404, "GET", "/api/recordings/nope/peaks")

    def test_unreadable_peaks_are_a_server_error_without_details(self, env: ApiEnv) -> None:
        rid = recording_id(env)
        (env.workspace / "recordings" / rid / "peaks.json").write_text("{broken")
        message = env.error(500, "GET", f"/api/recordings/{rid}/peaks")
        assert str(env.workspace) not in message
