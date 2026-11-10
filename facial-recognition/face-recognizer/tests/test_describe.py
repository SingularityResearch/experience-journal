"""describe.py: server addresses, the settings file, and that photos and the API key go only where they should."""
import http.server
import json

import pytest

import describe as D


@pytest.mark.parametrize("given, want", [
    ("127.0.0.1:1234", "http://127.0.0.1:1234"),
    ("http://192.168.1.20:1234/v1/", "http://192.168.1.20:1234"),
    ("https://ai.example.com/", "https://ai.example.com"),
    ("  nas:11434 ", "http://nas:11434"),
])
def test_clean_url(given, want):
    assert D.clean_url(given) == want


@pytest.mark.parametrize("bad", ["ftp://x", "http://", "http://host:port", "", "   "])
def test_clean_url_refuses(bad):
    with pytest.raises(ValueError):
        D.clean_url(bad)


@pytest.mark.parametrize("url, place, open_net", [
    ("http://127.0.0.1:1234", "this computer", False),
    ("http://localhost:1234", "this computer", False),
    ("http://192.168.1.20:1234", "your network", False),
    ("http://10.0.0.5", "your network", False),
    ("http://nas:1234", "your network", False),
    ("http://ai.example.com", "the internet", True),
    ("https://ai.example.com", "the internet", False),
])
def test_where(url, place, open_net):
    assert D.where(url) == (place, open_net)


def test_settings_round_trip_and_defaults(home):
    assert D.config() == {"use": "auto", "url": D.URL, "model": "", "key": ""}
    D.set_config(use="server", url="192.168.1.20:1234", model="m" * 300, key="k")
    c = D.config()
    assert c["use"] == "server" and c["url"] == "http://192.168.1.20:1234" and len(c["model"]) == 200 and c["key"] == "k"
    D.set_config(url="")
    assert D.config()["url"] == D.URL
    with pytest.raises(ValueError):
        D.set_config(use="sometimes")
    (home / "describe.json").write_text("{not json", "utf-8")
    assert D.config()["use"] == "auto"                       # a damaged file gives the defaults


def test_key_stays_with_its_server(home):
    D.set_config(url="http://127.0.0.1:1234", key="SECRET")
    D.set_config(url="http://127.0.0.1:1234")                # same address: kept
    assert D.config()["key"] == "SECRET"
    D.set_config(url="http://192.168.1.20:1234")             # another address: forgotten
    assert D.config()["key"] == ""
    D.set_config(url="http://192.168.1.21:1234", key="NEW")  # given together with the address: kept
    assert D.config()["key"] == "NEW"


def test_status_never_contains_the_key(home, monkeypatch):
    D.set_config(key="SECRET")
    monkeypatch.setattr(D, "server_models", lambda *a, **k: (_ for _ in ()).throw(D.Unavailable("down")))
    s = D.status()
    assert s["config"]["key"] is True and "SECRET" not in json.dumps(s)


class _Recorder(http.server.BaseHTTPRequestHandler):
    """Remembers what it was asked; /redirect sends the client to another server."""
    seen, target = [], None

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).seen.append((self.server.server_address[1], self.path, self.headers.get("Authorization")))
        if self.path.startswith("/api/v0/") and type(self).target:
            self.send_response(302)
            self.send_header("Location", type(self).target + "/steal")
            self.end_headers()
            return
        body = b'{"data": [{"id": "m1"}]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_no_redirects_and_no_key_to_other_servers(home, serve):
    _Recorder.seen, _Recorder.target = [], None
    other = serve(_Recorder)
    _Recorder.target = other
    redirecting = serve(_Recorder)
    other_port = int(other.rsplit(":", 1)[1])
    D.set_config(url=redirecting, key="SECRET")
    assert D.server_models() == ([("m1", None)], [])         # the 302 wasn't followed: asked the standard way
    assert not [s for s in _Recorder.seen if s[0] == other_port]
    assert {s[2] for s in _Recorder.seen if s[0] != other_port} == {"Bearer SECRET"}
    D.test(other)                                            # Test on another address: not with the saved key
    sent = [s[2] for s in _Recorder.seen if s[0] == other_port]
    assert sent and set(sent) == {None}


def test_answers_are_capped(home, serve, monkeypatch):
    monkeypatch.setattr(D, "MAX_ANSWER", 10)
    _Recorder.seen, _Recorder.target = [], None
    url = serve(_Recorder)
    with pytest.raises(ValueError):
        D._open(D.urllib.request.Request(url + "/v1/models"), 5)
