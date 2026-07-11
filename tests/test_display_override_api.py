from display_override_api import _is_private_client, create_override_app


def test_private_client_detection():
    assert _is_private_client("127.0.0.1")
    assert _is_private_client("192.168.1.20")
    assert _is_private_client("fd00::1")
    assert not _is_private_client("8.8.8.8")
    assert not _is_private_client("invalid")


def test_override_api_accepts_json_and_path():
    calls = []
    app = create_override_app(
        lambda module: calls.append(module) or {"accepted": True, "module": module},
        lambda: {"cleared": True},
        lambda: {"module": None},
    )
    client = app.test_client()

    assert client.post("/api/display", json={"module": "weather"}).status_code == 202
    assert client.post("/api/display/codex").status_code == 202
    assert calls == ["weather", "codex"]
    assert client.get("/api/display").get_json() == {"module": None}
    assert client.delete("/api/display").get_json() == {"cleared": True}


def test_override_api_validates_access_auth_and_payload():
    app = create_override_app(
        lambda module: {"accepted": False, "error": "unknown module"},
        lambda: {},
        lambda: {},
        token="secret",
    )
    client = app.test_client()

    assert (
        client.get("/api/display", environ_base={"REMOTE_ADDR": "8.8.8.8"}).status_code
        == 403
    )
    assert client.get("/api/display").status_code == 401
    headers = {"Authorization": "Bearer secret"}
    assert client.post("/api/display", headers=headers, json={}).status_code == 400
    assert client.post("/api/display/nope", headers=headers).status_code == 404
