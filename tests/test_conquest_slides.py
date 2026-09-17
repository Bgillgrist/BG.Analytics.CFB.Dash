"""Slide captions must describe the selected conquest ownership rules."""

import base64
import json
import re
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.conquest_slides import conquest_slide_controls
from utils import conquest_slides


def slide_config(scope, season=2026, checkpoint="Week 3"):
    markup = conquest_slide_controls(scope, season, checkpoint)
    return json.loads(re.search(r"const config = (.*);", markup).group(1))


@pytest.mark.parametrize(
    "scope,initial_teams,promotions",
    [
        ("Power 4 + Notre Dame", "Power 4 schools and Notre Dame", False),
        ("P4 + Promotions", "Power 4 schools and Notre Dame", True),
        ("G6 + UConn", "G6 schools and UConn", False),
        ("All Teams / Conferences", "All FBS schools", False),
    ],
)
def test_rules_match_ownership_scope(scope, initial_teams, promotions):
    config = slide_config(scope)
    assert config["rules"][0].startswith(initial_teams)
    assert len(config["rules"]) == 4
    assert ("even outside the Power 4" in config["rules"][2]) is promotions
    if not promotions:
        assert "Only games between schools in the selected map scope" in config["rules"][2]


@pytest.mark.parametrize(
    "checkpoint,heading",
    [("Week 4", "Week 4"), ("Postseason Week 1", "Postseason Week 1"),
     ("Before Season", "Preseason"), ("After Season", "Final Map")],
)
def test_selected_season_and_checkpoint_drive_header(checkpoint, heading):
    config = slide_config("P4 + Promotions", 2027, checkpoint)
    assert config["season"] == "2027"
    assert config["week"] == heading
    assert "source" not in config


def test_heading_cannot_insert_html_or_terminate_script():
    label = '</script><img src=x onerror="alert(1)"> & __CONQUEST_SLIDE_CONFIG__'
    markup = conquest_slide_controls("P4 + Promotions", 2026, label)
    assert label not in markup
    assert slide_config("P4 + Promotions", checkpoint=label)["week"] == label


@pytest.fixture
def logo_cache():
    conquest_slides._logo_data_url.cache_clear()
    yield
    conquest_slides._logo_data_url.cache_clear()


def logo_bytes(format="PNG"):
    output = BytesIO()
    Image.new("RGBA", (500, 500), (20, 80, 180, 128)).save(output, format=format)
    return output.getvalue()


def test_server_embeds_original_png_and_caches_success(monkeypatch, logo_cache):
    original = logo_bytes()
    requests = []

    def fetch(request, timeout):
        requests.append(request.full_url)
        assert timeout == 8
        return BytesIO(original)

    monkeypatch.setattr(conquest_slides, "urlopen", fetch)
    url = "https://a.espncdn.com/i/teamlogos/ncaa/500/264.png"
    data = conquest_slides._logo_data_url(url)
    assert data.startswith("data:image/png;base64,")
    assert base64.b64decode(data.split(",", 1)[1]) == original
    assert conquest_slides._logo_data_url(url) == data
    assert requests == [url]


def test_bad_response_is_not_cached_and_can_retry(monkeypatch, logo_cache):
    payloads = iter([b"<html>temporarily unavailable</html>", logo_bytes()])
    monkeypatch.setattr(conquest_slides, "urlopen", lambda *args, **kwargs: BytesIO(next(payloads)))
    url = "https://example.com/logo.png"
    with pytest.raises(OSError):
        conquest_slides._logo_data_url(url)
    assert conquest_slides._logo_data_url(url).startswith("data:image/png;base64,")


def test_other_raster_formats_keep_resolution_and_transparency(monkeypatch, logo_cache):
    monkeypatch.setattr(conquest_slides, "urlopen", lambda *args, **kwargs: BytesIO(logo_bytes("WEBP")))
    data = conquest_slides._logo_data_url("https://example.com/logo.webp")
    with Image.open(BytesIO(base64.b64decode(data.split(",", 1)[1]))) as image:
        assert image.format == "PNG"
        assert image.size == (500, 500)
        assert image.getpixel((0, 0))[3] == 128


def test_dark_logo_failure_uses_regular_logo_once_for_shared_owner(monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        if url == "https://example.com/dark.png":
            raise OSError("404")
        return "data:image/png;base64,regular"

    monkeypatch.setattr(conquest_slides, "_logo_data_url", fetch)
    seeds = [dict(logo="https://example.com/dark.png", logoFallback="https://example.com/regular.png") for _ in range(4)]
    conquest_slides.embed_conquest_logos(seeds)
    assert calls == ["https://example.com/dark.png", "https://example.com/regular.png"]
    assert all(seed["logo"] == "data:image/png;base64,regular" for seed in seeds)


def test_failed_server_download_preserves_live_map_url(monkeypatch):
    def fail(url):
        raise OSError("timeout")

    monkeypatch.setattr(conquest_slides, "_logo_data_url", fail)
    seeds = [dict(logo="https://example.com/logo.png")]
    conquest_slides.embed_conquest_logos(seeds)
    assert seeds[0]["logo"] == "https://example.com/logo.png"


def test_embedded_and_missing_logos_do_not_trigger_requests(monkeypatch):
    def unexpected_request(url):
        pytest.fail("This logo does not need a network request")

    monkeypatch.setattr(conquest_slides, "_logo_data_url", unexpected_request)
    seeds = [dict(logo=""), dict(logo="data:image/png;base64,existing")]
    conquest_slides.embed_conquest_logos(seeds)
    assert seeds == [dict(logo=""), dict(logo="data:image/png;base64,existing")]
