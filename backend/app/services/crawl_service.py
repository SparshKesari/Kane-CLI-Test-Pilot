from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx


class _Extract(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__()
        self.base = base
        self.title = ""
        self.links: list[dict] = []
        self.forms: list[dict] = []
        self.buttons: list[str] = []
        self.headings: list[str] = []
        self._cur_form: dict | None = None
        self._capture = ""           # "title" | "a" | "button" | "h"
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._capture, self._buf = "title", ""
        elif tag == "a" and a.get("href"):
            self._capture, self._buf = "a", ""
            self._href = urljoin(self.base, a["href"])
        elif tag == "form":
            self._cur_form = {"action": urljoin(self.base, a.get("action", "")),
                              "method": (a.get("method") or "get").lower(), "inputs": []}
        elif tag in ("input", "select", "textarea") and self._cur_form is not None:
            nm = a.get("name") or a.get("id") or a.get("type") or tag
            self._cur_form["inputs"].append(nm)
        elif tag == "button":
            self._capture, self._buf = "button", ""
        elif tag in ("h1", "h2", "h3"):
            self._capture, self._buf = "h", ""

    def handle_data(self, data):
        if self._capture:
            self._buf += data

    def handle_endtag(self, tag):
        txt = " ".join(self._buf.split())[:80]
        if tag == "title" and self._capture == "title":
            self.title = txt
        elif tag == "a" and self._capture == "a":
            if txt:
                self.links.append({"text": txt, "href": self._href})
        elif tag == "button" and self._capture == "button":
            if txt:
                self.buttons.append(txt)
        elif tag in ("h1", "h2", "h3") and self._capture == "h":
            if txt:
                self.headings.append(txt)
        elif tag == "form" and self._cur_form is not None:
            self.forms.append(self._cur_form)
            self._cur_form = None
        self._capture = ""


def crawl(target_url: str) -> dict:
    """Understand the live app structurally. Prefer a Playwright-rendered crawl
    (sees client-rendered SPA content); fall back to a static HTTP crawl."""
    rendered = _crawl_rendered(target_url)
    if rendered and not rendered.get("error"):
        return rendered
    static = _crawl_static(target_url)
    static.setdefault("rendered", False)
    return static


def _crawl_rendered(target_url: str, timeout_ms: int = 25000) -> dict:
    """Headless-render the page and extract the real DOM. Runs in a worker
    thread (no asyncio loop), so sync Playwright is safe here."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return {"error": "playwright-missing"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(target_url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(800)
            title = page.title()
            links = page.eval_on_selector_all(
                "a", "els=>els.map(e=>({text:(e.innerText||'').trim().slice(0,80),"
                "href:e.href,target:e.target})).filter(l=>l.text)")
            buttons = page.eval_on_selector_all(
                "button,[role='button']",
                "els=>els.map(e=>(e.innerText||'').trim().slice(0,60)).filter(Boolean)")
            inputs = page.eval_on_selector_all(
                "input,textarea,select",
                "els=>els.map(e=>e.name||e.placeholder||e.id||e.type).filter(Boolean)")
            headings = page.eval_on_selector_all(
                "h1,h2,h3", "els=>els.map(e=>(e.innerText||'').trim().slice(0,80)).filter(Boolean)")
            body = (page.inner_text("body") or "")[:2500]
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    seen, ulinks = set(), []
    for l in links:
        k = l["text"].lower()
        if k and k not in seen:
            seen.add(k); ulinks.append(l)
    return {
        "rendered": True, "title": title, "links": ulinks[:30],
        "buttons": list(dict.fromkeys(buttons))[:25],
        "inputs": list(dict.fromkeys(inputs))[:20],
        "headings": list(dict.fromkeys(headings))[:20],
        "visible_text": " ".join(body.split()),
        "forms": [],
    }


def _crawl_static(target_url: str, timeout: float = 15.0) -> dict:
    """Static HTTP fallback (no JS). Misses client-rendered SPA content."""
    try:
        r = httpx.get(target_url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "AgenticTestFactory/0.1"})
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "links": [], "forms": [], "buttons": [], "headings": []}
    p = _Extract(str(r.url))
    p.feed(r.text)
    # de-dup links by text, keep first 25
    seen, links = set(), []
    for l in p.links:
        key = l["text"].lower()
        if key and key not in seen:
            seen.add(key); links.append(l)
    return {
        "title": p.title,
        "links": links[:25],
        "forms": p.forms[:10],
        "buttons": list(dict.fromkeys(p.buttons))[:20],
        "headings": list(dict.fromkeys(p.headings))[:15],
    }
