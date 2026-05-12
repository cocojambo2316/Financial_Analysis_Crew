from __future__ import annotations

from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from crewai.tools import tool


@tool
def search_news(query: str) -> str:
    """Search recent news headlines for a company or ticker using Google News RSS."""
    try:
        rss_url = (
            "https://news.google.com/rss/search?q="
            f"{quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        request = Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        with urlopen(request, timeout=15) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return f"No news feed available for query: {query}"

        items = []
        for item in channel.findall("item")[:5]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = item.find("source")
            source_text = (source.text or "").strip() if source is not None else "Unknown source"
            pub_date = (item.findtext("pubDate") or "").strip()
            items.append(
                f"- {title}\n  Source: {source_text}\n  Published: {pub_date}\n  Link: {link}"
            )

        if not items:
            return f"No recent news found for query: {query}"

        return f"Top news results for '{query}':\n" + "\n\n".join(items)

    except Exception as exc:
        return f"❌ News search error for '{query}': {exc}"