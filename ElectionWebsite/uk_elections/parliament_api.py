import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://api.parliament.uk/uk-general-elections"


def normalize_api_name(api_name):
    """'Critchley, Julian' -> 'Julian Critchley'"""
    if ', ' in api_name:
        surname, firstnames = api_name.split(', ', 1)
        return f'{firstnames.strip()} {surname.strip()}'
    return api_name.strip()


def _parse_votes(votes_str):
    try:
        return int(votes_str.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


class ParliamentAPIBase:

    def __init__(self):
        self.session = requests.Session()
        self._ge_year_to_id = {}
        self._ge_constituency_to_election_id = {}

    def _get(self, url):
        time.sleep(0.1)
        resp = self.session.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    def _load_ge_index(self):
        if self._ge_year_to_id:
            return
        soup = self._get(f"{BASE_URL}/general-elections")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/general-elections/" in href and href.split("/")[-1].isdigit():
                # "February 1974 General Election" -> "February 1974"
                # "1979 General Election" -> "1979"
                key = a.get_text(strip=True).replace("General Election", "").strip()
                if key:
                    self._ge_year_to_id[key] = href.split("/")[-1]

    def _load_ge_constituencies(self, ge_id):
        if ge_id in self._ge_constituency_to_election_id:
            return
        soup = self._get(f"{BASE_URL}/general-elections/{ge_id}")
        links = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/elections/" in href and "/general-elections/" not in href:
                election_id = href.split("/")[-1]
                name = a.get_text(strip=True)
                if name:
                    links[name] = election_id
        self._ge_constituency_to_election_id[ge_id] = links

    def _get_election_id(self, year, constituency_name):
        self._load_ge_index()
        ge_id = self._ge_year_to_id.get(str(year))
        if not ge_id:
            raise ValueError(f"Year {year} not found in Parliament API")
        self._load_ge_constituencies(ge_id)
        election_id = self._ge_constituency_to_election_id[ge_id].get(constituency_name)
        if not election_id:
            raise ValueError(f"Constituency '{constituency_name}' not found in {year} General Election")
        return election_id

    def query(self, **kwargs):
        raise NotImplementedError


class ElectionResultsQuery(ParliamentAPIBase):
    """Fetch all candidate results for a constituency+election."""

    def query(self, constituency_name, api_year):
        """
        Returns:
          {
            'turnout_pct': float or None,
            'candidates': [{'api_name': str, 'party': str, 'votes': int or None}, ...]
          }
        Candidates are ordered by votes descending (winner first), as the API lists them.
        """
        election_id = self._get_election_id(api_year, constituency_name)
        soup = self._get(f"{BASE_URL}/elections/{election_id}")

        result = {'turnout_pct': None, 'candidates': []}
        tables = soup.find_all('table')

        if tables:
            for row in tables[0].find_all('tr'):
                cells = [td.get_text(strip=True) for td in row.find_all('td')]
                if len(cells) == 2 and cells[0] == 'Turnout':
                    try:
                        result['turnout_pct'] = float(cells[1].rstrip('%'))
                    except ValueError:
                        pass

        if len(tables) > 1:
            for row in tables[1].find_all('tr')[1:]:  # skip header
                cells = [td.get_text(strip=True) for td in row.find_all('td')]
                if len(cells) >= 2:
                    result['candidates'].append({
                        'api_name': cells[0],
                        'party': cells[1] if len(cells) > 1 else '',
                        'votes': _parse_votes(cells[2]) if len(cells) > 2 else None,
                    })

        return result


class TurnoutQuery(ParliamentAPIBase):

    RESULT_COLUMN = "API Turnout"

    def query(self, constituency_name, year):
        election_id = self._get_election_id(year, constituency_name)
        soup = self._get(f"{BASE_URL}/elections/{election_id}")
        for row in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) == 2 and cells[0] == "Turnout":
                return cells[1]
        raise ValueError(f"Turnout not found for '{constituency_name}' {year}")
