"""Static contract checks complement actual browser testing, not replace it."""
from html.parser import HTMLParser
from pathlib import Path


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag in ("script", "link"):
            value = attrs.get("src") or attrs.get("href", "")
            if value.startswith("/static/"):
                self.assets.append(value)


def test_frontend_has_unique_targets_and_local_assets():
    root = Path(__file__).resolve().parents[1] / "twins" / "static"
    document = Document()
    document.feed((root / "index.html").read_text(encoding="utf-8"))
    assert len(document.ids) == len(set(document.ids))
    assert document.assets
    for asset in document.assets:
        assert (root / asset.removeprefix("/static/")).is_file(), f"Missing frontend asset: {asset}"
    for control in ("play-button", "step-button", "reset-button", "plasticity-toggle", "shuffle-toggle", "neuron-form", "replay-tick"):
        assert control in document.ids
