"""
Scrape History of Parliament Online (1820-1832) constituency election results.

Fetches pages via Wayback Machine (the live site uses JS challenge protection).
Writes results to an Excel spreadsheet.

Usage:
    python scrape_hop_constituencies.py [--output PATH] [--limit N] [--delay SEC]
"""

import argparse
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# ── Constants ────────────────────────────────────────────────────────────────

WAYBACK_PREFIX = re.compile(r'^(?:https?://web\.archive\.org)?/web/[^/]+/')
BASE_URL = 'https://www.historyofparliamentonline.org/volume/1820-1832/constituencies/'
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── URL helpers ──────────────────────────────────────────────────────────────

def wayback_url(original_url, year='2023'):
    """Return a Wayback Machine URL for the given original URL."""
    return f'https://web.archive.org/web/{year}/{original_url}'


def _wayback_snapshot_url(original_url):
    """
    Use the CDX API to find the most recent archived snapshot with a 200 status.
    Returns a Wayback Machine URL or None.
    """
    cdx_url = re.sub(r'^https?://', '', original_url)
    try:
        resp = SESSION.get(
            'https://web.archive.org/cdx/search/cdx',
            params={
                'url': cdx_url,
                'output': 'text',
                'fl': 'timestamp',
                'filter': 'statuscode:200',
                'limit': 1,
                'sort': 'reverse',
            },
            timeout=15,
        )
        if resp.status_code == 200:
            timestamp = resp.text.strip().splitlines()[0].strip() if resp.text.strip() else ''
            if timestamp:
                return f'https://web.archive.org/web/{timestamp}/{original_url}'
    except Exception:
        pass
    return None


def hop_id_from_url(url):
    """
    Extract the HOP id from a member URL — everything after /volume/, e.g.
    '1820-1832/member/herries-john-1778-1855'. Works for any period.
    """
    if url and '/volume/' in url:
        return url.split('/volume/', 1)[1].rstrip('/')
    return ''


def clean_url(href):
    """Strip Wayback Machine prefix from an href, returning the canonical https URL."""
    if not href:
        return ''
    cleaned = WAYBACK_PREFIX.sub('', href)
    # Normalise to https and ensure www.
    cleaned = re.sub(r'^https?://', 'https://', cleaned)
    if cleaned.startswith('https://historyofparliamentonline.org'):
        cleaned = cleaned.replace('https://historyofparliamentonline.org', 'https://www.historyofparliamentonline.org', 1)
    return cleaned


def get_constituency_slugs(cdx_file=None):
    """
    Return a list of (name, url) tuples for all 1820-1832 constituencies.
    If cdx_file is given, reads from it; otherwise queries the CDX API.
    """
    if cdx_file:
        with open(cdx_file) as f:
            raw_urls = [l.strip() for l in f if l.strip()]
    else:
        print('Querying CDX API for constituency URLs...', flush=True)
        resp = SESSION.get(
            'http://web.archive.org/cdx/search/cdx',
            params={
                'url': 'www.historyofparliamentonline.org/volume/1820-1832/constituencies/*',
                'output': 'text',
                'fl': 'original',
                'collapse': 'urlkey',
                'limit': 600,
            },
            timeout=30,
        )
        raw_urls = [l.strip() for l in resp.text.splitlines() if l.strip()]

    results = []
    seen_slugs = set()
    for url in raw_urls:
        # Normalise URL
        url = re.sub(r':80/', '/', url)
        url = url.rstrip('/')
        # Match slugs that may contain hyphens and URL-encoded parentheses (%28 / %29)
        m = re.match(
            r'https?://www\.historyofparliamentonline\.org/volume/1820-1832/constituencies/([a-z0-9][a-z0-9\-%28%29]+)$',
            url
        )
        if not m:
            continue
        slug = m.group(1)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        # Decode %28/%29 → () for the display name, replace hyphens with spaces
        name = slug.replace('%28', '(').replace('%29', ')').replace('-', ' ').title()
        results.append((name, f'https://www.historyofparliamentonline.org/volume/1820-1832/constituencies/{slug}'))

    return sorted(results, key=lambda x: x[0])


# ── Page fetching ────────────────────────────────────────────────────────────

def fetch_page(url, retries=2):
    """
    Fetch a constituency page, returning (BeautifulSoup, error_str).
    Tries the live site first; falls back to Wayback Machine if that fails.
    Returns (None, error_str) if both sources fail.
    """
    errors = []

    # Try the live site first
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Verify we got actual content, not a bot-challenge page
            if soup.find('table', class_='hop_mp_table') or soup.find('h1'):
                return soup, ''
            errors.append(f'live site returned 200 but no recognisable content')
        else:
            errors.append(f'live site HTTP {resp.status_code}')
    except Exception as e:
        errors.append(f'live site error: {e}')

    # Fall back to Wayback Machine — find a valid snapshot URL via availability API
    wb_url = _wayback_snapshot_url(url)
    if not wb_url:
        wb_url = wayback_url(url)   # last-resort: guess with year timestamp
        errors.append('availability API returned no snapshot; trying timestamp URL')

    for attempt in range(retries + 1):
        try:
            resp = SESSION.get(wb_url, timeout=20)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, 'html.parser'), ''
            errors.append(f'Wayback HTTP {resp.status_code}')
            print(f'  HTTP {resp.status_code} for {wb_url}', flush=True)
        except Exception as e:
            errors.append(f'Wayback error: {e}')
            print(f'  Error fetching {wb_url}: {e}', flush=True)
        if attempt < retries:
            time.sleep(3)

    return None, '; '.join(errors)


# ── Parsing ──────────────────────────────────────────────────────────────────

_QUALIFIER_RE  = re.compile(r'\s+(on\s+petition)\b', re.IGNORECASE)
_REELECTED_RE  = re.compile(r're-elected\b', re.IGNORECASE)
_PEERAGE_RE    = re.compile(
    r'\b(?:earl|viscount|duke|baron|marquess|marquis|lord)\s+(?:of\s+)?([A-Z][a-zA-Z]+)',
    re.IGNORECASE
)


def parse_vice_note(cand_td):
    """
    Extract the replacement note from a candidate cell containing <em>vice</em>.

    Returns (is_vice, note_string, ex_mp_url, ex_mp_surname).
    - note_string: 'Surname(s) reason' (no bracket prefix)
    - ex_mp_url:   cleaned member URL of the replaced MP, or ''
    - ex_mp_surname: raw surname string used for _flush_group matching
    """
    vice_em = cand_td.find('em')
    if not vice_em or vice_em.get_text(strip=True).lower() != 'vice':
        return False, '', '', ''

    parts = []
    ex_mp_url = ''
    for node in vice_em.next_siblings:
        if hasattr(node, 'name') and node.name == 'a' and not ex_mp_url:
            href = node.get('href', '')
            if href:
                ex_mp_url = clean_url(href)
        text = node.get_text(strip=True) if hasattr(node, 'get_text') else str(node).strip()
        if text:
            parts.append(text)
    vice_text = ' '.join(parts).strip().strip(',').strip()

    if not vice_text:
        return True, '', ex_mp_url, ''

    # Split on "on petition" first (it may precede the comma), then fall back to comma.
    m = _QUALIFIER_RE.search(vice_text)
    if m:
        surname = vice_text[:m.start()].strip()
        reason  = vice_text[m.start():].strip()
    else:
        comma_idx = vice_text.find(',')
        if comma_idx != -1:
            surname = vice_text[:comma_idx].strip()
            reason  = vice_text[comma_idx + 1:].strip()
        else:
            surname = vice_text.strip()
            reason  = ''

    note = f'{surname} {reason}'.strip() if reason else surname
    return True, note, ex_mp_url, surname


def _name_el_trailing(cand_td):
    """Return text that appears after the primary name element (<a> or first <span>)."""
    name_el = cand_td.find('a') or cand_td.find('span')
    if not name_el:
        return ''
    parts = []
    for node in name_el.next_siblings:
        if hasattr(node, 'name') and node.name == 'em':
            break   # stop at <em>vice</em>
        text = node.get_text(strip=True) if hasattr(node, 'get_text') else str(node).strip()
        if text:
            parts.append(text)
    return ' '.join(parts).strip()


def parse_reelected_note(cand_td):
    """
    Detect 're-elected after appointment to office' trailing text.
    Works whether or not the candidate has a link.
    Returns (True, trailing_text) or (False, '').
    """
    trailing = _name_el_trailing(cand_td)
    return (_REELECTED_RE.search(trailing) is not None, trailing)


def peerage_alias(trailing_text):
    """
    Extract a peerage title word from trailing text like 'earl of Brecknock'.
    Returns the uppercased title word, or '' if none found.
    """
    m = _PEERAGE_RE.search(trailing_text)
    return m.group(1).upper() if m else ''


def split_vice_names(surname_str):
    """
    Split 'Haldimand and Torrens' into ['Haldimand', 'Torrens'].
    Used to find which rows to mark with * in petition cases.
    """
    return [n.strip() for n in re.split(r'\s+and\s+', surname_str, flags=re.IGNORECASE) if n.strip()]


def _flush_group(group):
    """
    Post-process a completed election group:
    - For petition-within-GE rows, add '*' to the votes of the candidates they replaced.
    - Remove internal tracking keys.
    """
    petition_rows = [r for r in group if r.get('_vice_names')]
    for p_row in petition_rows:
        for name in p_row['_vice_names']:
            for row in group:
                if row is p_row:
                    continue
                if name.lower() in row['Candidate'].lower():
                    row['Votes'] = (row['Votes'] + '*') if row['Votes'] else '*'
                    break

    for row in group:
        row.pop('_vice_names', None)

    return group


def _get_votes(tr, num_vote_cols):
    """Return a votes string from the TR, handling 1 or 2 vote columns."""
    cells = tr.find_all('td', class_='hop_mp_table_votes_td')
    if not cells:
        return ''

    def cell_text(td):
        td = td.__copy__()          # don't mutate original
        for fn in td.find_all(class_='see-footnote'):
            fn.decompose()
        return td.get_text(strip=True)

    def normalise(v):
        return '0' if v.lower() == 'nil' else v

    if num_vote_cols >= 2 and len(cells) >= 2:
        v1, v2 = normalise(cell_text(cells[0])), normalise(cell_text(cells[1]))
        if v1 and v2:
            return f'{v1}/{v2}'
        return v1 or v2

    return normalise(cell_text(cells[0]))


def parse_elections_table(soup, constituency_name):
    """Parse the hop_mp_table on a constituency page, return list of row dicts."""
    table = soup.find('table', class_='hop_mp_table')
    if not table:
        return []

    tbody = table.find('tbody')
    if not tbody:
        return []

    # Detect number of votes columns from the header colspan
    votes_th = table.find('th', class_=lambda c: c and 'hop_mp_table_th_votes' in c)
    num_vote_cols = int(votes_th.get('colspan', 1)) if votes_th else 1

    all_rows = []
    current_group = []      # rows accumulated for the current election
    current_date = ''
    current_is_bye = False
    url_to_name   = {}      # candidate_url → fullest known name
    alias_to_name = {}      # peerage title word (upper) → full name

    for tr in tbody.find_all('tr'):
        tr_classes = ' '.join(tr.get('class', []))
        is_new_group = 'hop_new_p' in tr_classes

        date_td = tr.find('td', class_='hop_mp_table_date_td')
        cand_td = None
        for td in tr.find_all('td'):
            cls = ' '.join(td.get('class', []))
            if 'election_win' in cls or 'election_lose' in cls:
                cand_td = td
                break

        if not cand_td:
            continue

        # ── Flush previous group when a new election starts ──────────────────
        if is_new_group and current_group:
            all_rows.extend(_flush_group(current_group))
            current_group = []

        # ── Date ────────────────────────────────────────────────────────────
        date_text = date_td.get_text(strip=True) if date_td else ''
        has_new_date = bool(date_text)

        if has_new_date:
            current_date = date_text
            current_is_bye = bool(date_td.find('i') or date_td.find('em'))

        # ── Candidate name and link ──────────────────────────────────────────
        link_tag = cand_td.find('a')
        if link_tag:
            href = link_tag.get('href', '')
            candidate_url = clean_url(href)
            span = link_tag.find('span')
            candidate_name = span.get_text(strip=True) if span else link_tag.get_text(strip=True)
        else:
            candidate_url = ''
            span = cand_td.find('span')
            candidate_name = span.get_text(strip=True) if span else ''

        candidate_name = re.sub(r'\s+', ' ', candidate_name).strip().rstrip(',')
        if not candidate_name:
            continue

        # ── Re-elected after appointment to office ───────────────────────────
        is_reelected, reelected_text = parse_reelected_note(cand_td)
        ex_mp_hop_id = ''
        if is_reelected:
            # candidate_name may be just a surname or a peerage title word.
            # Try URL first, then alias dict (covers cases like BRECKNOCK with no link).
            full_name = (url_to_name.get(candidate_url, '')
                         or alias_to_name.get(candidate_name.upper(), ''))
            display = full_name or candidate_name
            note = f'{display.title()} {reelected_text}'.strip()
            if full_name:
                candidate_name = full_name
            # The re-elected MP vacated and won the ensuing by-election — they are the old MP
            ex_mp_hop_id = hop_id_from_url(candidate_url) or display

        # ── Vice note and election-type logic ───────────────────────────────
        if is_reelected:
            is_vice = False
        else:
            is_vice, note, ex_mp_url, ex_mp_surname = parse_vice_note(cand_td)
            ex_mp_hop_id = hop_id_from_url(ex_mp_url) or ex_mp_surname
        vice_names = []
        election_type = 'By-election' if current_is_bye else 'General'

        if is_vice:
            if has_new_date:
                current_is_bye = True
                election_type = 'By-election'
            else:
                if not current_is_bye:
                    election_type = 'Petition'
                    vice_names = split_vice_names(ex_mp_surname)
                else:
                    election_type = 'By-election'

        # ── Update name lookups (only when name looks like more than a bare surname) ──
        if ' ' in candidate_name:
            if candidate_url:
                url_to_name[candidate_url] = candidate_name
            # Build peerage alias from trailing text, e.g. "earl of Brecknock" → BRECKNOCK
            trailing = _name_el_trailing(cand_td)
            alias = peerage_alias(trailing)
            if alias:
                alias_to_name[alias] = candidate_name

        # ── Votes ───────────────────────────────────────────────────────────
        votes = _get_votes(tr, num_vote_cols)

        row = {
            'Election Type': election_type,
            'Date': current_date,
            'Constituency': constituency_name,
            'Candidate': candidate_name,
            'Hop ID': hop_id_from_url(candidate_url),
            'Ex-MP': ex_mp_hop_id,
            'Candidate URL': candidate_url,
            'Votes': votes,
            'Notes': note,
            '_vice_names': vice_names,   # internal; stripped before output
        }
        current_group.append(row)

    # Flush the final group
    if current_group:
        all_rows.extend(_flush_group(current_group))

    return all_rows


# ── Spreadsheet output ───────────────────────────────────────────────────────

HEADERS_ROW = ['Election Type', 'Date', 'Constituency', 'Candidate', 'Hop ID', 'Ex-MP', 'Candidate URL', 'Votes', 'Notes']
COL_WIDTHS   = [14, 16, 28, 32, 28, 28, 60, 8, 60]

HEADER_FILL = PatternFill('solid', fgColor='1F4E79')
HEADER_FONT = Font(bold=True, color='FFFFFF')

BYE_FILL      = PatternFill('solid', fgColor='FFF2CC')  # pale yellow — by-elections
PETITION_FILL = PatternFill('solid', fgColor='FCE4D6')  # pale orange — petitions within GE
UNSEATED_FONT = Font(italic=True)                        # italic — candidates with * votes


def write_spreadsheet(all_rows, output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '1820-1832 Elections'

    # Header
    for col_idx, (h, w) in enumerate(zip(HEADERS_ROW, COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.column_dimensions[cell.column_letter].width = w

    ws.row_dimensions[1].height = 16
    ws.freeze_panes = 'A2'

    # Data
    for row_idx, row in enumerate(all_rows, start=2):
        for col_idx, key in enumerate(HEADERS_ROW, start=1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(key, ''))

        etype = row.get('Election Type', '')
        if etype == 'By-election':
            fill = BYE_FILL
        elif etype == 'Petition':
            fill = PETITION_FILL
        else:
            fill = None

        if fill:
            for col_idx in range(1, len(HEADERS_ROW) + 1):
                ws.cell(row=row_idx, column=col_idx).fill = fill

        # Italicise rows where votes have been asterisked (unseated by petition)
        votes_val = str(row.get('Votes', ''))
        if '*' in votes_val:
            for col_idx in range(1, len(HEADERS_ROW) + 1):
                ws.cell(row=row_idx, column=col_idx).font = UNSEATED_FONT

    wb.save(output_path)
    print(f'Saved {len(all_rows)} rows to {output_path}')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Scrape HOP 1820-1832 constituency elections')
    parser.add_argument('--output', default='hop_elections_1820_1832.xlsx',
                        help='Output Excel file path')
    parser.add_argument('--limit', type=int, default=0,
                        help='Maximum number of constituencies to scrape (0=all)')
    parser.add_argument('--delay', type=float, default=1.5,
                        help='Delay in seconds between requests')
    parser.add_argument('--cdx-file', default='C:/Users/Marka/AppData/Local/Temp/hop_urls.txt',
                        help='Pre-downloaded CDX URL list file')
    args = parser.parse_args()

    constituencies = get_constituency_slugs(cdx_file=args.cdx_file)
    print(f'Constituencies to scrape: {len(constituencies)}', flush=True)

    if args.limit:
        constituencies = constituencies[:args.limit]

    all_rows = []
    for i, (name, url) in enumerate(constituencies, start=1):
        print(f'[{i}/{len(constituencies)}] {name} ...', end=' ', flush=True)
        soup, fetch_error = fetch_page(url)
        if soup is None:
            print(f'FAILED ({fetch_error})')
            continue

        rows = parse_elections_table(soup, name)
        if rows:
            all_rows.extend(rows)
            print(f'{len(rows)} rows')
        else:
            # Try to detect if the page just has no elections table
            h3 = soup.find('h3', id='constituency-elections')
            if h3:
                print('table missing (has elections heading)')
            else:
                print('no elections section')

        if i < len(constituencies):
            time.sleep(args.delay)

    write_spreadsheet(all_rows, args.output)


if __name__ == '__main__':
    main()
