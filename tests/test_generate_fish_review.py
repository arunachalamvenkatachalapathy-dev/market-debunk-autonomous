from pathlib import Path
import pytest
from scripts.generate_fish_review import generate, MODEL, ELITE

class Response:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content

class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def post(self, url, **kw):
        self.calls.append((url, kw))
        return next(self.responses)

def test_review_developer_request(tmp_path):
    s = Session([Response(200, b"ID3" + bytes(2000))])
    out = generate("Hello.", tmp_path / "one.mp3", "private-key", session=s)
    assert out.read_bytes().startswith(b"ID3")
    url, kw = s.calls[0]
    assert url == "https://api.fish.audio/v1/tts"
    assert kw["headers"]["model"] == MODEL
    assert kw["headers"]["Authorization"] == "Bearer private-key"
    assert kw["json"]["reference_id"] == ELITE
    assert kw["json"]["text"] == "Hello."

def test_429_retries_then_success(tmp_path):
    s = Session([Response(429), Response(200, b"ID3" + bytes(2000))])
    generate("Hello.", tmp_path / "one.mp3", "private-key", session=s, sleep=lambda _: None)
    assert len(s.calls) == 2

def test_invalid_response_not_written(tmp_path):
    s = Session([Response(200, b"<html>paywall</html>" * 150)])
    with pytest.raises(RuntimeError, match="recognizable MP3"):
        generate("Hello.", tmp_path / "one.mp3", "private-key", session=s)
    assert not (tmp_path / "one.mp3").exists()

def test_auth_error_does_not_retry_or_write(tmp_path):
    s = Session([Response(401)])
    with pytest.raises(RuntimeError, match="401"):
        generate("Hello.", tmp_path / "one.mp3", "private-key", session=s)
    assert len(s.calls) == 1
    assert not (tmp_path / "one.mp3").exists()
