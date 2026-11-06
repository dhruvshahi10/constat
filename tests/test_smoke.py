"""The post-install smoke test, run in-process against a fresh API."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import smoke  # noqa: E402
from tests.test_api_questionnaires import H, client  # noqa: E402,F401 - the API fixture


class TestClientHttp:
    """The smoke script's Http protocol over FastAPI's TestClient."""

    def __init__(self, c):
        self.c = c

    @staticmethod
    def _out(r):
        return r.status_code, (r.json() if "json" in r.headers.get("content-type", "") else r.content)

    def get(self, path):
        return self._out(self.c.get(path, headers=H))

    def post(self, path, body=None):
        return self._out(self.c.post(path, headers=H, json=body or {}))

    def upload(self, path, fields, filename, data):
        return self._out(self.c.post(path, headers=H, data=fields,
                                     files={"file": (filename, data, "application/octet-stream")}))


def test_smoke_passes_on_a_fresh_install(client):
    rep = smoke.run(TestClientHttp(client), wait_s=30, poll_s=0.1)
    assert rep.ok, rep.render()
    assert len(rep.checks) == 12


def test_smoke_fails_loudly_when_the_api_is_down():
    class Down:
        def get(self, path):
            return 503, b"unavailable"
    rep = smoke.run(Down())
    assert not rep.ok and rep.checks[0][0] == "healthz answers ok" and "503" in rep.render()
