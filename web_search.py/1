"""
Maya AI - Complete Internet + Research Engine

Features in one file:
- Web search
- News search
- URL/page reader
- Deep research
- Multi-query search
- Official-source priority
- Claim verification helper
- Weather
- Currency conversion
- Country information
- Time/timezone
- Live sports adapter with optional API
- Cache, retries, URL safety, deduplication
- Central execute_web_action() router

Install:
    pip install ddgs requests beautifulsoup4 python-dotenv
Optional:
    pip install trafilatura

Optional .env for a dedicated sports provider:
    SPORTS_API_URL=
    SPORTS_API_KEY=
    SPORTS_API_HEADER=x-api-key
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time
from collections import OrderedDict
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote, urlparse, urlunparse
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

try:
    from ddgs import DDGS
except Exception:
    DDGS = None

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    import trafilatura
except Exception:
    trafilatura = None


DEFAULT_MAX_RESULTS = 8
MAX_RESULTS_LIMIT = 20
REQUEST_TIMEOUT = 12
MAX_PAGE_BYTES = 3_000_000
MAX_PAGE_CHARS = 18_000
CACHE_TTL_SECONDS = 300
CACHE_MAX_ITEMS = 150

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36 MayaAI/1.0"
)

SPORTS_API_URL = os.getenv("SPORTS_API_URL", "").strip()
SPORTS_API_KEY = os.getenv("SPORTS_API_KEY", "").strip()
SPORTS_API_HEADER = os.getenv("SPORTS_API_HEADER", "x-api-key").strip() or "x-api-key"

OFFICIAL_DOMAIN_HINTS = {
    "openai": ["openai.com"],
    "google": ["google.com", "developers.google.com"],
    "gemini": ["ai.google.dev", "google.com"],
    "microsoft": ["microsoft.com", "learn.microsoft.com"],
    "windows": ["microsoft.com", "learn.microsoft.com"],
    "github": ["github.com", "docs.github.com"],
    "python": ["python.org", "docs.python.org"],
    "flutter": ["flutter.dev", "docs.flutter.dev"],
    "android": ["developer.android.com"],
}

WEATHER_CODE_TEXT = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
}

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "169.254.169.254",
}

_cache: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
_cache_lock = threading.RLock()
_search_lock = threading.RLock()


def _clean_text(value: Any) -> str:
    value = unescape(str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        value = int(value)
    except Exception:
        value = default
    return max(low, min(high, value))


def _normalize_domain(domain: str) -> str:
    domain = re.sub(r"^https?://", "", (domain or "").strip().lower()).split("/")[0]
    return domain[4:] if domain.startswith("www.") else domain


def _host_matches(host: str, domain: str) -> bool:
    host = (host or "").lower()
    host = host[4:] if host.startswith("www.") else host
    domain = _normalize_domain(domain)
    return host == domain or host.endswith("." + domain)


def _normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return (url or "").strip()
    return urlunparse(parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
    ))


def _cache_key(prefix: str, payload: Any) -> str:
    raw = json.dumps(
        {"prefix": prefix, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_get(key: str):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        created, value = item
        if time.time() - created > CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return value


def _cache_set(key: str, value: Any):
    with _cache_lock:
        _cache[key] = (time.time(), value)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ITEMS:
            _cache.popitem(last=False)


def clear_web_cache():
    with _cache_lock:
        count = len(_cache)
        _cache.clear()
    return {"success": True, "cleared_items": count}


def _request_json(method: str, url: str, *, params=None, headers=None, timeout=REQUEST_TIMEOUT, retries=2):
    if requests is None:
        return {"success": False, "error": "requests is not installed"}

    delay = 0.8
    last_error = None

    for attempt in range(retries + 1):
        try:
            response = requests.request(
                method.upper(),
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"Temporary HTTP error {response.status_code}")

            response.raise_for_status()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json(),
            }

        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(delay)
                delay *= 2

    return {"success": False, "error": str(last_error)}


def _is_public_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
        return not (
            ip.is_private or ip.is_loopback or ip.is_link_local or
            ip.is_multicast or ip.is_reserved or ip.is_unspecified
        )
    except Exception:
        return False


def _is_safe_public_url(url: str):
    try:
        parsed = urlparse(url)

        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            return False, "Only http/https URLs are allowed."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL hostname is missing."

        if hostname.lower() in BLOCKED_HOSTNAMES:
            return False, "Local/private hostname is blocked."

        try:
            direct_ip = ipaddress.ip_address(hostname)
            return (
                (True, "")
                if _is_public_ip(str(direct_ip))
                else (False, "Private/local IP address is blocked.")
            )
        except ValueError:
            pass

        infos = socket.getaddrinfo(
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )

        for info in infos:
            if not _is_public_ip(info[4][0]):
                return False, "URL resolves to a private/local network address."

        return True, ""

    except Exception as error:
        return False, f"Invalid URL: {error}"


def _deduplicate(results):
    seen_urls = set()
    seen_titles = set()
    output = []

    for item in results:
        url = _normalize_url(item.get("url", ""))
        title = _clean_text(item.get("title", "")).lower()

        if not url or url in seen_urls or (title and title in seen_titles):
            continue

        seen_urls.add(url)
        if title:
            seen_titles.add(title)

        clean = dict(item)
        clean["url"] = url
        output.append(clean)

    return output


def _filter_domains(results, include_domains=None, exclude_domains=None):
    include_domains = include_domains or []
    exclude_domains = exclude_domains or []
    output = []

    for item in results:
        host = urlparse(item.get("url", "")).hostname or ""

        if include_domains and not any(_host_matches(host, d) for d in include_domains):
            continue

        if exclude_domains and any(_host_matches(host, d) for d in exclude_domains):
            continue

        output.append(item)

    return output


def _official_domains(query: str):
    q = query.lower()
    domains = []

    for keyword, values in OFFICIAL_DOMAIN_HINTS.items():
        if keyword in q:
            domains.extend(values)

    return list(dict.fromkeys(domains))


def _rank_results(query: str, results: list[dict[str, Any]], official_domains=None):
    official_domains = official_domains or []
    q_tokens = set(re.findall(r"\w+", query.lower()))
    ranked = []

    for index, item in enumerate(results):
        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        t_tokens = set(re.findall(r"\w+", text))
        overlap = len(q_tokens & t_tokens) / max(1, len(q_tokens))
        host = urlparse(item.get("url", "")).hostname or ""
        official_bonus = 0.35 if any(_host_matches(host, d) for d in official_domains) else 0
        position_bonus = max(0.0, 0.12 - index * 0.01)

        clean = dict(item)
        clean["score"] = round(overlap + official_bonus + position_bonus, 4)
        ranked.append(clean)

    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    return ranked


def search_web(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: str | None = None,
    include_domains=None,
    exclude_domains=None,
    prefer_official: bool = True,
    use_cache: bool = True,
):
    query = _clean_text(query)

    if not query:
        return {"success": False, "error": "Search query is empty.", "results": []}

    if DDGS is None:
        return {"success": False, "error": "ddgs is not installed. Run: pip install ddgs"}

    max_results = _clamp_int(max_results, 1, MAX_RESULTS_LIMIT, DEFAULT_MAX_RESULTS)
    key = _cache_key("search_web", {
        "q": query,
        "n": max_results,
        "region": region,
        "safe": safesearch,
        "time": timelimit,
        "in": include_domains or [],
        "out": exclude_domains or [],
        "official": prefer_official,
    })

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return {**cached, "cached": True}

    try:
        raw = []

        with _search_lock:
            ddgs = DDGS()
            kwargs = {
                "query": query,
                "region": region,
                "safesearch": safesearch,
                "max_results": min(max_results * 3, 50),
            }

            if timelimit:
                kwargs["timelimit"] = timelimit

            for item in ddgs.text(**kwargs) or []:
                raw.append({
                    "title": _clean_text(item.get("title", "")),
                    "url": _clean_text(item.get("href") or item.get("url") or ""),
                    "snippet": _clean_text(item.get("body") or item.get("snippet") or ""),
                    "source": _clean_text(item.get("source") or ""),
                })

        raw = _deduplicate(raw)
        raw = _filter_domains(raw, include_domains, exclude_domains)
        official = _official_domains(query) if prefer_official else []
        raw = _rank_results(query, raw, official)[:max_results]

        result = {
            "success": True,
            "query": query,
            "count": len(raw),
            "official_domains": official,
            "results": raw,
            "cached": False,
        }

        if use_cache:
            _cache_set(key, result)

        return result

    except Exception as error:
        return {"success": False, "error": str(error), "query": query, "results": []}


def search_news(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: str | None = "m",
    include_domains=None,
    exclude_domains=None,
    use_cache: bool = True,
):
    query = _clean_text(query)

    if not query:
        return {"success": False, "error": "News query is empty.", "results": []}

    if DDGS is None:
        return {"success": False, "error": "ddgs is not installed. Run: pip install ddgs"}

    max_results = _clamp_int(max_results, 1, MAX_RESULTS_LIMIT, DEFAULT_MAX_RESULTS)
    key = _cache_key("search_news", {
        "q": query,
        "n": max_results,
        "region": region,
        "safe": safesearch,
        "time": timelimit,
    })

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return {**cached, "cached": True}

    try:
        raw = []

        with _search_lock:
            ddgs = DDGS()
            kwargs = {
                "query": query,
                "region": region,
                "safesearch": safesearch,
                "max_results": min(max_results * 3, 50),
            }

            if timelimit:
                kwargs["timelimit"] = timelimit

            for item in ddgs.news(**kwargs) or []:
                raw.append({
                    "title": _clean_text(item.get("title", "")),
                    "url": _clean_text(item.get("url") or item.get("href") or ""),
                    "snippet": _clean_text(item.get("body") or item.get("snippet") or ""),
                    "source": _clean_text(item.get("source") or ""),
                    "published": _clean_text(item.get("date") or item.get("published") or ""),
                })

        raw = _deduplicate(raw)
        raw = _filter_domains(raw, include_domains, exclude_domains)
        raw = _rank_results(query, raw)[:max_results]

        result = {
            "success": True,
            "query": query,
            "count": len(raw),
            "results": raw,
            "cached": False,
        }

        if use_cache:
            _cache_set(key, result)

        return result

    except Exception as error:
        return {"success": False, "error": str(error), "query": query, "results": []}


def _extract_html_text(html: str, url: str = ""):
    title = ""
    text = ""

    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                html,
                url=url or None,
                include_links=False,
                include_images=False,
                include_tables=False,
                favor_precision=True,
            )
            if extracted:
                text = _clean_text(extracted)
        except Exception:
            pass

    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")

            if soup.title and soup.title.string:
                title = _clean_text(soup.title.string)

            for tag in soup(["script", "style", "noscript", "svg", "canvas", "template"]):
                tag.decompose()

            if not text:
                text = _clean_text(soup.get_text(" ", strip=True))
        except Exception:
            pass

    if not text:
        stripped = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
        stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
        text = _clean_text(stripped)

    return title, text[:MAX_PAGE_CHARS]


def read_url(url: str, timeout: int = REQUEST_TIMEOUT, max_chars: int = MAX_PAGE_CHARS, use_cache=True):
    if requests is None:
        return {"success": False, "error": "requests is not installed"}

    url = _normalize_url(url)
    safe, reason = _is_safe_public_url(url)

    if not safe:
        return {"success": False, "error": reason, "url": url}

    timeout = _clamp_int(timeout, 3, 30, REQUEST_TIMEOUT)
    max_chars = _clamp_int(max_chars, 500, MAX_PAGE_CHARS, MAX_PAGE_CHARS)
    key = _cache_key("read_url", {"url": url, "max_chars": max_chars})

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return {**cached, "cached": True}

    try:
        with requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()

            final_url = _normalize_url(response.url)
            safe_final, reason = _is_safe_public_url(final_url)
            if not safe_final:
                return {"success": False, "error": f"Redirected URL blocked: {reason}"}

            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()

            if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                return {"success": False, "error": f"Unsupported content type: {content_type}"}

            chunks = []
            total = 0

            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue

                total += len(chunk)
                if total > MAX_PAGE_BYTES:
                    break

                chunks.append(chunk)

            raw = b"".join(chunks)
            encoding = response.encoding or response.apparent_encoding or "utf-8"
            html = raw.decode(encoding, errors="replace")

            if content_type == "text/plain":
                title = ""
                text = _clean_text(html)[:max_chars]
            else:
                title, text = _extract_html_text(html, final_url)
                text = text[:max_chars]

            result = {
                "success": True,
                "url": final_url,
                "title": title,
                "content_type": content_type or "unknown",
                "text": text,
                "chars": len(text),
                "truncated": len(text) >= max_chars,
                "cached": False,
            }

            if use_cache:
                _cache_set(key, result)

            return result

    except Exception as error:
        return {"success": False, "error": str(error), "url": url}


def search_and_read(query: str, max_results=5, read_top=3, news=False, timelimit=None):
    search = (
        search_news(query, max_results=max_results, timelimit=timelimit or "m")
        if news
        else search_web(query, max_results=max_results, timelimit=timelimit)
    )

    if not search.get("success"):
        return search

    output = []

    for index, item in enumerate(search.get("results", [])):
        current = dict(item)

        if index < read_top:
            page = read_url(item.get("url", ""), max_chars=7000)
            if page.get("success"):
                current["page_text"] = page.get("text", "")
            else:
                current["page_error"] = page.get("error", "")

        output.append(current)

    return {
        "success": True,
        "mode": "news_research" if news else "deep_research",
        "query": query,
        "count": len(output),
        "results": output,
    }


def multi_query_search(queries: list[str], max_results_per_query=5):
    combined = []
    reports = []

    for query in (queries or [])[:8]:
        result = search_web(query, max_results=max_results_per_query)

        reports.append({
            "query": query,
            "success": result.get("success", False),
            "count": result.get("count", 0),
            "error": result.get("error"),
        })

        if result.get("success"):
            for item in result.get("results", []):
                clean = dict(item)
                clean["matched_query"] = query
                combined.append(clean)

    return {
        "success": True,
        "queries": (queries or [])[:8],
        "reports": reports,
        "count": len(_deduplicate(combined)),
        "results": _deduplicate(combined),
    }


def verify_claim(claim: str, read_top=4):
    claim = _clean_text(claim)

    if not claim:
        return {"success": False, "error": "Claim is empty."}

    research = multi_query_search([
        claim,
        f'"{claim}"',
        f"{claim} official source",
    ])

    evidence = []

    for item in research.get("results", [])[:read_top]:
        page = read_url(item.get("url", ""), max_chars=6000)

        evidence.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "source": item.get("source", ""),
            "page_text": page.get("text", "") if page.get("success") else "",
            "page_error": None if page.get("success") else page.get("error"),
        })

    return {
        "success": True,
        "mode": "verify_claim",
        "claim": claim,
        "evidence_count": len(evidence),
        "evidence": evidence,
    }


def geocode_place(place: str, count=5, language="en"):
    place = _clean_text(place)

    if not place:
        return {"success": False, "error": "Place name is empty.", "results": []}

    response = _request_json(
        "GET",
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": place,
            "count": _clamp_int(count, 1, 10, 5),
            "language": language,
            "format": "json",
        },
    )

    if not response.get("success"):
        return response

    output = []

    for item in (response.get("data") or {}).get("results") or []:
        output.append({
            "name": item.get("name"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "country": item.get("country"),
            "country_code": item.get("country_code"),
            "admin1": item.get("admin1"),
            "timezone": item.get("timezone"),
        })

    return {
        "success": True,
        "query": place,
        "count": len(output),
        "results": output,
    }


def get_weather(place: str, forecast_days=3):
    geo = geocode_place(place, count=1)

    if not geo.get("success") or not geo.get("results"):
        return {"success": False, "error": "Location not found.", "place": place}

    loc = geo["results"][0]

    response = _request_json(
        "GET",
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,sunrise,sunset"
            ),
            "timezone": "auto",
            "forecast_days": _clamp_int(forecast_days, 1, 7, 3),
        },
    )

    if not response.get("success"):
        return response

    data = response.get("data") or {}
    current = data.get("current") or {}
    code = current.get("weather_code")

    if code is not None:
        current["condition"] = WEATHER_CODE_TEXT.get(int(code), "Unknown")

    return {
        "success": True,
        "place": {
            "name": loc.get("name"),
            "country": loc.get("country"),
            "admin1": loc.get("admin1"),
            "timezone": data.get("timezone") or loc.get("timezone"),
        },
        "current": current,
        "daily": data.get("daily") or {},
        "provider": "Open-Meteo",
    }


def get_exchange_rate(base: str, quote_currency: str):
    base = _clean_text(base).upper()
    quote_currency = _clean_text(quote_currency).upper()

    if base == quote_currency:
        return {
            "success": True,
            "base": base,
            "quote": quote_currency,
            "rate": 1.0,
            "provider": "Identity",
        }

    response = _request_json(
        "GET",
        "https://api.frankfurter.app/latest",
        params={"from": base, "to": quote_currency},
    )

    if not response.get("success"):
        return response

    data = response.get("data") or {}
    rate = (data.get("rates") or {}).get(quote_currency)

    if rate is None:
        return {"success": False, "error": f"Rate unavailable for {base}->{quote_currency}"}

    return {
        "success": True,
        "base": base,
        "quote": quote_currency,
        "rate": rate,
        "date": data.get("date"),
        "provider": "Frankfurter / ECB",
    }


def convert_currency(amount: float, base: str, quote_currency: str):
    try:
        amount = float(amount)
    except Exception:
        return {"success": False, "error": "Amount must be numeric."}

    rate = get_exchange_rate(base, quote_currency)

    if not rate.get("success"):
        return rate

    return {
        "success": True,
        "amount": amount,
        "base": rate["base"],
        "quote": rate["quote"],
        "rate": rate["rate"],
        "converted": round(amount * float(rate["rate"]), 6),
        "date": rate.get("date"),
        "provider": rate.get("provider"),
    }


def get_country_info(country: str, full_text=False):
    country = _clean_text(country)

    if not country:
        return {"success": False, "error": "Country name is empty."}

    response = _request_json(
        "GET",
        "https://restcountries.com/v3.1/name/" + quote(country),
        params={"fullText": "true" if full_text else "false"},
    )

    if not response.get("success"):
        return response

    output = []

    for item in (response.get("data") or [])[:10]:
        name = item.get("name") or {}
        output.append({
            "name": name.get("common"),
            "official_name": name.get("official"),
            "capital": item.get("capital") or [],
            "region": item.get("region"),
            "subregion": item.get("subregion"),
            "population": item.get("population"),
            "area_km2": item.get("area"),
            "languages": item.get("languages") or {},
            "currencies": item.get("currencies") or {},
            "timezones": item.get("timezones") or [],
            "continents": item.get("continents") or [],
            "borders": item.get("borders") or [],
            "maps": item.get("maps") or {},
        })

    return {
        "success": True,
        "query": country,
        "count": len(output),
        "results": output,
        "provider": "REST Countries",
    }


def get_time_info(place: str | None = None, timezone: str | None = None):
    tz_name = _clean_text(timezone or "")
    location = None

    if not tz_name:
        geo = geocode_place(place or "", count=1)

        if not geo.get("success") or not geo.get("results"):
            return {"success": False, "error": "Location not found."}

        location = geo["results"][0]
        tz_name = location.get("timezone") or ""

    try:
        now = datetime.now(ZoneInfo(tz_name))
        return {
            "success": True,
            "place": location,
            "timezone": tz_name,
            "local_time": now.isoformat(),
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M:%S"),
            "timezone_abbreviation": now.tzname(),
        }
    except Exception as error:
        return {"success": False, "error": str(error), "timezone": tz_name}


def get_live_sports(query: str, sport=None, league=None, date=None):
    query = _clean_text(query)

    if SPORTS_API_URL and SPORTS_API_KEY:
        headers = {
            SPORTS_API_HEADER: SPORTS_API_KEY,
            "User-Agent": USER_AGENT,
        }

        params = {"query": query}
        if sport:
            params["sport"] = sport
        if league:
            params["league"] = league
        if date:
            params["date"] = date

        response = _request_json(
            "GET",
            SPORTS_API_URL,
            params=params,
            headers=headers,
        )

        if not response.get("success"):
            return response

        return {
            "success": True,
            "mode": "live_provider",
            "data": response.get("data"),
        }

    fallback_query = " ".join(
        part for part in [
            query,
            sport or "",
            league or "",
            date or "",
            "live score results",
        ]
        if part
    )

    result = search_news(
        fallback_query,
        max_results=8,
        timelimit="d",
    )

    return {
        "success": result.get("success", False),
        "mode": "web_fallback",
        "warning": (
            "No dedicated sports API configured. "
            "Web/news results are not guaranteed real-time scoreboard data."
        ),
        "query": fallback_query,
        "results": result.get("results", []),
        "error": result.get("error"),
    }


def execute_web_action(action: str, **kwargs: Any):
    action = (action or "").strip().lower()

    if action in {"search", "web_search"}:
        return search_web(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", DEFAULT_MAX_RESULTS),
            timelimit=kwargs.get("timelimit"),
            include_domains=kwargs.get("include_domains"),
            exclude_domains=kwargs.get("exclude_domains"),
            prefer_official=kwargs.get("prefer_official", True),
        )

    if action in {"news", "news_search"}:
        return search_news(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", DEFAULT_MAX_RESULTS),
            timelimit=kwargs.get("timelimit", "m"),
        )

    if action in {"read_url", "read", "fetch"}:
        return read_url(
            kwargs.get("url", ""),
            max_chars=kwargs.get("max_chars", MAX_PAGE_CHARS),
        )

    if action in {"research", "deep_research", "search_and_read"}:
        return search_and_read(
            kwargs.get("query", ""),
            max_results=kwargs.get("max_results", 5),
            read_top=kwargs.get("read_top", 3),
            news=kwargs.get("news", False),
            timelimit=kwargs.get("timelimit"),
        )

    if action in {"multi_search", "multi_query"}:
        return multi_query_search(
            kwargs.get("queries", []),
            max_results_per_query=kwargs.get("max_results_per_query", 5),
        )

    if action in {"verify", "verify_claim", "fact_check"}:
        return verify_claim(
            kwargs.get("claim") or kwargs.get("query", ""),
            read_top=kwargs.get("read_top", 4),
        )

    if action in {"geocode", "location_lookup"}:
        return geocode_place(
            kwargs.get("place") or kwargs.get("query", ""),
            count=kwargs.get("count", 5),
        )

    if action in {"weather", "forecast"}:
        return get_weather(
            kwargs.get("place") or kwargs.get("query", ""),
            forecast_days=kwargs.get("forecast_days", 3),
        )

    if action in {"exchange_rate", "fx_rate"}:
        return get_exchange_rate(
            kwargs.get("base", "USD"),
            kwargs.get("quote", "INR"),
        )

    if action in {"currency", "currency_convert", "convert_currency"}:
        return convert_currency(
            kwargs.get("amount", 1),
            kwargs.get("base", "USD"),
            kwargs.get("quote", "INR"),
        )

    if action in {"country", "country_info"}:
        return get_country_info(
            kwargs.get("country") or kwargs.get("query", ""),
            full_text=kwargs.get("full_text", False),
        )

    if action in {"time", "timezone", "time_info"}:
        return get_time_info(
            place=kwargs.get("place"),
            timezone=kwargs.get("timezone"),
        )

    if action in {"sports", "live_sports", "score"}:
        return get_live_sports(
            kwargs.get("query", ""),
            sport=kwargs.get("sport"),
            league=kwargs.get("league"),
            date=kwargs.get("date"),
        )

    if action == "clear_cache":
        return clear_web_cache()

    if action == "status":
        return web_search_status()

    return {"success": False, "error": f"Unknown web action: {action}"}


def web_search_status():
    return {
        "module": "web_search",
        "ready": DDGS is not None and requests is not None,
        "ddgs_installed": DDGS is not None,
        "requests_installed": requests is not None,
        "beautifulsoup_installed": BeautifulSoup is not None,
        "trafilatura_installed": trafilatura is not None,
        "sports_api_configured": bool(SPORTS_API_URL and SPORTS_API_KEY),
        "providers": {
            "web_search": "DuckDuckGo / ddgs",
            "weather": "Open-Meteo",
            "currency": "Frankfurter / ECB",
            "country": "REST Countries",
            "time": "Open-Meteo geocoding + Python zoneinfo",
            "sports": "Configured API" if SPORTS_API_URL and SPORTS_API_KEY else "Web/news fallback",
        },
        "features": [
            "web_search",
            "news_search",
            "website_reader",
            "deep_research",
            "multi_query_search",
            "official_source_priority",
            "claim_verification",
            "weather",
            "currency_conversion",
            "country_information",
            "time_timezone",
            "live_sports_adapter",
            "cache",
            "safe_url_fetch",
            "central_router",
        ],
    }


if __name__ == "__main__":
    print("Maya Internet + Research Engine")
    print(json.dumps(web_search_status(), ensure_ascii=False, indent=2))
