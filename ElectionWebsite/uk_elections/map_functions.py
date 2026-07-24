from .models import Party, Constituency, Election, CandidateResult
from .constants import BOKEH_DISPLAY_TEXT, GEOJSON_NAME_MAP, DISENFRANCHISED_CONSTITUENCIES

import numpy as np
from collections import defaultdict
from matplotlib.patches import RegularPolygon
from django.db.models import Count
from bokeh.models import TapTool, CustomJS, ColumnDataSource, Toggle
from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.layouts import column
import pickle, os, geojson, json
from shapely.geometry import box, Polygon, MultiPolygon
from shapely.validation import make_valid

# Construct path to app's static directory
app_static_dir = os.path.join(os.path.dirname(__file__), 'static')

class ElectionMap():

    def __init__(self, request, election, map_type):
        self.electionObj = Election.objects.get(year=election, type='GE')
        self.map_type = map_type
        self.context = {'pageview':'results',
                        'election': self.electionObj,
                        'main_parties': get_main_parties(self.electionObj)}
        self.get_adjacents()
        self.get_overall_results()
        if map_type != 'results':
            self.context['pageview'] = 'hex' if map_type == 'hex' else ('gj' if map_type == 'gj' else 'map')
            names, xs, ys = self.get_base_data()
            results = get_results(names, election)
            selected_party, colours, split_colours, all_seat_colours, pct_map = resolve_party_mode(names, results, self.electionObj, request.GET.get('party'), is_hex=(self.map_type == 'hex'))
            line_colours = ['black'] * len(names)
            if self.map_type == 'gj':
                names, xs, ys, colours, line_colours, results = expand_split_seats(names, xs, ys, colours, split_colours, results)
            elif self.map_type == 'map' and selected_party is None:
                names, xs, ys, colours, line_colours, results = expand_multi_seats(names, xs, ys, all_seat_colours, results)
            disfranchised_set = set(DISENFRANCHISED_CONSTITUENCIES.get(election, []))
            disenfranchised = []
            for i, n in enumerate(names):
                if n in disfranchised_set:
                    colours[i] = '#aaaaaa'
                    disenfranchised.append(True)
                else:
                    disenfranchised.append(False)
            pcts, tooltips = build_pcts_and_tooltips(names, pct_map, selected_party)
            cds = ColumnDataSource(dict(x=xs, y=ys, name=names, colours=colours, line_colours=line_colours, results=results, pct=pcts, disenfranchised=disenfranchised))
            p = self.create_figure(tooltips)
            patch_renderer = self.get_patch_renderer(p, cds)
            self.context['uni_results'] = [] if self.map_type == 'hex' else get_university_results(election)
            tile = getattr(self, '_tile_renderer', None)
            self.context['script'], self.context['div'] = wire_map_layout(p, patch_renderer, cds, election, tile)
            self.context['selected_party'] = selected_party

    def get_adjacents(self):
        # Get all general elections
        all_elections = list(Election.objects.filter(type='GE').order_by('-date'))

        index = all_elections.index(self.electionObj)

        # all_elections is ordered -date (newest first)
        # so index+1 = older = "Previous" and index-1 = newer = "Next"
        self.context['next'] = all_elections[index - 1] if index > 0 else None
        self.context['last'] = all_elections[index + 1] if index < len(all_elections) - 1 else None

    def get_overall_results(self):
        # Get all parties and colours
        parties = Party.objects.all()
        colours = {p.name:p.colour for p in parties}

        # Get all candidate results
        cand_results = CandidateResult.objects.filter(election=self.electionObj, elected=True).order_by('constituency__name')

        # Set defaults
        overall_results = {}
        const_results = []

        # Iterate over candidate results
        for result in cand_results:
            if result.party.name in overall_results:
                overall_results[result.party.name] += 1
            else:
                overall_results[result.party.name] = 1
            res_dict = {'Constituency':result.constituency.name,
                        'Party':result.party.name,
                        'Colour':colours[result.party.name],
                        'Candidate':result.candidate,
                        'Votes':result.votes,
                        'Percent':result.percent}
            const_results.append(res_dict)

        overall_results = [(k,overall_results[k],colours[k]) for k in overall_results.keys()]
        overall_results.sort(key=lambda x: x[1], reverse=True)
        self.context['overall_results'] = overall_results
        self.context['const_results'] = const_results

    def get_base_data(self):

        if self.map_type == 'gj':

            file_path = os.path.join(app_static_dir, self.electionObj.gj)
            with open(file_path) as f:
                gj = geojson.load(f)
            
            return process_geojson(gj)
        
        elif self.map_type == 'map':

            file_path = os.path.join(app_static_dir, 'uk_svg_data_ws')
            with open(file_path, "rb") as f:
                svgs = pickle.load(f)

            svg_dict = svgs[self.electionObj.map]
            names = [GEOJSON_NAME_MAP.get(n, n) for n in svg_dict['names']]
            
            return names, svg_dict['xs'], svg_dict['ys']
        
        elif self.map_type == 'hex':

            hex_col = self.electionObj.hex
            file_path = os.path.join(app_static_dir, 'uk_hex_data_ws')
            with open(file_path, "rb") as f:
                hex_df = pickle.load(f)
            hex_df = hex_df[hex_df[hex_col] != ""]

            names = list(hex_df['Constituency'])
            xs, ys = get_hex_coords(list(hex_df[hex_col]))

            return names, xs, ys

    def create_figure(self, tooltips):

        tools = "pan,wheel_zoom,reset,save"

        if self.map_type == 'gj':

            p = figure(x_range=(-900000, 300000), y_range=(6300000, 8600000),
                       x_axis_type="mercator", y_axis_type="mercator",
                       tools=tools, tooltips=tooltips,
                       sizing_mode="stretch_width", aspect_ratio=0.6)
            
            self._tile_renderer = p.add_tile('OpenStreetMap Mapnik')

        elif self.map_type == 'map':

            p = figure(x_axis_location=None, y_axis_location=None,
                       tools=tools, tooltips=tooltips,
                       sizing_mode="stretch_width", aspect_ratio=0.5,)
            
        elif self.map_type == 'hex':

            p = figure(x_axis_location=None, y_axis_location=None,
                       tools=tools, tooltips=tooltips, 
                       sizing_mode="stretch_width", aspect_ratio=1)
    
        p.background_fill_color = None
        p.border_fill_color = None
        p.grid.grid_line_color = None
        #p.outline_line_color = None (hex,map)
        p.hover.point_policy = "follow_mouse"

        return p

    def get_patch_renderer(self, p, cds):

        if self.map_type == 'gj':
            patch_renderer = p.multi_polygons(xs='x', ys='y', source=cds,
                                    fill_color='colours', fill_alpha=0.7,
                                    line_color='line_colours', line_width=0.5)
        elif self.map_type == 'map':
            patch_renderer = p.multi_polygons(xs="x", ys="y", source=cds,
                                    fill_color="colours", name="names",
                                    line_color='black', line_width=1)
        elif self.map_type == 'hex':
            patch_renderer = p.patches(xs='x', ys='y', source=cds,
                                    fill_color="colours", fill_alpha=0.7,
                                    line_color="white", line_width=0.5)

        return patch_renderer

def get_colours(consts, election, mode='party'):

    colours = []

    if mode[:2] == 'SP':

            party = mode[2:]
            coalition = ''
            if Party.party_list[party].coalition != '':
                coalition = Party.party_list[party].coalition

            if party in Party.party_list and Party.party_list[party].colour_scale != []:
                colour_scale = Party.party_list[party].colour_scale
            else:
                colour_scale = ['#403943','#5F5763','#7F7484','#A199A5','#C4BEC6']

            percents = []

            for const in consts:
                if const not in Constituency.const_list.keys():
                    try:
                        const_obj = Constituency.previous_list[const]
                    except:
                        raise Exception('Constituency not in database',const,election)
                else:
                    const_obj = Constituency.const_list[const]
                df = const_obj.election_list[election].results
                if party in list(df.Party):
                    percent_series = df.loc[df['Party'] == party, 'Percent']
                    if percent_series[percent_series.index[0]] != '':
                        percents.append(percent_series[percent_series.index[0]])

            arrays = np.array_split(sorted(percents,reverse=True),5)

            const_count = 0
            colour_count = 0
            for const in consts:
                if const not in Constituency.const_list.keys():
                    try:
                        const_obj = Constituency.previous_list[const]
                    except:
                        raise Exception('Constituency not in database',const,election)
                else:
                    const_obj = Constituency.const_list[const]
                df = const_obj.election_list[election].results
                if party in list(df.Party):
                    percent_series = df.loc[df['Party'] == party, 'Percent']
                    percent = percent_series[percent_series.index[0]]
                    count = 0
                    for array in arrays:
                        if percent in array:
                            colour_count += 1
                            colours.append(colour_scale[count])
                            break
                        count += 1
                else:
                    colours.append('#C3C4BE')
                const_count += 1
                #print(const_count,colour_count,end=':')
                #if colour_count > 650:
                    #print(const)

            return colours

    electionObj = Election.objects.get(year=election, type='GE')
    qs = (CandidateResult.objects
          .filter(election=electionObj, elected=True)
          .select_related('party', 'constituency')
          .order_by('constituency__start_date'))
    winner_map = {}
    for r in qs:
        winner_map[r.constituency.name] = r.party.colour
    return [winner_map.get(name, '#cccccc') for name in consts]

def get_party_vote_colours(consts, electionObj, party):
    """
    Returns (colours, pct_map) for a quintile colour-scale map of a party's
    vote percentage.  Constituencies where the party didn't stand get grey.
    colour_scale runs darkest (highest %) → lightest (lowest %).
    """
    colour_scale = [c.strip() for c in party.cScale.split(',')] if party.cScale else [
        '#403943', '#5F5763', '#7F7484', '#A199A5', '#C4BEC6'
    ]
    qs = (CandidateResult.objects
          .filter(election=electionObj, party=party)
          .select_related('constituency'))
    pct_map = {r.constituency.name: r.percent for r in qs if r.percent is not None}

    if pct_map:
        sorted_pcts = sorted(pct_map.values(), reverse=True)
        quintiles = np.array_split(sorted_pcts, len(colour_scale))
        # minimum value in each group — used as lower cutoff (groups are desc)
        cutoffs = [float(arr[-1]) for arr in quintiles if len(arr) > 0]
    else:
        cutoffs = []

    colours = []
    for name in consts:
        pct = pct_map.get(name)
        if pct is None:
            colours.append('#cccccc')
        else:
            colour_idx = len(colour_scale) - 1  # default: lowest quintile
            for i, cutoff in enumerate(cutoffs):
                if pct >= cutoff:
                    colour_idx = i
                    break
            colours.append(colour_scale[colour_idx])

    return colours, pct_map

def get_results(consts, election):
    electionObj = Election.objects.get(year=election, type='GE')
    qs = (CandidateResult.objects
          .filter(election=electionObj)
          .select_related('party', 'constituency')
          .order_by('constituency__name', '-votes'))
    results_by_const = defaultdict(
        lambda: {'Party Colour': [], 'Party': [], 'Candidate': [], 'Votes': [], 'Percent': [], 'Elected': []}
    )
    for r in qs:
        d = results_by_const[r.constituency.name]
        d['Party Colour'].append(r.party.colour)
        d['Party'].append(r.party.name)
        d['Candidate'].append(r.candidate)
        d['Votes'].append(r.votes)
        d['Percent'].append(r.percent)
        d['Elected'].append(r.elected)
    return [results_by_const[name] for name in consts]

def get_hex_coords(hex_coords):

    final_coords = []
    for hex_string in hex_coords:
        hex_split = hex_string.split(',')
        hex_split = [int(x) for x in hex_split]
        final_coords.append(hex_split)

    # Horizontal cartesian coords
    hcoord_n = [c[0] for c in final_coords]
    # Vertical cartersian coords
    vcoord_n = [2. * np.sin(np.radians(60)) * (c[1] - c[2]) /3. for c in final_coords]

    x_list = []
    y_list = []
    for i in range(0,len(hcoord_n)):
        hex1 = RegularPolygon((hcoord_n[i], vcoord_n[i]), numVertices=6, radius=2. / 3.,orientation=np.radians(30))
        points = hex1.get_verts().tolist()
        x_list.append([m[0] for m in points])
        y_list.append([m[1] for m in points])

    return x_list, y_list

def hex_to_rgb(hex):
  return tuple(int(hex[i:i+2], 16) for i in (0, 2, 4))

def wgs84_to_webmercator(lon, lat):
    """Convert WGS84 degrees to Web Mercator (EPSG:3857) metres."""
    x = lon * 20037508.342789244 / 180.0
    y = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * 20037508.342789244 / np.pi
    return x, y

def get_main_parties(electionObj):
    return list(
        Party.objects.filter(candidateresult__election=electionObj)
        .exclude(cScale='')
        .annotate(n=Count('candidateresult'))
        .filter(n__gte=30)
        .order_by('-n')
    )

def get_winner_colours(results, names=None):
    """Returns (fill_colours, split_colours, all_seat_colours).
    fill_colours:     primary (first) winner colour per entry.
    split_colours:    second-winner colour or None (used by expand_split_seats for gj).
    all_seat_colours: one colour per elected seat, ordered by votes desc, with repeats
                      (e.g. Con wins 3 seats, Lib wins 1 → [Con,Con,Con,Lib]).
                      Used by expand_multi_seats for the SVG map.
    If names is provided (hex mode), assigns unique[N] to the Nth occurrence of each name
    so that split multi-seat hex pairs show different party colours."""
    fill_colours, split_colours, all_seat_colours = [], [], []
    name_count = {} if names is not None else None
    for i, r in enumerate(results):
        elected_colours = [c for c, e in zip(r['Party Colour'], r['Elected']) if e]
        unique = list(dict.fromkeys(elected_colours))
        all_seat_colours.append(elected_colours)
        if name_count is not None:
            name = names[i]
            occ = name_count.get(name, 0)
            name_count[name] = occ + 1
            idx = min(occ, len(unique) - 1) if unique else 0
            fill_colours.append(unique[idx] if unique else '#cccccc')
            split_colours.append(unique[1] if len(unique) >= 2 and occ == 0 else None)
        elif len(unique) >= 2:
            fill_colours.append(unique[0])
            split_colours.append(unique[1])
        else:
            fill_colours.append(unique[0] if unique else '#cccccc')
            split_colours.append(None)
    return fill_colours, split_colours, all_seat_colours

def resolve_party_mode(names, results, electionObj, party_pk, is_hex=False):
    """Returns (selected_party, colours, split_colours, all_seat_colours, pct_map).
    is_hex=True assigns unique[N] colours to the Nth hex of a multi-seat constituency."""
    selected_party = None
    pct_map = {}
    if party_pk:
        try:
            selected_party = Party.objects.get(pk=party_pk)
            colours, pct_map = get_party_vote_colours(names, electionObj, selected_party)
            split_colours = [None] * len(colours)
            all_seat_colours = [[c] for c in colours]
        except Party.DoesNotExist:
            colours, split_colours, all_seat_colours = get_winner_colours(results, names if is_hex else None)
    else:
        colours, split_colours, all_seat_colours = get_winner_colours(results, names if is_hex else None)
    return selected_party, colours, split_colours, all_seat_colours, pct_map

def build_pcts_and_tooltips(names, pct_map, selected_party):
    pcts = [f"{pct_map[n]:.1f}%" if n in pct_map else "Did not stand" for n in names]
    tooltips = (
        [("Name", "@name"), (selected_party.name + " %", "@pct")]
        if selected_party else [("Name", "@name")]
    )
    return pcts, tooltips

def wire_map_layout(p, patch_renderer, cds, election, tile_renderer=None):
    """Adds TapTool + click callback, returns (script, div)."""
    p.add_tools(TapTool(renderers=[patch_renderer]))
    cds.selected.js_on_change('indices', CustomJS(
        args=dict(cds=cds, election=election),
        code=BOKEH_DISPLAY_TEXT,
    ))
    if tile_renderer is not None:
        toggle = Toggle(label="Hide base map", button_type="light", active=False, width=140)
        toggle.js_on_click(CustomJS(args=dict(tile=tile_renderer), code="""
            tile.visible = !cb_obj.active;
        """))
        return components(column(toggle, p, sizing_mode="stretch_width"))
    return components(p)

def _xs_ys_to_shapely(x, y):
    """Convert multi_polygons xs/ys entry back to a Shapely geometry.
    Ring 0 of each polygon entry is the exterior; rings 1+ are interior holes."""
    parts = []
    for p_idx in range(len(x)):
        if not x[p_idx]:
            continue
        ext = list(zip(x[p_idx][0], y[p_idx][0]))
        if len(ext) < 3:
            continue
        holes = [
            list(zip(x[p_idx][r], y[p_idx][r]))
            for r in range(1, len(x[p_idx]))
            if len(x[p_idx][r]) >= 3
        ]
        try:
            parts.append(Polygon(ext, holes))
        except Exception:
            parts.append(Polygon(ext))
    if not parts:
        return None
    return make_valid(MultiPolygon(parts) if len(parts) > 1 else parts[0])

def _shapely_to_xs_ys(geom):
    """Convert a Shapely geometry to multi_polygons xs/ys entry.
    Interior rings (holes) are preserved so that borough cutouts in county
    polygons survive the split operation."""
    xs, ys = [], []
    polys = [geom] if geom.geom_type == 'Polygon' else (
        list(geom.geoms) if geom.geom_type == 'MultiPolygon' else []
    )
    for poly in polys:
        rings_x = [[c[0] for c in poly.exterior.coords]]
        rings_y = [[c[1] for c in poly.exterior.coords]]
        for interior in poly.interiors:
            rings_x.append([c[0] for c in interior.coords])
            rings_y.append([c[1] for c in interior.coords])
        xs.append(rings_x)
        ys.append(rings_y)
    return xs, ys

def expand_split_seats(names, xs, ys, colours, split_colours, results):
    """For split two-member constituencies, replace each entry with two half-polygon
    entries coloured by the respective winning party. Returns line_colours too:
    black for normal boundaries, pale grey for internal split lines."""
    new_names, new_xs, new_ys, new_colours, new_line_colours, new_results = [], [], [], [], [], []
    for name, x, y, colour, split_colour, result in zip(names, xs, ys, colours, split_colours, results):
        if split_colour is None:
            new_names.append(name)
            new_xs.append(x)
            new_ys.append(y)
            new_colours.append(colour)
            new_line_colours.append('black')
            new_results.append(result)
            continue

        geom = _xs_ys_to_shapely(x, y)
        if geom is None or geom.is_empty:
            new_names.append(name)
            new_xs.append(x)
            new_ys.append(y)
            new_colours.append(colour)
            new_line_colours.append('black')
            new_results.append(result)
            continue

        minx, miny, maxx, maxy = geom.bounds
        midx = (minx + maxx) / 2
        pad = max(maxx - minx, maxy - miny)
        left_half = make_valid(geom.intersection(box(minx - pad, miny - pad, midx, maxy + pad)))
        right_half = make_valid(geom.intersection(box(midx, miny - pad, maxx + pad, maxy + pad)))

        for half, col in [(left_half, colour), (right_half, split_colour)]:
            if not half.is_empty:
                hxs, hys = _shapely_to_xs_ys(half)
                new_names.append(name)
                new_xs.append(hxs)
                new_ys.append(hys)
                new_colours.append(col)
                new_line_colours.append('black')
                new_results.append(result)

    return new_names, new_xs, new_ys, new_colours, new_line_colours, new_results

def expand_multi_seats(names, xs, ys, all_seat_colours, results):
    """Split multi-seat constituencies into N strips (one per seat), coloured by winner.
    Strips run along the polygon's longer axis so they look natural.
    Seats won by the same party are grouped into adjacent strips of that colour.
    Single-seat or unanimously-won constituencies are left as a single polygon."""
    new_names, new_xs, new_ys, new_colours, new_line_colours, new_results = [], [], [], [], [], []

    for name, x, y, seat_colours, result in zip(names, xs, ys, all_seat_colours, results):
        unique = list(dict.fromkeys(seat_colours))
        n = len(seat_colours)

        if n <= 1 or len(unique) == 1:
            new_names.append(name)
            new_xs.append(x)
            new_ys.append(y)
            new_colours.append(seat_colours[0] if seat_colours else '#cccccc')
            new_line_colours.append('black')
            new_results.append(result)
            continue

        geom = _xs_ys_to_shapely(x, y)
        if geom is None or geom.is_empty:
            new_names.append(name)
            new_xs.append(x)
            new_ys.append(y)
            new_colours.append(seat_colours[0] if seat_colours else '#cccccc')
            new_line_colours.append('black')
            new_results.append(result)
            continue

        minx, miny, maxx, maxy = geom.bounds
        width  = maxx - minx
        height = maxy - miny
        pad    = max(width, height)

        # Cut along the longer axis into n equal strips
        any_added = False
        if width >= height:
            step = width / n
            slices = [box(minx + i * step, miny - pad, minx + (i + 1) * step, maxy + pad) for i in range(n)]
        else:
            step = height / n
            slices = [box(minx - pad, miny + i * step, maxx + pad, miny + (i + 1) * step) for i in range(n)]

        for slice_box, col in zip(slices, seat_colours):
            part = make_valid(geom.intersection(slice_box))
            if not part.is_empty:
                hxs, hys = _shapely_to_xs_ys(part)
                new_names.append(name)
                new_xs.append(hxs)
                new_ys.append(hys)
                new_colours.append(col)
                new_line_colours.append('black')
                new_results.append(result)
                any_added = True

        if not any_added:
            new_names.append(name)
            new_xs.append(x)
            new_ys.append(y)
            new_colours.append(seat_colours[0] if seat_colours else '#cccccc')
            new_line_colours.append('black')
            new_results.append(result)

    return new_names, new_xs, new_ys, new_colours, new_line_colours, new_results


def _rings_to_xy(rings):
    """Convert a list of GeoJSON rings (outer + holes) to ([x_lists], [y_lists])."""
    rings_x, rings_y = [], []
    for ring in rings:
        coords = [wgs84_to_webmercator(lon, lat) for lon, lat in ring]
        rings_x.append([c[0] for c in coords])
        rings_y.append([c[1] for c in coords])
    return rings_x, rings_y


def process_geojson(gj):

    names, xs, ys = [], [], []
    for feature in gj['features']:
        props = feature['properties']
        raw_name = props.get('name') or props.get('Name', '')
        names.append(GEOJSON_NAME_MAP.get(raw_name, raw_name))
        geom = feature['geometry']
        if geom['type'] == 'Polygon':
            rings_x, rings_y = _rings_to_xy(geom['coordinates'])
            xs.append([rings_x])
            ys.append([rings_y])
        elif geom['type'] == 'MultiPolygon':
            feat_xs, feat_ys = [], []
            for polygon in geom['coordinates']:
                rings_x, rings_y = _rings_to_xy(polygon)
                feat_xs.append(rings_x)
                feat_ys.append(rings_y)
            xs.append(feat_xs)
            ys.append(feat_ys)
        elif geom['type'] == 'GeometryCollection':
            # Extract polygon components; ignore stray lines/points from clip artefacts
            feat_xs, feat_ys = [], []
            for part in geom['geometries']:
                if part['type'] == 'Polygon':
                    rings_x, rings_y = _rings_to_xy(part['coordinates'])
                    feat_xs.append(rings_x)
                    feat_ys.append(rings_y)
                elif part['type'] == 'MultiPolygon':
                    for polygon in part['coordinates']:
                        rings_x, rings_y = _rings_to_xy(polygon)
                        feat_xs.append(rings_x)
                        feat_ys.append(rings_y)
            xs.append(feat_xs)
            ys.append(feat_ys)

    return names, xs, ys


def get_university_results(election):
    """Returns list of {name, elected_colours, results} for university constituencies in this election."""
    electionObj = Election.objects.get(year=election, type='GE')
    qs = (CandidateResult.objects
          .filter(election=electionObj, constituency__name__icontains='universit')
          .select_related('party', 'constituency')
          .order_by('constituency__name', '-votes'))
    results_by_const = defaultdict(
        lambda: {'Party Colour': [], 'Party': [], 'Candidate': [], 'Votes': [], 'Percent': [], 'Elected': []}
    )
    order = []
    for r in qs:
        name = r.constituency.name
        if name not in results_by_const:
            order.append(name)
        d = results_by_const[name]
        d['Party Colour'].append(r.party.colour)
        d['Party'].append(r.party.name)
        d['Candidate'].append(r.candidate)
        d['Votes'].append(r.votes)
        d['Percent'].append(r.percent)
        d['Elected'].append(r.elected)
    unis = []
    for name in order:
        res = results_by_const[name]
        elected_colours = [c for c, e in zip(res['Party Colour'], res['Elected']) if e]
        unis.append({
            'name': name,
            'elected_colours': elected_colours,
            'results_json': json.dumps(res),
        })
    return unis


