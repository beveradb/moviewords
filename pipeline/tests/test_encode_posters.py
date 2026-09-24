import shutil
import subprocess

import pytest

import scripts_path  # noqa: F401
import encode_posters as mod


def test_pending_skips_posters_with_avif(tmp_path):
    for name in ("tt1.jpg", "tt2.jpg", "tt2.avif", "tt3.jpg", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in mod.pending(tmp_path)] == ["tt1.jpg", "tt3.jpg"]


def test_avifenc_cmd_is_single_threaded_at_quality(tmp_path):
    cmd = mod.avifenc_cmd(tmp_path / "a.jpg", tmp_path / "a.avif", 55)
    assert cmd[0] == "avifenc"
    assert cmd[cmd.index("-q") + 1] == "55"
    assert cmd[cmd.index("-j") + 1] == "1"
    assert cmd[-2:] == [str(tmp_path / "a.jpg"), str(tmp_path / "a.avif")]


def test_encode_one_failure_leaves_no_partial(tmp_path):
    bad = tmp_path / "tt9.jpg"
    bad.write_bytes(b"not a jpeg")
    if shutil.which("avifenc") is None:
        pytest.skip("avifenc not installed")
    assert mod.encode_one(bad) == "failed"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tt9.jpg"]


@pytest.mark.skipif(shutil.which("avifenc") is None or shutil.which("magick") is None,
                    reason="avifenc/magick not installed")
def test_encode_all_writes_avif_and_is_resumable(tmp_path):
    subprocess.run(["magick", "-size", "34x51", "gradient:red-blue",
                    str(tmp_path / "tt1.jpg")], check=True)
    assert mod.encode_all(tmp_path, workers=2) == {"encoded": 1}
    avif = tmp_path / "tt1.avif"
    assert avif.read_bytes()[4:12] == b"ftypavif"
    assert mod.encode_all(tmp_path, workers=2) == {}


def test_is_webp_sniffs_magic_bytes(tmp_path):
    webp = tmp_path / "tt1.jpg"
    webp.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    jpeg = tmp_path / "tt2.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00")
    assert mod.is_webp(webp)
    assert not mod.is_webp(jpeg)


@pytest.mark.skipif(shutil.which("avifenc") is None or shutil.which("magick") is None,
                    reason="avifenc/magick not installed")
def test_encode_one_handles_webp_named_jpg(tmp_path):
    src = tmp_path / "tt1.jpg"
    subprocess.run(["magick", "-size", "34x51", "gradient:red-blue", f"webp:{src}"], check=True)
    assert mod.is_webp(src)
    assert mod.encode_one(src) == "encoded"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tt1.avif", "tt1.jpg"]
