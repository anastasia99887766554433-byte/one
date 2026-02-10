from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).parent
RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
DEFAULT_QUERY = "AI OR artificial intelligence when:1d"
MAX_ITEMS = 10

STOP_WORDS = {
    "ai",
    "artificial",
    "intelligence",
    "the",
    "a",
    "an",
    "and",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "is",
    "are",
    "at",
    "from",
    "by",
    "as",
    "new",
    "says",
}


def fetch_ai_news(limit: int = MAX_ITEMS) -> list[dict[str, Any]]:
    query = quote_plus(DEFAULT_QUERY)
    with urlopen(RSS_URL.format(query=query), timeout=12) as response:
        raw_xml = response.read()

    root = ET.fromstring(raw_xml)
    channel = root.find("channel")
    if channel is None:
        return []

    items: list[dict[str, Any]] = []
    for item in channel.findall("item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "Unknown source").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()

        published_at = pub_date_raw
        try:
            dt = parsedate_to_datetime(pub_date_raw).astimezone(timezone.utc)
            published_at = dt.isoformat().replace("+00:00", "Z")
        except Exception:
            pass

        items.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": published_at,
            }
        )

    return items


def build_daily_summary(news_items: list[dict[str, Any]]) -> str:
    if not news_items:
        return "За последние сутки заметных AI-новостей не найдено."

    titles = " ".join(item["title"] for item in news_items)
    words = re.findall(r"[A-Za-z][A-Za-z\-']+", titles.lower())
    frequent = [w for w, _ in Counter(words).most_common(6) if w not in STOP_WORDS][:4]

    topics = ", ".join(frequent) if frequent else "модели, продукты и внедрение AI"
    count = len(news_items)
    return (
        f"За последние 24 часа в AI было много активности: собрано {count} ключевых новостей. "
        f"Чаще всего встречаются темы: {topics}. "
        "Откройте карточки ниже, чтобы быстро перейти к первоисточникам."
    )


def fallback_news() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return [
        {
            "title": "Open-source AI models continue improving multimodal reasoning",
            "url": "https://news.google.com/",
            "source": "Fallback digest",
            "published_at": now,
        },
        {
            "title": "Enterprise adoption of AI copilots expands across industries",
            "url": "https://news.google.com/",
            "source": "Fallback digest",
            "published_at": now,
        },
        {
            "title": "Governments discuss new frameworks for safe AI deployment",
            "url": "https://news.google.com/",
            "source": "Fallback digest",
            "published_at": now,
        },
    ]


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_file(self, path: Path, content_type: str) -> None:
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path

        if route == "/":
            return self._serve_file(ROOT / "templates" / "index.html", "text/html; charset=utf-8")
        if route == "/static/styles.css":
            return self._serve_file(ROOT / "static" / "styles.css", "text/css; charset=utf-8")
        if route == "/api/news":
            try:
                items = fetch_ai_news()
                return self._send_json(
                    {
                        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "summary": build_daily_summary(items),
                        "items": items,
                    }
                )
            except Exception:
                items = fallback_news()
                return self._send_json(
                    {
                        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "summary": "Онлайн-источник новостей временно недоступен, показан резервный дайджест.",
                        "items": items,
                    }
                )

        self.send_error(404, "Not found")


def run() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    print("Server started at http://localhost:8000")
    server.serve_forever()


if __name__ == "__main__":
    run()
