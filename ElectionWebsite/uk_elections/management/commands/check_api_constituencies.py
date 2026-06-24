import re
import html
import requests
from django.core.management.base import BaseCommand
from django.db.models import Q
from uk_elections.models import Constituency

API_URL = "https://api.parliament.uk/uk-general-elections/constituencies"


def fetch_api_names():
    resp = requests.get(API_URL)
    resp.raise_for_status()
    pairs = re.findall(
        r'href="https://api\.parliament\.uk/uk-general-elections/constituencies/\d+"[^>]*>([^<]+)<',
        resp.text
    )
    return {re.sub(r'\s*\(\d+ elections?\)$', '', html.unescape(name)).strip() for name in pairs}


def db_match(api_name):
    """Return the first Constituency that recognises api_name, or None.

    SQLite doesn't support JSONField __contains, so we search the serialised
    text for the quoted string — JSON wraps each element in double quotes, so
    '"name"' only matches an element whose value is exactly 'name'.
    """
    qs = Constituency.objects.filter(
        Q(name=api_name) |
        Q(alt_name=api_name) |
        Q(api_names__icontains=f'"{api_name}"')
    )
    return qs.first()


class Command(BaseCommand):
    help = 'Check which Parliament API constituency names are missing from the local database'

    def handle(self, *args, **kwargs):
        self.stdout.write('Fetching API constituency list...')
        api_names = fetch_api_names()
        self.stdout.write(f'  {len(api_names)} constituencies on API')

        db_names = set(Constituency.objects.values_list('name', flat=True))
        db_alt_names = set(
            Constituency.objects.exclude(alt_name__isnull=True)
                                .exclude(alt_name='')
                                .values_list('alt_name', flat=True)
        )
        self.stdout.write(f'  {len(db_names)} unique names in DB ({len(db_alt_names)} alt names)')

        matched_via_alt = []
        matched_via_api_names = []
        missing = []

        for api_name in sorted(api_names):
            if api_name in db_names:
                continue  # exact name match — nothing to report
            match = db_match(api_name)
            if match:
                if api_name in db_alt_names:
                    matched_via_alt.append((api_name, match.name))
                else:
                    matched_via_api_names.append((api_name, match.name))
            else:
                missing.append(api_name)

        self.stdout.write(f'\n--- Matched via alt_name only ({len(matched_via_alt)}) ---')
        for api_name, db_name in matched_via_alt:
            self.stdout.write(f'  API: {api_name!r:50s} -> DB: {db_name!r}')

        self.stdout.write(f'\n--- Matched via api_names field ({len(matched_via_api_names)}) ---')
        for api_name, db_name in matched_via_api_names:
            self.stdout.write(f'  API: {api_name!r:50s} -> DB: {db_name!r}')

        self.stdout.write(f'\n--- Not found anywhere ({len(missing)}) ---')
        for api_name in missing:
            self.stdout.write(f'  {api_name!r}')

        total_matched = len(api_names) - len(missing)
        self.stdout.write(
            f'\nSummary: {total_matched} matched '
            f'({len(matched_via_alt)} via alt_name, {len(matched_via_api_names)} via api_names), '
            f'{len(missing)} missing'
        )
