from difflib import SequenceMatcher

from django.utils import timezone

from uk_elections.models import (
    APIValidationRecord, CandidateResult, ConstituencyResult,
)
from uk_elections.parliament_api import (
    ElectionResultsQuery, normalize_api_name,
)

MONTH_ABBR_TO_FULL = {
    'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
    'May': 'May',     'Jun': 'June',     'Jul': 'July',  'Aug': 'August',
    'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December',
}


def db_year_to_api_year(db_year):
    """'1974 Feb' -> 'February 1974', '1979' -> '1979'"""
    parts = str(db_year).strip().split()
    if len(parts) == 2:
        year, abbr = parts
        return f'{MONTH_ABBR_TO_FULL.get(abbr, abbr)} {year}'
    return str(db_year)


def _get_api_name(constituency, api, api_year):
    """
    Find the API name that works for this constituency in the given year.
    Tries api_names list first (they differ from the DB name), then the DB name itself.
    Returns (name, election_id) or raises ValueError if none work.
    """
    candidates = list(constituency.api_names)
    candidates.append(constituency.name)
    if constituency.alt_name:
        candidates.append(constituency.alt_name)

    for name in candidates:
        try:
            eid = api._get_election_id(api_year, name)
            return name, eid
        except ValueError:
            continue
    raise ValueError(
        f"No API match found for '{constituency.name}' in {api_year}. "
        f"Tried: {candidates}"
    )


def _names_match(api_name, db_name):
    """
    True if api_name (Surname, First format) refers to the same person as db_name (First Surname).
    Strategy: exact after normalization, then surname + first-initial, then middle-name-as-first
    (some candidates are known by a middle name rather than their registered first name),
    then high-similarity fallback.
    """
    normalized = normalize_api_name(api_name)

    if normalized.lower() == db_name.lower():
        return True

    # Extract surname and all given names from API name
    if ', ' in api_name:
        api_surname, api_first = api_name.split(', ', 1)
        api_surname = api_surname.strip()
        api_given_names = [n.strip() for n in api_first.strip().split() if n.strip()]
        api_initial = api_given_names[0][0].upper() if api_given_names else ''
    else:
        parts = api_name.strip().split()
        api_surname = parts[-1] if parts else ''
        api_given_names = parts[:-1]
        api_initial = parts[0][0].upper() if len(parts) > 1 else ''

    # Extract surname and first name from DB name (First ... Surname)
    db_parts = db_name.strip().split()
    db_surname = db_parts[-1] if db_parts else ''
    db_first = db_parts[0] if db_parts else ''
    db_initial = db_first[0].upper() if db_first else ''

    if api_surname.lower() == db_surname.lower():
        # Standard: first initial match
        if api_initial and db_initial and api_initial == db_initial:
            return True
        # Middle-name-as-given-name: DB first name matches a middle name (2nd given name onwards).
        # Only checks past the first given name to avoid false positives — the first name is
        # already handled by the initial check above.
        if db_first and len(api_given_names) > 1 and any(
            n.lower() == db_first.lower() for n in api_given_names[1:]
        ):
            return True

    # High-similarity fallback catches small typos where initials diverge
    ratio = SequenceMatcher(None, normalized.lower(), db_name.lower()).ratio()
    return ratio >= 0.88


def _name_update(api_name, db_name):
    """
    Return the new value for the DB candidate name if the API warrants an update, else None.

    Updates are applied when:
    - API has a fuller first name (DB has an initial, API has the full name)
    - Names are near-identical (ratio >= 0.88) — small typo correction
    The API is treated as authoritative; we never shorten a full name to an initial.
    """
    normalized = normalize_api_name(api_name)
    if normalized == db_name:
        return None

    api_parts = normalized.split()
    db_parts = db_name.split()
    api_surname = api_parts[-1] if api_parts else ''
    db_surname = db_parts[-1] if db_parts else ''
    api_first = ' '.join(api_parts[:-1]) if len(api_parts) > 1 else ''
    db_first = ' '.join(db_parts[:-1]) if len(db_parts) > 1 else ''

    if api_surname.lower() == db_surname.lower():
        db_stripped = db_first.rstrip('.')
        # API first name is longer and DB is a prefix/initial of it → upgrade
        if len(api_first) > len(db_first) and api_first.upper().startswith(db_stripped.upper()):
            return normalized
        # DB records only a middle name (e.g. DB "Reza Hossain" vs API "Shah Reza Hossain"):
        # single DB given name matches a non-first API given name → upgrade to full name
        if ', ' in api_name:
            _, api_given_str = api_name.split(', ', 1)
            api_given_names = [n.strip() for n in api_given_str.strip().split() if n.strip()]
        else:
            api_given_names = api_first.split()
        db_given_names = db_first.split()
        if (len(api_given_names) > 1
                and len(db_given_names) == 1
                and any(n.lower() == db_given_names[0].lower() for n in api_given_names[1:])):
            return normalized
        # Near-identical after normalisation → small typo
        ratio = SequenceMatcher(None, normalized.lower(), db_name.lower()).ratio()
        if ratio >= 0.88:
            return normalized

    return None


def compare_constituency(constituency, election):
    """
    Fetch API results for constituency+election and compare against the DB.

    Returns:
    {
      'api_name_used': str,
      'matched':      [(api_cand_dict, CandidateResult, diff_dict), ...],
      'only_in_api':  [api_cand_dict, ...],
      'only_in_db':   [CandidateResult, ...],
      'turnout_diff': (db_pct, api_pct) or None,
      'error':        str or None,
    }

    diff_dict keys: 'name' -> (old, new), 'votes' -> (db_val, api_val)
    """
    api = ElectionResultsQuery()
    api_year = db_year_to_api_year(election.year)

    try:
        api_name_used, _ = _get_api_name(constituency, api, api_year)
        api_data = api.query(api_name_used, api_year)
    except Exception as exc:
        return {'error': str(exc), 'api_name_used': None,
                'matched': [], 'only_in_api': [], 'only_in_db': [],
                'turnout_diff': None}

    db_results = list(
        CandidateResult.objects.filter(constituency=constituency, election=election)
        .select_related('party')
    )

    unmatched_db = list(db_results)
    matched = []
    only_in_api = []

    for api_cand in api_data['candidates']:
        best = None
        for db_r in unmatched_db:
            if _names_match(api_cand['api_name'], db_r.candidate):
                best = db_r
                break

        if best:
            unmatched_db.remove(best)
            diff = {}
            new_name = _name_update(api_cand['api_name'], best.candidate)
            if new_name:
                diff['name'] = (best.candidate, new_name)
            if (api_cand['votes'] is not None
                    and best.votes is not None
                    and api_cand['votes'] != best.votes):
                diff['votes'] = (best.votes, api_cand['votes'])
            matched.append((api_cand, best, diff))
        else:
            only_in_api.append(api_cand)

    # Turnout comparison
    cr = ConstituencyResult.objects.filter(
        constituency=constituency, election=election
    ).first()
    db_turnout = cr.turnout_percent if cr else None
    api_turnout = api_data['turnout_pct']
    turnout_diff = None
    if (db_turnout is not None and api_turnout is not None
            and abs(db_turnout - api_turnout) > 0.05):
        turnout_diff = (db_turnout, api_turnout)

    return {
        'api_name_used': api_name_used,
        'matched': matched,
        'only_in_api': only_in_api,
        'only_in_db': unmatched_db,
        'turnout_diff': turnout_diff,
        'error': None,
    }


def has_any_diff(comparison):
    return (comparison['only_in_api'] or comparison['only_in_db']
            or comparison['turnout_diff']
            or any(diff for _, _, diff in comparison['matched']))
