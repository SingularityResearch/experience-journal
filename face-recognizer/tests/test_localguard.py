"""localguard: the request checks every server uses, and its bind / error-answer helpers."""
import sys

import pytest

import localguard as G

PORT = 8765


def why(headers, write=False):
    return G.refuse_reason(headers, PORT, write)


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765"])
def test_own_host_is_allowed(host):
    assert why({"Host": host}) is None


@pytest.mark.parametrize("host", ["", "evil.example:8765", "127.0.0.1:8766", "127.0.0.1", "127.0.0.1.evil.example:8765"])
def test_other_hosts_are_refused(host):
    # DNS rebinding: a website's own name pointed at 127.0.0.1 still says its name in Host
    assert why({"Host": host}) is not None


def test_writes_need_the_header_and_own_origin():
    ok = {"Host": "127.0.0.1:8765", "X-Face-Tool": "1"}
    assert why(ok, write=True) is None
    assert why({**ok, "Origin": "http://127.0.0.1:8765"}, write=True) is None
    assert why({"Host": "127.0.0.1:8765"}, write=True) is not None                     # no header
    assert why({**ok, "X-Face-Tool": "yes"}, write=True) is not None
    for origin in ("null", "https://evil.example", "http://127.0.0.1:8764"):
        assert why({**ok, "Origin": origin}, write=True) is not None


def test_frame_parents_are_only_the_app_window():
    assert G.FRAME_PARENTS >= {"http://127.0.0.1:8764"}
    assert all(p.startswith(("http://127.0.0.1:", "http://localhost:")) for p in G.FRAME_PARENTS)


@pytest.mark.skipif(sys.platform != "win32", reason="address reuse only lets two programs share a port on Windows")
def test_a_second_bind_of_the_same_port_fails():
    first = G.bind(0)
    try:
        with pytest.raises(OSError):
            G.bind(first.server_address[1])
    finally:
        first.server_close()


def test_answer_errors_turns_a_crash_into_a_500():
    sent = []
    G.answer_errors(None, lambda: {}["missing"], lambda body, code: sent.append((code, body)))
    assert sent and sent[0][0] == 500 and "KeyError" in sent[0][1]["error"]
    sent.clear()
    G.answer_errors(None, lambda: None, lambda body, code: sent.append(code))
    assert sent == []
