"""
Local HTML cache for HOP constituency and member pages.

Files are stored at:
  Data/hop_html/{page_type}/{period}/{slug}.html

This module handles saving/loading local copies and running batch downloads.
"""
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Data/hop_html/ is 3 levels above uk_elections/ (uk_elections → ElectionWebsite → ElectionWebsite → election_website)
_HOP_HTML_ROOT = Path(__file__).resolve().parents[3] / 'Data' / 'hop_html'

HOP_ALL_PERIODS = [
    ('1386-1421',  '1386–1421'),
    ('1422-1504',  '1422–1504'),
    ('1509-1558',  '1509–1558'),
    ('1558-1603',  '1558–1603'),
    ('1604-1629',  '1604–1629'),
    ('1640-1660',  '1640–1660'),
    ('1660-1690',  '1660–1690'),
    ('1690-1715',  '1690–1715'),
    ('1715-1754',  '1715–1754'),
    ('1754-1790',  '1754–1790'),
    ('1790-1820',  '1790–1820'),
    ('1820-1832',  '1820–1832'),
]

_VALID_PERIODS = {k for k, _ in HOP_ALL_PERIODS}
PAGE_TYPES = ['constituencies', 'members']


# ── Path helpers ──────────────────────────────────────────────────────────────

def get_html_path(page_type, period, slug):
    return _HOP_HTML_ROOT / page_type / period / f'{slug}.html'


def load_local_html(page_type, period, slug):
    """Return raw HTML string from local cache, or None if not present."""
    path = get_html_path(page_type, period, slug)
    if path.exists():
        return path.read_text(encoding='utf-8', errors='replace')
    return None


def save_local_html(page_type, period, slug, html):
    path = get_html_path(page_type, period, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')
    return path


def count_downloaded(page_type, period):
    folder = _HOP_HTML_ROOT / page_type / period
    if not folder.exists():
        return 0
    return sum(1 for _ in folder.glob('*.html'))


def list_downloaded_slugs(page_type, period):
    folder = _HOP_HTML_ROOT / page_type / period
    if not folder.exists():
        return set()
    return {p.stem for p in folder.glob('*.html')}


# ── HTTP fetching ─────────────────────────────────────────────────────────────

_SESSION = requests.Session()
_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (election research; contact schofieldmark@gmail.com)'
})


def _wayback_snapshot_url(url):
    cdx_url = url.replace('https://', '').replace('http://', '')
    try:
        resp = _SESSION.get(
            'https://web.archive.org/cdx/search/cdx',
            params={'url': cdx_url, 'output': 'text', 'fl': 'timestamp',
                    'filter': 'statuscode:200', 'limit': 1, 'sort': 'reverse'},
            timeout=15,
        )
        if resp.status_code == 200:
            ts = resp.text.strip().splitlines()[0].strip() if resp.text.strip() else ''
            if ts:
                return f'https://web.archive.org/web/{ts}/{url}'
    except Exception:
        pass
    return None


def fetch_hop_html(page_type, period, slug, url=None):
    """
    Fetch raw HTML for one HOP page: live site first, then Wayback Machine.
    Returns (html_str_or_None, source_str, error_str).
    source is 'live', 'wayback', or None.

    Pass `url` explicitly when the caller knows the correct path (e.g. member
    pages use the singular '/member/' segment, not '/members/').
    """
    if url is None:
        url = f'https://www.historyofparliamentonline.org/volume/{period}/{page_type}/{slug}'
    errors = []

    try:
        resp = _SESSION.get(url, timeout=20)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            if soup.find('table', class_='hop_mp_table') or soup.find('h1'):
                return resp.text, 'live', ''
            errors.append('live: 200 but no recognisable content')
        else:
            errors.append(f'live: HTTP {resp.status_code}')
    except Exception as e:
        errors.append(f'live error: {e}')

    wb_url = _wayback_snapshot_url(url)
    if not wb_url:
        wb_url = f'https://web.archive.org/web/2023/{url}'
        errors.append('wayback: no CDX snapshot, using timestamp guess')

    for attempt in range(3):
        try:
            resp = _SESSION.get(wb_url, timeout=20)
            if resp.status_code == 200:
                return resp.text, 'wayback', ''
            errors.append(f'wayback: HTTP {resp.status_code}')
        except Exception as e:
            errors.append(f'wayback error: {e}')
        if attempt < 2:
            time.sleep(3)

    return None, None, '; '.join(errors)


# ── Member index discovery ────────────────────────────────────────────────────

def _fetch_member_index(index_url, period):
    """
    Fetch a HOP member index page (e.g. /research/members/1790-1820/A) and
    extract (name, slug, hop_url) triples for each individual member link.
    Returns (list, error_str).
    """
    import re
    pattern = re.compile(
        rf'/volume/{re.escape(period)}/member/([^/?#"\'>\s]+)',
        re.IGNORECASE,
    )

    def _extract(html):
        soup = BeautifulSoup(html, 'html.parser')
        members, seen = [], set()
        for a in soup.find_all('a', href=True):
            m = pattern.search(a['href'])
            if not m:
                continue
            slug = m.group(1).rstrip('/')
            if slug in seen:
                continue
            seen.add(slug)
            name = a.get_text(strip=True)
            url = f'https://www.historyofparliamentonline.org/volume/{period}/member/{slug}'
            members.append((name, slug, url))
        return members

    errors = []

    try:
        resp = _SESSION.get(index_url, timeout=20)
        if resp.status_code == 200:
            members = _extract(resp.text)
            if members:
                return members, ''
            errors.append('live: no member links found on page')
        else:
            errors.append(f'live: HTTP {resp.status_code}')
    except Exception as e:
        errors.append(f'live error: {e}')

    # Wayback fallback
    wb_url = _wayback_snapshot_url(index_url)
    if not wb_url:
        wb_url = f'https://web.archive.org/web/2023/{index_url}'
        errors.append('wayback: no CDX snapshot, using timestamp guess')
    try:
        resp = _SESSION.get(wb_url, timeout=20)
        if resp.status_code == 200:
            members = _extract(resp.text)
            if members:
                return members, ''
            errors.append('wayback: no member links found')
        else:
            errors.append(f'wayback: HTTP {resp.status_code}')
    except Exception as e:
        errors.append(f'wayback error: {e}')

    return [], '; '.join(errors)


def download_member_pages_by_letter(period, letters, delay=1.5, skip_existing=True):
    """
    Generator: for each letter, fetch the HOP member index page to discover
    individual member URLs, then download and save each one.

    Yields dicts with a 'phase' key:
      phase='index'    — fetching or result for a letter's index page
      phase='download' — result for downloading one member biography page
    Common keys: letter, name, slug, status, source, error, done, total
    """
    page_type = 'members'
    existing = list_downloaded_slugs(page_type, period) if skip_existing else set()

    for letter in sorted(letters):
        index_url = (f'https://www.historyofparliamentonline.org'
                     f'/research/members/{period}/{letter}')

        yield {'phase': 'index', 'letter': letter, 'status': 'fetching',
               'name': f'Index {letter}', 'slug': '', 'source': None,
               'error': '', 'done': 0, 'total': 0}

        members, err = _fetch_member_index(index_url, period)

        if not members:
            yield {'phase': 'index', 'letter': letter, 'status': 'error',
                   'name': f'Index {letter}', 'slug': '', 'source': None,
                   'error': err or 'No members found', 'done': 0, 'total': 0}
            continue

        yield {'phase': 'index', 'letter': letter, 'status': 'ok',
               'name': f'Index {letter}', 'slug': '', 'source': 'live',
               'error': '', 'done': 0, 'total': len(members)}

        letter_total = len(members)
        for i, (name, slug, url) in enumerate(members, 1):
            if skip_existing and slug in existing:
                yield {'phase': 'download', 'slug': slug, 'name': name, 'letter': letter,
                       'status': 'skip', 'source': None, 'error': '',
                       'done': i, 'total': letter_total}
                continue

            html, source, error = fetch_hop_html(page_type, period, slug, url=url)
            if html:
                save_local_html(page_type, period, slug, html)
                existing.add(slug)
                yield {'phase': 'download', 'slug': slug, 'name': name, 'letter': letter,
                       'status': 'ok', 'source': source, 'error': '',
                       'done': i, 'total': letter_total}
            else:
                yield {'phase': 'download', 'slug': slug, 'name': name, 'letter': letter,
                       'status': 'error', 'source': None, 'error': error,
                       'done': i, 'total': letter_total}

            if i < letter_total:
                time.sleep(delay)


# ── Batch download (constituencies) ──────────────────────────────────────────

def download_pages(page_type, period, slug_triples, delay=1.5, skip_existing=True):
    """
    Generator: download and save HTML pages, yielding a progress dict per item.

    slug_triples: iterable of (display_name, slug, url)

    Yielded dicts have keys:
      slug, name, letter, status ('ok'/'skip'/'error'), source, error, done, total
    """
    existing = list_downloaded_slugs(page_type, period) if skip_existing else set()
    items = list(slug_triples)
    total = len(items)

    for i, (name, slug, hop_url) in enumerate(items, 1):
        letter = name[0].upper() if name else '?'

        if skip_existing and slug in existing:
            yield {'slug': slug, 'name': name, 'letter': letter,
                   'status': 'skip', 'source': None, 'error': '', 'done': i, 'total': total}
            continue

        html, source, error = fetch_hop_html(page_type, period, slug,
                                              url=hop_url if hop_url else None)
        if html:
            save_local_html(page_type, period, slug, html)
            yield {'slug': slug, 'name': name, 'letter': letter,
                   'status': 'ok', 'source': source, 'error': '', 'done': i, 'total': total}
        else:
            yield {'slug': slug, 'name': name, 'letter': letter,
                   'status': 'error', 'source': None, 'error': error, 'done': i, 'total': total}

        if i < total:
            time.sleep(delay)
