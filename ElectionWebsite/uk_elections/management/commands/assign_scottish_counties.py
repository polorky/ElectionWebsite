"""
Management command: assign_scottish_counties

1. Creates all Scottish council areas as County objects (Region=Scotland).
2. For every election GeoJSON file (newest first), finds Scottish constituencies
   and works out which modern counties they overlap with.
3. Assigns any county whose area makes up >= MIN_OVERLAP_PCT% of a constituency
   as a modern_county on the Constituency object.

Run with:
    python manage.py assign_scottish_counties [--min-overlap 10] [--dry-run]
"""

import json
import os

from django.core.management.base import BaseCommand
from shapely.geometry import shape
from shapely.validation import make_valid

from uk_elections.models import County, Constituency, Election, Region
from uk_elections.constants import GEOJSON_NAME_MAP

COUNTIES_GEOJSON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'Data', 'geojson', 'modern_counties.geojson')
)
STATIC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'static')
)


class Command(BaseCommand):
    help = 'Create Scottish counties and assign them to Scottish constituencies via GeoJSON overlap'

    def add_arguments(self, parser):
        parser.add_argument('--min-overlap', type=float, default=10.0,
                            help='Minimum %% of constituency area a county must cover to be assigned (default 10)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print what would change without writing to the database')

    def handle(self, *args, **options):
        min_pct = options['min_overlap'] / 100.0
        dry_run = options['dry_run']

        # ── Step 1: load Scottish county geometries from modern_counties.geojson ──
        self.stdout.write('Loading modern_counties.geojson …')
        with open(COUNTIES_GEOJSON) as f:
            counties_gj = json.load(f)

        scottish_county_geoms = {}   # county_name → shapely geometry
        for feat in counties_gj['features']:
            if feat['properties']['areacd'].startswith('S'):
                name = feat['properties']['areanm']
                geom = make_valid(shape(feat['geometry']))
                scottish_county_geoms[name] = geom

        self.stdout.write(f'  Found {len(scottish_county_geoms)} Scottish council areas')

        # ── Step 2: create County DB records ──
        scotland_region = Region.objects.get(name='Scotland')
        created_count = 0
        county_objs = {}   # name → County instance
        for name in sorted(scottish_county_geoms):
            obj, created = County.objects.get_or_create(
                name=name,
                defaults={'region': scotland_region}
            )
            if created:
                created_count += 1
                if not dry_run:
                    pass  # already saved by get_or_create
                self.stdout.write(f'  Created county: {name}')
            county_objs[name] = obj

        self.stdout.write(f'Counties created: {created_count}, already existing: {len(scottish_county_geoms) - created_count}')

        # ── Step 3: iterate GeoJSON files newest → oldest, assign counties ──
        elections = (Election.objects
                     .filter(type='GE', gj__isnull=False)
                     .exclude(gj='')
                     .order_by('-date'))

        # Collect unique GeoJSON filenames in newest-first order
        seen_files = set()
        gj_files = []
        for elec in elections:
            if elec.gj not in seen_files:
                seen_files.add(elec.gj)
                gj_files.append(elec.gj)

        processed = set()   # constituency names already handled
        assignments = {}    # const_name → [county_name, …]

        for gj_filename in gj_files:
            path = os.path.join(STATIC_DIR, gj_filename)
            if not os.path.exists(path):
                self.stdout.write(self.style.WARNING(f'  File not found: {gj_filename}, skipping'))
                continue

            self.stdout.write(f'Processing {gj_filename} …')
            with open(path) as f:
                gj = json.load(f)

            for feat in gj['features']:
                props = feat.get('properties', {})
                raw_name = props.get('Name') or props.get('name', '')
                const_name = GEOJSON_NAME_MAP.get(raw_name, raw_name)

                if not const_name or const_name in processed:
                    continue

                # Only process if there are matching Constituency DB records
                const_objs = list(Constituency.objects.filter(name=const_name))
                if not const_objs:
                    continue

                # Build constituency geometry
                try:
                    const_geom = make_valid(shape(feat['geometry']))
                except Exception:
                    continue

                const_area = const_geom.area
                if const_area == 0:
                    continue

                # Check overlap with each Scottish county
                matched_counties = []
                for county_name, county_geom in scottish_county_geoms.items():
                    try:
                        intersection = const_geom.intersection(county_geom)
                    except Exception:
                        continue
                    overlap_pct = intersection.area / const_area
                    if overlap_pct >= min_pct:
                        matched_counties.append((county_name, overlap_pct))

                if not matched_counties:
                    continue

                matched_counties.sort(key=lambda x: x[1], reverse=True)
                assignments[const_name] = matched_counties
                processed.add(const_name)

        # ── Step 4: apply assignments ──
        self.stdout.write('\nAssigning counties to constituencies:')
        assigned_consts = 0
        for const_name, county_overlaps in sorted(assignments.items()):
            const_objs = list(Constituency.objects.filter(name=const_name))
            county_names = [cn for cn, _ in county_overlaps]
            pct_strs = ', '.join(f'{cn} ({pct*100:.0f}%)' for cn, pct in county_overlaps)
            self.stdout.write(f'  {const_name}: {pct_strs}')

            if not dry_run:
                for const_obj in const_objs:
                    for county_name in county_names:
                        const_obj.modern_county.add(county_objs[county_name])
            assigned_consts += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {"[DRY RUN] Would have assigned" if dry_run else "Assigned"} '
            f'counties to {assigned_consts} constituencies across '
            f'{len(processed)} unique names processed.'
        ))
