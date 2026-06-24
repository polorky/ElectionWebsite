import re
import html
import requests
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db.models import Q
from uk_elections.models import Constituency

API_URL = "https://api.parliament.uk/uk-general-elections/constituencies"

# Explicit mappings: API name -> DB name
# Where a DB constituency has multiple API names, each API name appears as its own key
# pointing to the same DB name — the command collects them into one list before writing.
EXPLICIT = {
    # Welsh spelling
    'Caernarvon':                               'Caernarfon',
    'Caernarvon Boroughs':                      'Caernarfon',
    'Llanelly':                                 'Llanelli',
    # Hyphenation
    'Barrow in Furness':                        'Barrow-in-Furness',
    'Newcastle upon Tyne':                      'Newcastle-upon-Tyne',
    # Suffix/abbreviation differences
    'Richmond (Yorks)':                         'Richmond (Yorkshire)',
    'Kinross and Western Perthshire':           'Kinross and West Perthshire',
    'Clackmannan and East Stirlingshire':       'Clackmannan and Eastern Stirlingshire',
    'West Newington':                           'Newington West',
    'East MIddlesbrough':                       'Middlesbrough East',
    'Durham':                                   'City of Durham',
    'Stoke':                                    'Stoke-on-Trent',
    'Gorton':                                   'Manchester Gorton',
    'Southgate':                                'Enfield Southgate',
    'Wellington':                               'Wellington (Shropshire)',
    'Pembroke Boroughs':                        'Pembroke',
    # University seats
    'Aberdeen and Glasgow Universities':        'Glasgow and Aberdeen Universities',
    "Edinburgh and St Andrew's Universities":   'Edinburgh and St Andrews Universities',
    # Compound names with reversed word order
    'Maldon and East Chelmsford':               'Maldon and Chelmsford East',
    'South Colchester and Maldon':              'Colchester South and Maldon',
    'Peebles and South Midlothian':             'Midlothian and Peebles Southern',
    # Aberdeen/Kincardine — API drops "-shire"
    'Central Aberdeen and Kincardine':          'Central Aberdeenshire and Kincardineshire',
    'East Aberdeen and Kincardine':             'East Aberdeenshire and Kincardineshire',
    'West Aberdeen and Kincardine':             'West Aberdeenshire and Kincardineshire',
    # Irish — API uses plain name, DB prefixes "County"
    'Cork':                                     'County Cork',
    'Dublin':                                   'County Dublin',
    'Kilkenny':                                 'County Kilkenny',
    'Limerick':                                 'County Limerick',
    'Sligo':                                    'County Sligo',
    'Waterford':                                'County Waterford',
    'Westmeath':                                'County Westmeath',
    'Wexford':                                  'County Wexford',
    # Irish — API says "City", DB says "Borough"
    'Galway City':                              'Galway Borough',
    # Irish — API inserts "County" in sub-division names
    'North County Dublin':                      'North Dublin',
    'South County Dublin':                      'South Dublin',
    # Irish — API says City, DB uses the plain county name
    'Carlow City':                              'Carlow',
    # Compound names with "and" — direction reversal doesn't handle these
    'East Newcastle upon Tyne and Wallsend':    'Newcastle upon Tyne East and Wallsend',
    'North Southwark and Bermondsey':           'Southwark North and Bermondsey',
    'South Middlesbrough and East Cleveland':   'Middlesbrough South and East Cleveland',
    'West Kingston upon Hull and Hessle':       'Kingston upon Hull Haltemprice',
    # Other
    'Cotswold':                                 'The Cotswolds',
}

DIRECTIONS = ['North West', 'South West', 'North East', 'South East',
              'Central', 'North', 'South', 'East', 'West']


def reverse_direction(name):
    """'East Foo Bar' -> 'Foo Bar East', 'North West Foo' -> 'Foo North West'."""
    for direction in DIRECTIONS:
        prefix = direction + ' '
        if name.startswith(prefix):
            return name[len(prefix):] + ' ' + direction
    return None


def fetch_api_names():
    resp = requests.get(API_URL)
    resp.raise_for_status()
    pairs = re.findall(
        r'href="https://api\.parliament\.uk/uk-general-elections/constituencies/\d+"[^>]*>([^<]+)<',
        resp.text,
    )
    return {re.sub(r'\s*\(\d+ elections?\)$', '', html.unescape(p)).strip() for p in pairs}


class Command(BaseCommand):
    help = 'Set api_names on Constituency records where the API uses a different name'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be set without writing to DB')

    def handle(self, *args, **kwargs):
        dry_run = kwargs['dry_run']
        if dry_run:
            self.stdout.write('DRY RUN — no changes will be saved\n')

        self.stdout.write('Fetching API constituency list...')
        api_names = fetch_api_names()
        self.stdout.write(f'  {len(api_names)} constituencies on API\n')

        already_matched = set()
        # db_name -> [api_names that map to it]
        db_to_api = defaultdict(list)
        unmatched = []

        for api_name in sorted(api_names):
            # Already matched via name or alt_name — no entry needed
            if Constituency.objects.filter(Q(name=api_name) | Q(alt_name=api_name)).exists():
                already_matched.add(api_name)
                continue

            db_name = EXPLICIT.get(api_name)

            if db_name is None:
                reversed_name = reverse_direction(api_name)
                if reversed_name and Constituency.objects.filter(name=reversed_name).exists():
                    db_name = reversed_name

            if db_name is not None:
                if Constituency.objects.filter(name=db_name).exists():
                    db_to_api[db_name].append(api_name)
                else:
                    unmatched.append((api_name, f'EXPLICIT target not in DB: {db_name!r}'))
            else:
                unmatched.append((api_name, ''))

        # Apply updates — one per DB name so lists are written atomically
        assigned = []
        for db_name in sorted(db_to_api):
            api_names_list = sorted(db_to_api[db_name])
            qs = Constituency.objects.filter(name=db_name)
            assigned.append((api_names_list, db_name, qs.count()))
            if not dry_run:
                qs.update(api_names=api_names_list)

        self.stdout.write(f'\n--- Assigned ({len(assigned)} DB constituencies) ---')
        for api_names_list, db_name, count in assigned:
            api_str = ', '.join(f'{n!r}' for n in api_names_list)
            self.stdout.write(f'  [{api_str}]  ->  {db_name!r} ({count} record(s))')

        self.stdout.write(f'\n--- Unmatched ({len(unmatched)}) — need manual api_names ---')
        for api_name, note in unmatched:
            suffix = f'  [{note}]' if note else ''
            self.stdout.write(f'  {api_name!r}{suffix}')

        self.stdout.write(
            f'\nSummary: {len(already_matched)} already matched via name/alt_name, '
            f'{len(assigned)} DB constituencies assigned, {len(unmatched)} still unmatched'
        )
