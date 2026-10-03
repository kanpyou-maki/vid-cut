from tests.api.conftest import ApiEnv


class TestFs:
    def test_lists_home_by_default(self, env: ApiEnv) -> None:
        env.video("a.mov")
        data = env.data("GET", "/api/fs")
        assert data["path"] == str(env.home.resolve())
        assert data["parent"] is None
        assert [(e["name"], e["kind"]) for e in data["entries"]] == [
            ("Movies", "directory"),
            ("VidCut", "directory"),
        ]

    def test_lists_folders_and_videos_with_absolute_paths(self, env: ApiEnv) -> None:
        video = env.video("a.mov")
        (video.parent / "notes.txt").write_text("x")
        data = env.data("GET", "/api/fs", params={"path": str(video.parent)})
        assert data["parent"] == str(env.home.resolve())
        assert data["entries"] == [{"name": "a.mov", "path": str(video), "kind": "video"}]
        assert data["truncated"] is False

    def test_outside_home_is_refused(self, env: ApiEnv) -> None:
        assert "ホーム" in env.error(422, "GET", "/api/fs", params={"path": "/etc"})

    def test_hidden_folder_is_refused(self, env: ApiEnv) -> None:
        (env.home / ".ssh").mkdir()
        message = env.error(422, "GET", "/api/fs", params={"path": str(env.home / ".ssh")})
        assert "隠し" in message

    def test_missing_folder(self, env: ApiEnv) -> None:
        env.error(404, "GET", "/api/fs", params={"path": str(env.home / "nope")})

    def test_overlong_path_is_refused(self, env: ApiEnv) -> None:
        env.error(422, "GET", "/api/fs", params={"path": "/" + "a" * 5000})
