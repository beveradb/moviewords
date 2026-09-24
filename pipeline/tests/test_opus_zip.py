import zipfile

import pytest

from moviewords_pipeline import opus_zip


class _Resp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(self.status_code)


def _fake_session_cls(blob, ignore_range=False):
    """requests.Session stand-in serving `blob` with HTTP Range semantics."""
    class FakeSession:
        requests_made = []

        def head(self, url, timeout=None):
            return _Resp(200, headers={"content-length": str(len(blob))})

        def get(self, url, headers=None, timeout=None):
            FakeSession.requests_made.append(headers["Range"])
            if ignore_range:
                return _Resp(200, blob)
            start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
            if start >= len(blob):
                return _Resp(416)
            return _Resp(206, blob[start:end + 1])
    return FakeSession


def _zip_bytes(tmp_path, members, compression=zipfile.ZIP_DEFLATED):
    path = tmp_path / "t.zip"
    with zipfile.ZipFile(path, "w", compression=compression) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path.read_bytes()


MEMBERS = {
    "OpenSubtitles/raw/en/2013/993846/1.xml": b"<document>" + b"<s>fuck</s>" * 5000 + b"</document>",
    "OpenSubtitles/raw/en/2013/993846/2.xml": b"<document><s>featurette</s></document>",
}


@pytest.mark.parametrize("compression", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
def test_remote_zip_lists_and_reads_members(tmp_path, monkeypatch, compression):
    blob = _zip_bytes(tmp_path, MEMBERS, compression)
    monkeypatch.setattr(opus_zip.requests, "Session", _fake_session_cls(blob))
    z = opus_zip.RemoteZip("https://example.test/en.zip")
    assert sorted(i.filename for i in z.infolist()) == sorted(MEMBERS)
    for name, data in MEMBERS.items():
        assert z.read(name) == data


def test_remote_zip_read_is_one_ranged_get(tmp_path, monkeypatch):
    blob = _zip_bytes(tmp_path, MEMBERS)
    session_cls = _fake_session_cls(blob)
    monkeypatch.setattr(opus_zip.requests, "Session", session_cls)
    z = opus_zip.RemoteZip("https://example.test/en.zip")
    before = len(session_cls.requests_made)
    z.read("OpenSubtitles/raw/en/2013/993846/1.xml")
    assert len(session_cls.requests_made) - before == 1


def test_remote_zip_refuses_server_that_ignores_range(tmp_path, monkeypatch):
    blob = _zip_bytes(tmp_path, MEMBERS)
    monkeypatch.setattr(opus_zip.requests, "Session",
                        _fake_session_cls(blob, ignore_range=True))
    with pytest.raises(opus_zip.RangeNotSupported):
        opus_zip.RemoteZip("https://example.test/en.zip")


def test_open_source_prefers_local_zip(tmp_path, monkeypatch):
    local = tmp_path / "opus_en.zip"
    local.write_bytes(_zip_bytes(tmp_path, MEMBERS))

    def boom(url):
        raise AssertionError("remote zip opened despite local copy")
    monkeypatch.setattr(opus_zip, "RemoteZip", boom)
    with opus_zip.open_source(local) as z:
        assert isinstance(z, zipfile.ZipFile)


def test_open_source_falls_back_to_remote(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(opus_zip, "RemoteZip", lambda url: opened.append(url) or url)
    assert opus_zip.open_source(tmp_path / "missing.zip") == opus_zip.config.OPUS_URL
    assert opened == [opus_zip.config.OPUS_URL]
