"""
HOP 1820-1832 import: scrape constituency pages and preview/commit DB changes.
"""
import re
from datetime import date as date_cls, datetime as dt

import requests
from bs4 import BeautifulSoup as _BS

from django.db import transaction
from django.utils.timezone import make_aware


from .models import (
    Constituency, Election, Party, Person,
    CandidateResult, ConstituencyResult,
)

# ── Constituency list cache ───────────────────────────────────────────────────
_CONSTITUENCY_CACHE = None   # list of (display_name, slug, hop_url)

_HOP_YEARS = ['1820', '1826', '1830', '1831']


def _name_to_slug(name):
    """Convert a constituency display name to a HOP URL slug."""
    return name.lower().replace(' ', '-').replace('(', '%28').replace(')', '%29')


def get_hop_constituency_list():
    """
    Return cached list of (display_name, slug, hop_url) for all 1820-1832
    constituencies, built from the DB (no CDX API call needed).
    """
    global _CONSTITUENCY_CACHE
    if _CONSTITUENCY_CACHE is None:
        _CONSTITUENCY_CACHE = _build_list_from_db()
    return _CONSTITUENCY_CACHE


def _build_list_from_db():
    """Build the constituency list from CandidateResult + alternating Constituency records."""
    # Constituencies that have results in any of the four GEs
    names_with_data = set(
        CandidateResult.objects
        .filter(election__type='GE', election__year__in=_HOP_YEARS)
        .values_list('constituency__name', flat=True)
        .distinct()
    )
    # Alternating constituencies (Scottish burghs) may lack results in some years
    names_alt = set(
        Constituency.objects
        .filter(alternating__isnull=False)
        .exclude(alternating='')
        .values_list('name', flat=True)
    )
    result = []
    for name in sorted(names_with_data | names_alt):
        # Prefer hop_name for slug if set (handles name mismatches)
        const = Constituency.objects.filter(name=name).order_by('start_date').first()
        hop_display = (const.hop_name if const and const.hop_name else name)
        slug = _name_to_slug(hop_display)
        url = f'https://www.historyofparliamentonline.org/volume/1820-1832/constituencies/{slug}'
        result.append((name, slug, url))
    return result


def slug_to_name(slug):
    """Best-effort: convert a URL slug to a display name."""
    return slug.replace('%28', '(').replace('%29', ')').replace('-', ' ').title()


# ── Date / votes parsing ──────────────────────────────────────────────────────
_MONTH = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def parse_hop_date(s):
    """Return (year, month_or_None, day_or_None) from a HOP date string."""
    s = s.strip()
    # "D Mon.? YYYY" — by-election full date, e.g. "15 Jun 1826" or "31 Mar. 1820"
    m = re.match(r'(\d+)\s+([A-Za-z]+)\.?\s+(\d{4})', s)
    if m:
        return int(m.group(3)), _MONTH.get(m.group(2).lower()[:3]), int(m.group(1))
    # "YYYY Mon.?" — general election, e.g. "1826" or "1826 Mar"
    m = re.match(r'(\d{4})\s*([A-Za-z]*)', s)
    if m:
        mon = _MONTH.get(m.group(2).lower()[:3]) if m.group(2) else None
        return int(m.group(1)), mon, None
    # "Mon.? YYYY" — month-year without day, e.g. "Jun 1826" or "Mar. 1826"
    m = re.match(r'([A-Za-z]+)\.?\s+(\d{4})', s)
    if m:
        return int(m.group(2)), _MONTH.get(m.group(1).lower()[:3]), None
    # "Mon.? D YYYY" — month-day-year, e.g. "Jun 15 1826"
    m = re.match(r'([A-Za-z]+)\.?\s+(\d+)\s+(\d{4})', s)
    if m:
        return int(m.group(3)), _MONTH.get(m.group(1).lower()[:3]), int(m.group(2))
    # Last resort: trailing 4-digit year
    m = re.search(r'(\d{4})\s*$', s)
    if m:
        return int(m.group(1)), None, None
    return None, None, None


def parse_votes(s):
    """Return (int_or_None, is_disqualified) from a votes string."""
    if not s:
        return None, False
    disq = '*' in s
    clean = s.replace('*', '').strip()
    if '/' in clean:            # dual-seat "v1/v2" — take first
        clean = clean.split('/')[0].strip()
    try:
        return int(clean.replace(',', '')), disq
    except (ValueError, AttributeError):
        return None, disq


def candidate_is_elected(name):
    """True when HOP presents name in ALL CAPS (their elected convention)."""
    name = name.strip()
    return bool(name) and name == name.upper()


# ── DB helpers ────────────────────────────────────────────────────────────────

def find_constituency(name):
    """Find Constituency by name or hop_name. Returns (obj_or_None, error_str)."""
    qs = Constituency.objects.filter(name=name)
    if qs.count() == 1:
        return qs.first(), None
    if qs.count() > 1:
        return qs.order_by('start_date').first(), None
    qs = Constituency.objects.filter(hop_name=name)
    if qs.exists():
        return qs.first(), None
    return None, f"'{name}' not found in DB (set hop_name on Constituency if the name differs)"


def find_ge(year):
    """Find a GE by year. Returns (obj_or_None, error_str)."""
    try:
        return Election.objects.get(year=str(year), type='GE'), None
    except Election.DoesNotExist:
        return None, f"No GE found for year {year}"
    except Election.MultipleObjectsReturned:
        return Election.objects.filter(year=str(year), type='GE').first(), None


def get_independent():
    """Get or create the Independent party."""
    p, _ = Party.objects.get_or_create(name='Independent', defaults={'colour': '#888888'})
    return p


def preview_person(hop_id, name, elected_flag):
    """
    Determine what would happen to the Person record.
    Returns (existing_person_or_None, action) where action is
    'link', 'create', or 'none'.
    """
    if not hop_id:
        return None, 'none'
    p = Person.objects.filter(hop_id=hop_id).first()
    return (p, 'link') if p else (None, 'create')


def _party_from_constituency_crs(name, constituency):
    """
    Find party by name-matching within the same constituency's existing CandidateResults.
    Uses constituency__name so all Constituency records with this name are searched,
    regardless of which date-range record was used when the data was imported.
    Returns (Party, source) only when all name-matched CRs agree on a single party.
    """
    if not constituency:
        return None, None
    surname = _core_surname(name)
    if not surname:
        return None, None
    sig = _sig_words(name)
    if not sig:
        return None, None
    crs = [
        cr for cr in (CandidateResult.objects
                      .filter(constituency__name=constituency.name,
                              candidate__icontains=surname)
                      .exclude(party__isnull=True)
                      .exclude(party__name='Independent')
                      .select_related('party'))
        if sig <= _sig_words(cr.candidate) or _sig_words(cr.candidate) <= sig
    ]
    if not crs:
        return None, None
    parties = {cr.party_id for cr in crs}
    if len(parties) == 1:
        return crs[0].party, 'constituency_name_match'
    return None, None


def _resolve_old_mp(constituency, rows):
    """
    Return the outgoing MP's name for a by-election.
    Priority: hop_id lookup → CandidateResult surname match (elected only) → raw surname.
    """
    for row in rows:
        ex_mp = (row.get('Ex-MP') or '').strip()
        if not ex_mp:
            continue
        # hop_id contains '/' (e.g. '1820-1832/member/slug')
        if '/' in ex_mp:
            person = Person.objects.filter(hop_id=ex_mp).first()
            if person:
                return person.name
            # hop_id known but Person not yet created — use slug as fallback surname
            ex_mp = ex_mp.rsplit('/', 1)[-1]  # last segment of path
        # Surname string — search elected CandidateResults for this constituency
        cr = (CandidateResult.objects
              .filter(constituency__name=constituency.name,
                      candidate__icontains=ex_mp,
                      elected=True)
              .order_by('-election__date')
              .first())
        if cr:
            return cr.candidate
        return ex_mp.title()  # plain surname as last resort
    return ''


_WIKI_CACHE = {}  # constituency_name → BeautifulSoup or None

_WIKI_SUFFIXES = [
    '_(constituency)',
    '_(UK_Parliament_constituency)',
    '_(UK_parliament_constituency)',
    '_constituency',
]

_WIKI_HEADERS = {'User-Agent': 'Mozilla/5.0 (election research; contact schofieldmark@gmail.com)'}


def _fetch_wikipedia_page(constituency_name):
    """Fetch and cache the Wikipedia page for a constituency, trying common URL patterns."""
    if constituency_name in _WIKI_CACHE:
        return _WIKI_CACHE[constituency_name]
    base = constituency_name.replace(' ', '_')
    soup = None
    for suffix in _WIKI_SUFFIXES:
        url = f'https://en.wikipedia.org/wiki/{base}{suffix}'
        try:
            r = requests.get(url, timeout=15, headers=_WIKI_HEADERS)
            if r.status_code == 200:
                soup = _BS(r.content, 'html.parser')
                break
        except Exception:
            continue
    _WIKI_CACHE[constituency_name] = soup
    return soup


def _match_wiki_party(party_text):
    """Map a Wikipedia party string to a DB Party object."""
    pt = party_text.strip()
    if not pt or pt.lower() in ('independent', 'none', '-', '—', 'n/a', ''):
        return None
    p = Party.objects.filter(name__iexact=pt).first()
    if p and p.name:
        return p
    for party in Party.objects.exclude(name='Independent').exclude(name=''):
        if party.name.lower() in pt.lower() or pt.lower() in party.name.lower():
            return party
    return None


_PRIORITY_PARTIES = ['Tory', 'Whig', 'Radical']


def _party_from_wikipedia(candidate_name, constituency_name):
    """
    Find the candidate's party by locating their name in any table cell on the
    constituency's Wikipedia page, then reading the next sibling <td>.
    Checks common 1820-1832 parties first (Tory, Whig, Radical) before falling
    back to the full DB party list.
    """
    soup = _fetch_wikipedia_page(constituency_name)
    if not soup:
        return None, None
    sig = _sig_words(candidate_name)
    if not sig:
        return None, None

    for cell in soup.find_all(['td', 'th']):
        cell_sig = _sig_words(cell.get_text(strip=True))
        overlap = sig & cell_sig
        if len(overlap) < min(2, len(sig)):
            continue
        next_td = cell.find_next_sibling('td')
        if not next_td:
            continue
        next_text = next_td.get_text(strip=True)
        for keyword in _PRIORITY_PARTIES:
            if keyword.lower() in next_text.lower():
                party = Party.objects.filter(name__icontains=keyword).exclude(name='').first()
                if party:
                    return party, 'wikipedia'
        party = _match_wiki_party(next_text)
        if party:
            return party, 'wikipedia'

    return None, None


def determine_party(existing_cr, person, name='', constituency=None):
    """
    Best-effort party determination. Returns (Party, source_str).
    Priority:
      1. Party already on the matching DB CandidateResult
      2. Any other CandidateResult for this person (via Person object)
      3. Name-match within this constituency's existing CandidateResults
      4. Constituency Wikipedia page
      5. Independent fallback
    """
    if existing_cr and existing_cr.party:
        return existing_cr.party, 'existing_db_record'

    if person:
        cr = (CandidateResult.objects
              .filter(person=person)
              .exclude(party__name='Independent')
              .select_related('party', 'election')
              .first())
        if cr:
            return cr.party, f'other_election_{cr.election.year}'

    if name:
        party, src = _party_from_constituency_crs(name, constituency)
        if party:
            return party, src

    if name and constituency:
        party, src = _party_from_wikipedia(name, constituency.name)
        if party:
            return party, src

    return get_independent(), 'default_independent'


_ROMAN_RE = re.compile(r'\b(Ii{1,2}|Iv|Vi{0,3}|Ix|Xi{0,2})\b')

_HONORIFICS_RE = re.compile(
    r'^(sir|lord|lady|hon\.?|dr\.?|rev\.?|mr\.?|mrs\.?)\s+', re.IGNORECASE
)
_TRAILING_TITLE_RE = re.compile(
    r',?\s*(\d+\w*\s+)?(bt|bart|baronet|esq|k\.?c\.?b\.?|k\.?g\.?|m\.?p\.?)\.?\s*$',
    re.IGNORECASE
)
_SKIP_WORDS = {'sir', 'lord', 'lady', 'the', 'of', 'bt', 'bart', 'esq', 'hon', 'rev'}


def _core_surname(name):
    """Strip leading honorifics and trailing titles, return the final name word."""
    n = _TRAILING_TITLE_RE.sub('', name).strip().rstrip(',')
    n = _HONORIFICS_RE.sub('', n).strip()
    parts = [p for p in re.split(r'[\s,]+', n) if p]
    return parts[-1].lower() if parts else ''


def _sig_words(name):
    """Return significant words (>2 chars, not a title/skip word) from a name."""
    return {w.strip('.,') for w in name.lower().split()
            if len(w.strip('.,')) > 2 and w.strip('.,') not in _SKIP_WORDS}


def _find_person_by_name(name):
    """
    Find a unique existing Person by name similarity when no hop_id is available.
    Only returns a match when exactly one Person shares the same significant words.
    """
    surname = _core_surname(name)
    if not surname:
        return None
    hop_sig = _sig_words(name)
    if not hop_sig:
        return None
    matches = [
        p for p in Person.objects.filter(name__icontains=surname)
        if hop_sig <= _sig_words(p.name) or _sig_words(p.name) <= hop_sig
    ]
    return matches[0] if len(matches) == 1 else None


def find_matching_cr(constituency, election, name, elected_flag, year=None):
    """
    Try to find an existing CandidateResult to update.
    Returns (obj_or_None, quality_str).
    """
    qs = list(CandidateResult.objects.filter(
        constituency__name=constituency.name, election=election
    ).select_related('party', 'person'))

    nl = name.lower()

    # 1. Exact match
    for cr in qs:
        if cr.candidate.lower() == nl:
            return cr, 'exact'

    # 2. Raw last-word surname match
    raw_surname = nl.split()[-1].rstrip('.,') if nl.split() else nl
    for cr in qs:
        cr_parts = cr.candidate.lower().split()
        if cr_parts and cr_parts[-1].rstrip('.,') == raw_surname:
            return cr, 'surname'

    # 3. Core-surname match — strips "Bt." / "8th Baronet" / "Sir" etc. before comparing
    hop_core = _core_surname(name)
    if hop_core:
        for cr in qs:
            if _core_surname(cr.candidate) == hop_core:
                return cr, 'core_surname'

    # 4. For years with complete data, significant-word overlap (unique best match only)
    if year in (1830, 1831):
        hop_words = _sig_words(name)
        if hop_words:
            scored = sorted(
                [(len(hop_words & _sig_words(cr.candidate)), cr) for cr in qs],
                key=lambda t: t[0],
                reverse=True,
            )
            if scored and scored[0][0] > 0:
                # Accept only if there is a clear single best match
                if len(scored) == 1 or scored[0][0] > scored[1][0]:
                    return scored[0][1], 'word_overlap'

    # 5. Last resort for elected: single winner in group
    if elected_flag:
        winners = [cr for cr in qs if cr.elected and not cr.disqualified]
        if len(winners) == 1:
            return winners[0], 'sole_winner'

    return None, None


# ── Preview builder ───────────────────────────────────────────────────────────

def build_preview(rows, constituency_name):
    """
    Given parsed scraper rows for one constituency, return a structured
    preview of what DB changes would be applied.
    """
    const, err = find_constituency(constituency_name)
    result = {
        'constituency_name': constituency_name,
        'constituency': const,
        'const_error': err,
        'elections': [],
    }
    if not const:
        return result

    # Group consecutive rows sharing the same Date (Petition rows share GE date)
    groups = []
    for row in rows:
        date_str = row['Date']
        etype_grp = 'BE' if row['Election Type'] == 'By-election' else 'GE'
        if groups and groups[-1][0] == date_str:
            groups[-1][2].append(row)
        else:
            groups.append((date_str, etype_grp, [row]))

    for date_str, etype_grp, grp_rows in groups:
        result['elections'].append(_process_group(const, date_str, etype_grp, grp_rows))

    return result


def _apply_petition_outcomes(candidates, petition_rows):
    """
    Post-process GE candidates using petition rows.

    The petition row's Candidate field names the person AWARDED the seat on
    appeal — they should be marked elected.  The original winner who is not
    that person should be marked disqualified/not-elected.

    Petition rows are NOT added as candidates themselves.
    """
    if not petition_rows:
        return

    raw_notes = [r.get('Notes', '').strip() for r in petition_rows if r.get('Notes', '').strip()]
    petition_note = '; '.join(raw_notes) if raw_notes else 'Removed on petition.'

    def _alpha_words(s):
        return {re.sub(r'[^a-z]', '', w) for w in s.lower().split()
                if len(re.sub(r'[^a-z]', '', w)) > 1}

    # Find the petition winner (named in the petition row) among GE candidates.
    petition_winner = None
    for pr in petition_rows:
        pr_words = _alpha_words(pr.get('Candidate', ''))
        for cand in candidates:
            if pr_words & _alpha_words(cand['row']['Candidate']):
                petition_winner = cand
                break
        if petition_winner:
            break

    # The candidate to disqualify is the original elected winner who is not the petition winner.
    if petition_winner:
        disq_cand = next(
            (c for c in candidates if c['elected'] and c is not petition_winner),
            None,
        )
    else:
        # Petition winner not matched by name — fall back to disqualifying the sole original winner.
        elected = [c for c in candidates if c['elected']]
        disq_cand = elected[0] if len(elected) == 1 else None

    if not disq_cand:
        return

    disq_cand['disqualified'] = True
    disq_cand['elected'] = False
    disq_cand['notes'] = petition_note
    existing = disq_cand.get('existing_cr')
    if existing:
        if not existing.disqualified and 'disqualified' not in disq_cand['changes']:
            disq_cand['changes'].append('disqualified')
        if existing.elected and 'elected' not in disq_cand['changes']:
            disq_cand['changes'].append('elected')
        if 'notes' not in disq_cand['changes']:
            disq_cand['changes'].append('notes')

    # Mark the petition winner as elected.
    if petition_winner:
        petition_winner['elected'] = True
        existing_pw = petition_winner.get('existing_cr')
        if existing_pw and not existing_pw.elected and 'elected' not in petition_winner['changes']:
            petition_winner['changes'].append('elected')
    else:
        # No named petition winner — promote the runner-up by votes.
        others = [c for c in candidates if c is not disq_cand]
        if others:
            runner_up = max(others, key=lambda c: c['votes'] or 0)
            runner_up['elected'] = True
            existing_ru = runner_up.get('existing_cr')
            if existing_ru and not existing_ru.elected and 'elected' not in runner_up['changes']:
                runner_up['changes'].append('elected')


def _process_group(const, date_str, etype_grp, rows):
    year, month, day = parse_hop_date(date_str)

    data = {
        'date': date_str,
        'year': year,
        'etype': etype_grp,
        'election': None,
        'election_action': None,
        'election_error': None,
        'be_notes': '',
        'total_votes': 0,
        'candidates': [],
        'const_result': None,
    }

    if etype_grp == 'GE':
        if year is None:
            data['election_action'] = 'error'
            data['election_error'] = f'Could not parse date: {date_str!r}'
        else:
            election, err = find_ge(year)
            data['election'] = election
            data['election_action'] = 'found' if election else 'error'
            data['election_error'] = err
    else:
        # By-election: check for an existing one at same constituency + date
        existing_be = None
        if year and month and day:
            try:
                be_date = date_cls(year, month, day)
                existing_be = Election.objects.filter(
                    type='BE', constituency=const, date__date=be_date,
                ).first()
            except (ValueError, TypeError):
                pass
        data['election'] = existing_be
        data['election_action'] = 'found' if existing_be else 'create'
        data['be_notes'] = '; '.join(r['Notes'] for r in rows if r.get('Notes'))
        data['old_mp_name'] = _resolve_old_mp(const, rows)

    election = data['election']

    # Separate petition rows — they inform outcomes but are not candidates themselves
    petition_rows = [r for r in rows if r.get('Election Type') == 'Petition']
    candidate_rows = [r for r in rows if r.get('Election Type') != 'Petition']

    # Sum votes from candidate rows only (petition rows may repeat the same figures)
    for row in candidate_rows:
        v, _ = parse_votes(row.get('Votes', ''))
        if v:
            data['total_votes'] += v

    for row in candidate_rows:
        data['candidates'].append(
            _process_candidate(const, election, year, row, data['total_votes'])
        )

    if etype_grp == 'GE' and petition_rows:
        _apply_petition_outcomes(data['candidates'], petition_rows)

    # ConstituencyResult (GEs with votes only)
    if etype_grp == 'GE' and data['total_votes'] and election:
        existing_cr = ConstituencyResult.objects.filter(
            constituency=const, election=election
        ).first()

        # Build petition note from all rows (petition row names are useful here)
        disq_names = [r['Candidate'] for r in rows if '*' in r.get('Votes', '')]
        petition_detail = '; '.join(r['Notes'] for r in rows
                                    if r['Election Type'] == 'Petition' and r.get('Notes'))
        if disq_names:
            notes = f"Petition unseated: {', '.join(disq_names)}."
            if petition_detail:
                notes += ' ' + petition_detail
        else:
            notes = petition_detail

        data['const_result'] = {
            'existing': existing_cr,
            'action': 'update' if existing_cr else 'create',
            'total_votes': data['total_votes'],
            'notes': notes,
        }

    return data


def _process_candidate(const, election, year, row, total_votes):
    name = row['Candidate']
    hop_id = row.get('Hop ID', '')
    votes_str = row.get('Votes', '')
    et = row['Election Type']

    elected_flag = candidate_is_elected(name)
    votes, disqualified = parse_votes(votes_str)
    unopposed = not votes_str.strip() and et in ('General', 'By-election')

    percent = round(votes / total_votes * 100, 1) if (votes and total_votes) else None

    person, person_action = preview_person(hop_id, name, elected_flag)

    # No hop_id — try to find an existing Person by name similarity for party lookup
    if person is None and not hop_id:
        matched = _find_person_by_name(name)
        if matched:
            person = matched
            person_action = 'link_by_name'

    display_name = person.name if person_action in ('link', 'link_by_name') else _ROMAN_RE.sub(lambda m: m.group().upper(), name.title())

    existing_cr, match_quality = (None, None)
    if election and const:
        existing_cr, match_quality = find_matching_cr(const, election, name, elected_flag, year=year)

    party, party_source = determine_party(existing_cr, person, name=name, constituency=const)

    changes = []
    if existing_cr:
        if existing_cr.candidate.lower() != display_name.lower():
            changes.append('candidate')
        if existing_cr.votes != votes:
            changes.append('votes')
        if votes and existing_cr.percent != percent:
            changes.append('percent')
        if existing_cr.elected != elected_flag:
            changes.append('elected')
        if existing_cr.disqualified != disqualified:
            changes.append('disqualified')
        if not existing_cr.person and person_action in ('link', 'create', 'link_by_name'):
            changes.append('person')
        if not existing_cr.unopposed and unopposed:
            changes.append('unopposed')

    return {
        'row': row,
        'action': 'update' if existing_cr else 'create',
        'existing_cr': existing_cr,
        'match_quality': match_quality,
        'display_name': display_name,
        'hop_id': hop_id,
        'person': person,
        'person_action': person_action,
        'party': party,
        'party_source': party_source,
        'elected': elected_flag,
        'disqualified': disqualified,
        'unopposed': unopposed,
        'votes': votes,
        'percent': percent,
        'changes': changes,
        'notes': None,
    }


# ── Commit ────────────────────────────────────────────────────────────────────

@transaction.atomic
def commit_preview(preview):
    """Apply the proposed changes from build_preview() to the database."""
    if not preview.get('constituency'):
        return {'error': 'Constituency not found — nothing committed.'}

    const = preview['constituency']
    stats = {
        'persons_created': 0, 'crs_created': 0, 'crs_updated': 0,
        'elections_created': 0, 'const_results_created': 0, 'const_results_updated': 0,
    }
    independent = get_independent()
    created_persons = {}  # hop_id → Person, for deduplication within this commit

    for elec_data in preview['elections']:
        year = elec_data['year']
        etype = elec_data['etype']
        election = elec_data['election']

        # Create by-election object if needed
        if not election and etype == 'BE' and elec_data['election_action'] == 'create':
            _, month, day = parse_hop_date(elec_data['date'])
            try:
                be_dt = make_aware(dt(year, month or 1, day or 1))
            except (ValueError, TypeError):
                continue
            election = Election.objects.create(
                type='BE',
                date=be_dt,
                constituency=const,
                notes=elec_data.get('be_notes', ''),
                oldMP=elec_data.get('old_mp_name') or None,
            )
            stats['elections_created'] += 1
        elif election and etype == 'BE':
            old_mp = elec_data.get('old_mp_name')
            if old_mp and not election.oldMP:
                election.oldMP = old_mp
                election.save()

        if not election:
            continue

        for cand in elec_data['candidates']:
            person = cand['person']

            if cand['person_action'] == 'create' and cand['hop_id']:
                if cand['hop_id'] in created_persons:
                    person = created_persons[cand['hop_id']]
                else:
                    person = Person.objects.create(
                        name=cand['display_name'],
                        hop_id=cand['hop_id'],
                        elected=cand['elected'],
                    )
                    created_persons[cand['hop_id']] = person
                    stats['persons_created'] += 1

            party = cand['party'] or independent

            if cand['action'] == 'create':
                CandidateResult.objects.create(
                    constituency=const,
                    election=election,
                    party=party,
                    candidate=cand['display_name'],
                    person=person,
                    votes=cand['votes'],
                    percent=cand['percent'],
                    unopposed=cand['unopposed'],
                    elected=cand['elected'],
                    disqualified=cand['disqualified'],
                    notes=cand.get('notes'),
                )
                stats['crs_created'] += 1

            elif cand['action'] == 'update' and cand['changes']:
                cr = cand['existing_cr']
                for field in cand['changes']:
                    if field == 'candidate':
                        cr.candidate = cand['display_name']
                    elif field == 'votes':
                        cr.votes = cand['votes']
                    elif field == 'percent':
                        cr.percent = cand['percent']
                    elif field == 'elected':
                        cr.elected = cand['elected']
                    elif field == 'disqualified':
                        cr.disqualified = cand['disqualified']
                    elif field == 'notes':
                        cr.notes = cand['notes']
                    elif field == 'person':
                        cr.person = person
                    elif field == 'unopposed':
                        cr.unopposed = cand['unopposed']
                cr.save()
                stats['crs_updated'] += 1

        cr_data = elec_data.get('const_result')
        if cr_data:
            if cr_data['action'] == 'create':
                ConstituencyResult.objects.create(
                    constituency=const,
                    election=election,
                    turnout_votes=cr_data['total_votes'],
                    notes=cr_data['notes'],
                )
                stats['const_results_created'] += 1
            elif cr_data['action'] == 'update' and cr_data['existing']:
                obj = cr_data['existing']
                obj.turnout_votes = cr_data['total_votes']
                if cr_data['notes']:
                    obj.notes = cr_data['notes']
                obj.save()
                stats['const_results_updated'] += 1

    return stats
