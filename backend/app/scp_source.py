"""Fetch a real SCP article's text + attribution (Milestone 4 auto-generate).

Uses the Crom API (https://api.crom.avn.sh/graphql), which indexes the SCP wiki
and exposes each page's wikidot source and its attributions (author, rewrite,
translator…). That gives us both the raw story to retell AND the credit chain
the CC BY-SA license requires — in one reliable JSON call. If Crom can't serve
it, we fall back to scraping the rendered wiki page.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

import requests

_CROM = "https://api.crom.avn.sh/graphql"
_UA = "scp-shorts-studio/0.1 (local tool)"
_BRANCH = "http://scp-wiki.wikidot.com"
_TIMEOUT = 30
_DEFAULT_LICENSE = "CC BY-SA 3.0"


class SCPSourceError(RuntimeError):
    """Raised (user-facing) when an SCP article can't be fetched."""


@dataclass
class SCPSource:
    title: str
    text: str
    authors: str
    source_url: str
    license: str = _DEFAULT_LICENSE


def normalize(ref: str) -> tuple[str, str]:
    """Return (crom_url, slug) for an SCP number, slug, or full URL."""
    ref = (ref or "").strip()
    if not ref:
        raise SCPSourceError("No SCP number or URL was given.")
    if "://" in ref or "wikidot.com" in ref or ref.startswith("www."):
        url = ref if "://" in ref else f"http://{ref}"
        slug = url.rstrip("/").rsplit("/", 1)[-1].lower()
        # Crom keys pages by the http scheme on the branch host.
        return url.replace("https://", "http://"), slug
    slug = ref.lower().replace(" ", "-")
    if re.fullmatch(r"\d+", slug):          # bare number -> scp-NNN
        slug = f"scp-{slug}"
    return f"{_BRANCH}/{slug}", slug


def _clean_wikidot(src: str) -> str:
    """Strip wikidot markup noise down to readable prose for the LLM."""
    s = src
    # Drop whole modules (rating widget, etc.) and includes.
    s = re.sub(r"\[\[module.*?\]\].*?\[\[/module\]\]", "", s, flags=re.S | re.I)
    s = re.sub(r"\[\[include[^\]]*\]\]", "", s, flags=re.I)
    # Drop image / file / size / span / table structural tags.
    s = re.sub(r"\[\[/?(?:div|span|size|table|row|cell|hcell|tabview|tab|"
               r"collapsible|>|<|=|==).*?\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[/?(?:image|file|footnoteblock|module)[^\]]*\]\]", "", s, flags=re.I)
    # Keep footnote text, drop the tags.
    s = re.sub(r"\[\[/?footnote\]\]", " ", s, flags=re.I)
    # Links: [[[page|label]]] -> label ; [[[page]]] -> page
    s = re.sub(r"\[\[\[[^\|\]]*\|([^\]]+)\]\]\]", r"\1", s)
    s = re.sub(r"\[\[\[([^\]]+)\]\]\]", r"\1", s)
    # Inline emphasis markers that add noise when read aloud.
    s = re.sub(r"//|__|\^\^|,,", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return html.unescape(s).strip()


def _from_crom(crom_url: str) -> SCPSource | None:
    query = (
        "{ page(url: %s) { url wikidotInfo { title source } "
        "attributions { user { name } type } } }" % _json_str(crom_url)
    )
    try:
        resp = requests.post(
            _CROM, json={"query": query}, headers={"User-Agent": _UA},
            timeout=_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    page = (resp.json().get("data") or {}).get("page")
    if not page:
        return None
    wi = page.get("wikidotInfo") or {}
    source = wi.get("source") or ""
    if not source.strip():
        return None

    # Prefer AUTHOR/REWRITE/TRANSLATOR credits; fall back to any attribution.
    attribs = page.get("attributions") or []
    preferred = ("AUTHOR", "REWRITE", "TRANSLATOR")
    names: list[str] = []
    for want_type in (preferred, None):
        if names:
            break
        for a in attribs:
            if want_type and (a.get("type") or "").upper() not in want_type:
                continue
            name = ((a.get("user") or {}).get("name") or "").strip()
            if name and name.lower() != "(user deleted)" and name not in names:
                names.append(name)
    return SCPSource(
        title=(wi.get("title") or "").strip(),
        text=_clean_wikidot(source),
        authors=", ".join(names),
        source_url=page.get("url") or crom_url,
        license=_DEFAULT_LICENSE,
    )


def _from_html(url: str) -> SCPSource | None:
    """Fallback: scrape the rendered wiki page's #page-content."""
    page_url = url.replace("http://", "https://")
    try:
        resp = requests.get(page_url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    body = resp.text
    m = re.search(r'<div id="page-content">(.*?)<div id="footer"', body, re.S)
    content = m.group(1) if m else body
    tm = re.search(r'<div id="page-title">(.*?)</div>', body, re.S)
    title = _strip_html(tm.group(1)) if tm else ""
    text = _strip_html(content)
    if len(text) < 200:  # looks empty / blocked
        return None
    return SCPSource(title=title, text=text, authors="", source_url=page_url)


def _strip_html(fragment: str) -> str:
    frag = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", fragment, flags=re.S | re.I)
    frag = re.sub(r"<[^>]+>", " ", frag)
    frag = html.unescape(frag)
    return re.sub(r"[ \t]*\n\s*\n\s*", "\n\n", re.sub(r"[ \t]+", " ", frag)).strip()


def _json_str(s: str) -> str:
    import json
    return json.dumps(s)


def fetch(ref: str) -> SCPSource:
    """Fetch an SCP article by number, slug, or URL. Raises SCPSourceError."""
    crom_url, slug = normalize(ref)
    result = _from_crom(crom_url) or _from_html(crom_url)
    if not result or not result.text.strip():
        raise SCPSourceError(
            f"Couldn't fetch “{slug}” from the SCP wiki. Check the number/URL, "
            "or paste the story text manually and use Generate episodes instead."
        )
    if not result.title:
        result.title = slug.upper()
    return result
