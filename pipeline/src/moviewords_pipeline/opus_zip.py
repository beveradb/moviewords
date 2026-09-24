"""Access to the OPUS subtitle zip - the local download if present, otherwise
the published zip over HTTP range requests.

The remote path means re-indexing and re-counting don't need the 34GB
download (or a VM): the index stage reads only the zip's central directory
(~2 min), and the count stage fetches just the entries it hasn't cached,
one ranged GET each.
"""
import io
import struct
import threading
import zipfile
import zlib

import requests

from . import config

_LOCAL_HEADER = struct.Struct("<4s5H3I2H")   # 30 bytes, PKZIP local file header
_LOCAL_SIG = b"PK\x03\x04"
_EXTRA_SLACK = 1024   # local extra field is usually tiny; refetch if bigger


class _HttpRangeFile(io.RawIOBase):
    """Minimal seekable read-only file over HTTP range requests - just enough
    for zipfile to parse the central directory."""

    def __init__(self, url, session):
        self.url, self.session, self.pos = url, session, 0
        head = session.head(url, timeout=60)
        head.raise_for_status()
        self.size = int(head.headers["content-length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        data = _get_range(self.session, self.url, self.pos, self.pos + n - 1)
        self.pos += len(data)
        return data

    def readinto(self, buf):
        data = self.read(len(buf))
        buf[:len(data)] = data
        return len(data)


class RangeNotSupported(RuntimeError):
    """The server answered a Range request with the whole body. Not an
    OSError on purpose: zipfile would swallow that as 'not a zip file'."""


def _get_range(session, url, start, end):
    resp = session.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=120)
    resp.raise_for_status()
    if resp.status_code != 206:
        raise RangeNotSupported(f"server ignored Range request for {url}")
    return resp.content


class RemoteZip:
    """zipfile-like view of a remote zip: infolist() + a thread-safe read(name)
    that costs one ranged GET per member (sessions are per-thread)."""

    def __init__(self, url):
        self.url = url
        self._local = threading.local()
        with zipfile.ZipFile(_HttpRangeFile(url, self._session())) as z:
            self._infos = z.infolist()
        self._by_name = {i.filename: i for i in self._infos}

    def _session(self):
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def infolist(self):
        return self._infos

    def read(self, name):
        info = self._by_name[name]
        start = info.header_offset
        head_len = _LOCAL_HEADER.size + len(info.orig_filename.encode()) + _EXTRA_SLACK
        blob = _get_range(self._session(), self.url, start,
                          start + head_len + info.compress_size - 1)
        fields = _LOCAL_HEADER.unpack_from(blob)
        if fields[0] != _LOCAL_SIG:
            raise zipfile.BadZipFile(f"bad local header for {name}")
        data_start = _LOCAL_HEADER.size + fields[9] + fields[10]
        data_end = data_start + info.compress_size
        if data_end > len(blob):   # extra field bigger than the slack: refetch
            blob = _get_range(self._session(), self.url, start, start + data_end - 1)
        raw = blob[data_start:data_end]
        if info.compress_type == zipfile.ZIP_STORED:
            return raw
        if info.compress_type == zipfile.ZIP_DEFLATED:
            return zlib.decompress(raw, -15)
        raise NotImplementedError(f"compression {info.compress_type} for {name}")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_source(zip_path=None):
    """The local OPUS zip if it exists, else the remote one (config.OPUS_URL).
    Both expose infolist() and a thread-safe read(name)."""
    zip_path = zip_path or config.RAW_DIR / "opus_en.zip"
    if zip_path.exists():
        return zipfile.ZipFile(zip_path)
    print(f"{zip_path} not found - reading {config.OPUS_URL} over HTTP ranges")
    return RemoteZip(config.OPUS_URL)
