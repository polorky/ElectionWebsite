import json
import os
from django.core.management.base import BaseCommand
from staticmap import StaticMap, Polygon
from uk_elections.constants import GEOJSON_NAME_MAP

MAP_WIDTH = 200
MAP_HEIGHT = 230
MAP_PADDING = 12

FILL_COLOR = '#5b82b859'    # #5b82b8 at ~35% opacity
OUTLINE_COLOR = '#3a5f8a'


def _add_geometry(m, geometry):
    """Add all rings of a GeoJSON geometry as Polygon overlays to a StaticMap."""
    t = geometry['type']
    if t == 'Polygon':
        for ring in geometry['coordinates']:
            coords = [(lon, lat) for lon, lat in ring]
            m.add_polygon(Polygon(coords, FILL_COLOR, OUTLINE_COLOR))
    elif t == 'MultiPolygon':
        for poly in geometry['coordinates']:
            for ring in poly:
                coords = [(lon, lat) for lon, lat in ring]
                m.add_polygon(Polygon(coords, FILL_COLOR, OUTLINE_COLOR))


# Process newest first so a constituency that changed boundaries gets its most recent shape.
GEOJSON_FILES = [
    '2024.geojson',
    '2010-2019.geojson',
    '2005.geojson',
    '2001.geojson',
    '1997.geojson',
    '1992.geojson',
    '1983-1987.geojson',
    '1974-1979.geojson',
    '1955-1970.geojson',
    '1950-1951.geojson',
    '1945.geojson',
    '1922-1935.geojson',
    '1918.geojson',
    '1885-1910.geojson',
]


class Command(BaseCommand):
    help = 'Pre-generate PNG constituency map thumbnails (OSM tiles + boundary overlay).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-existing', action='store_true',
            help='Skip constituencies that already have a PNG file.'
        )

    def handle(self, *args, **options):
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        static_dir = os.path.join(app_dir, 'static')
        maps_dir = os.path.join(static_dir, 'uk_elections', 'constituency_maps')
        os.makedirs(maps_dir, exist_ok=True)

        skip_existing = options['skip_existing']

        # Collect geometry per constituency name (newest file wins)
        seen = set()
        queue = []   # list of (name, geometry)

        for gj_filename in GEOJSON_FILES:
            file_path = os.path.join(static_dir, gj_filename)
            if not os.path.exists(file_path):
                self.stdout.write(self.style.WARNING(f'  Missing: {gj_filename}'))
                continue

            with open(file_path, encoding='utf-8') as f:
                gj = json.load(f)

            for feature in gj.get('features', []):
                props = feature.get('properties', {})
                raw_name = props.get('name') or props.get('Name', '')
                if not raw_name:
                    continue
                name = GEOJSON_NAME_MAP.get(raw_name, raw_name)
                if name in seen:
                    continue
                geometry = feature.get('geometry')
                if not geometry or not geometry.get('coordinates'):
                    continue
                seen.add(name)
                queue.append((name, geometry))

        total = len(queue)
        generated = 0
        skipped = 0
        errors = 0

        for i, (name, geometry) in enumerate(queue, 1):
            out_path = os.path.join(maps_dir, f'{name}.png')

            if skip_existing and os.path.exists(out_path):
                skipped += 1
                continue

            try:
                m = StaticMap(MAP_WIDTH, MAP_HEIGHT, padding_x=MAP_PADDING, padding_y=MAP_PADDING)
                _add_geometry(m, geometry)
                image = m.render()
                image.save(out_path)
                generated += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  [{i}/{total}] ERROR {name}: {e}'))
                errors += 1
                continue

            if i % 50 == 0 or i == total:
                self.stdout.write(f'  {i}/{total} done...')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Generated: {generated}  Skipped: {skipped}  Errors: {errors}'
        ))
        self.stdout.write(f'PNGs saved to: {maps_dir}')
