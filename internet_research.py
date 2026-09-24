from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from research_core import best_passages, rank_candidates


HEADERS = {
    "User-Agent": "QueryBridge/1.0 (+local schema research assistant)",
    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
}
MAX_WEB_BYTES = 2_000_000


def _public_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        for info in socket.getaddrinfo(parsed.hostname, None):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
    except (OSError, ValueError):
        return False
    return True


def search_internet(query: str, max_results: int = 8) -> dict:
    query = " ".join(str(query or "").split()).strip()
    if not query:
        raise ValueError("internet_search requires a non-empty query.")

    rows = []
    seen = set()
    diagnostics = []
    for backend in ("duckduckgo", "mojeek", "startpage"):
        try:
            found = list(
                DDGS(timeout=12).text(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=max_results,
                    backend=backend,
                )
                or []
            )
            diagnostics.append(f"{backend}: {len(found)} result(s)")
            for row in found:
                url = str(row.get("href") or row.get("url") or "").strip()
                if not _public_url(url) or url in seen:
                    continue
                seen.add(url)
                rows.append(
                    {
                        "title": str(row.get("title") or url),
                        "url": url,
                        "snippet": str(row.get("body") or row.get("snippet") or ""),
                        "query": query,
                        "published_at": str(row.get("date") or row.get("published") or ""),
                        "search_backend": backend,
                    }
                )
            if rows:
                break
        except Exception as exc:
            diagnostics.append(f"{backend}: {type(exc).__name__}: {exc}")

    ranked = rank_candidates(
        rows,
        query,
        title=lambda item: item.get("title", ""),
        snippet=lambda item: item.get("snippet", ""),
        url=lambda item: item.get("url", ""),
        query=lambda item: item.get("query", ""),
    )
    return {
        "query": query,
        "results": ranked[:max_results],
        "diagnostics": diagnostics,
    }


def read_internet(url: str, focus: str = "") -> dict:
    url = str(url or "").strip()
    if not _public_url(url):
        raise ValueError("internet_read only allows public http/https URLs.")

    response = requests.get(url, headers=HEADERS, timeout=18, stream=True, allow_redirects=True)
    response.raise_for_status()
    if not _public_url(response.url):
        raise ValueError("internet_read redirect resolved to a non-public address.")

    content_type = str(response.headers.get("content-type") or "").lower()
    if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain", "")):
        raise ValueError(f"internet_read does not parse content type: {content_type or 'unknown'}")

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_WEB_BYTES:
            break
        chunks.append(chunk)
    raw = b"".join(chunks)

    encoding = response.encoding or response.apparent_encoding or "utf-8"
    text = raw.decode(encoding, errors="replace")
    title = response.url
    if "html" in content_type or "<html" in text[:1000].lower():
        soup = BeautifulSoup(text, "html.parser")
        if soup.title and soup.title.string:
            title = " ".join(soup.title.string.split())
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())

    target = " ".join(str(focus or "").split()).strip() or title
    passages = best_passages(text, target, limit=6, max_chars=9000)
    return {
        "title": title,
        "url": response.url,
        "content_type": content_type or "text/plain",
        "focus": target,
        "passages": passages,
        "text": "\n\n".join(passages) if passages else text[:9000],
        "truncated": size > MAX_WEB_BYTES,
    }
