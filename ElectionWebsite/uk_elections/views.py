from collections import deque, defaultdict
from .models import *
from .upload import Uploader
from .map_functions import ElectionMap
from .data_cache import get_svg_data, get_hex_data
from .parliament_api import TurnoutQuery
from .validation import compare_constituency, has_any_diff
from .constants import GEOJSON_NAME_MAP
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Count, Sum
from django.utils import timezone
import io
import json
import pickle
from datetime import datetime
from urllib.parse import quote
from django.conf import settings
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import CustomJS, TapTool, ColumnDataSource, FixedTicker, LabelSet, Span, LinearAxis
import os

# Construct path to app's static directory
app_static_dir = os.path.join(os.path.dirname(__file__), 'static')

########## PAGE VIEWS ##########

def electionView(request, election, map_type='None'):

    # Get all general elections
    all_elections = list(Election.objects.filter(type='GE').order_by('-date'))

    # If home requested return election list
    if election == 'home':
        context = {'pageview':'home', 'elections': all_elections}
    else:
        em = ElectionMap(request, election, map_type)
        context = em.context

    context['active_nav'] = 'elections'
    return render(request, "uk_elections/elections.html", context)

# Module-level caches — populated on first use, shared across requests within a worker process.
_mini_svg_cache = {}     # {constituency_name: svg_string}

_CONST_MAPS_DIR = os.path.join(app_static_dir, 'uk_elections', 'constituency_maps')


def _get_constituency_map_url(name):
    """Return an absolute-path URL for the pre-generated PNG, or None if absent."""
    if os.path.exists(os.path.join(_CONST_MAPS_DIR, f'{name}.png')):
        static_url = settings.STATIC_URL
        if not static_url.startswith(('http://', 'https://', '/')):
            static_url = '/' + static_url
        return f'{static_url}uk_elections/constituency_maps/{quote(name)}.png'
    return None


def _get_constituency_mini_svg(name):
    if name in _mini_svg_cache:
        return _mini_svg_cache[name]

    svgs = get_svg_data()
    elections = Election.objects.filter(type='GE', map__isnull=False).exclude(map='').order_by('-date')
    xs_data = ys_data = None
    for elec in elections:
        svg_dict = svgs.get(elec.map)
        if not svg_dict:
            continue
        mapped_names = [GEOJSON_NAME_MAP.get(n, n) for n in svg_dict['names']]
        if name in mapped_names:
            idx = mapped_names.index(name)
            xs_data = svg_dict['xs'][idx]
            ys_data = svg_dict['ys'][idx]
            break

    if xs_data is None:
        _mini_svg_cache[name] = ''
        return ''

    all_x, all_y = [], []
    for poly in xs_data:
        for ring in poly:
            all_x.extend(ring)
    for poly in ys_data:
        for ring in poly:
            all_y.extend(ring)
    if not all_x:
        _mini_svg_cache[name] = ''
        return ''

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    w = max_x - min_x or 1
    h = max_y - min_y or 1
    size = 160
    scale = size / max(w, h)
    pad = 3
    vw = w * scale + pad * 2
    vh = h * scale + pad * 2
    paths = []
    for poly_xs, poly_ys in zip(xs_data, ys_data):
        for ring_xs, ring_ys in zip(poly_xs, poly_ys):
            pts = ' '.join(
                f'{(x - min_x) * scale + pad:.1f},{(max_y - y) * scale + pad:.1f}'
                for x, y in zip(ring_xs, ring_ys)
            )
            paths.append(f'<polygon points="{pts}" fill="#5b82b8" stroke="white" stroke-width="0.5"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw:.0f}" height="{vh:.0f}" '
        f'viewBox="0 0 {vw:.1f} {vh:.1f}">'
        + ''.join(paths) + '</svg>'
    )
    _mini_svg_cache[name] = svg
    return svg


def constituencyView(request, const):

    if const == 'home':

        names = list(Constituency.objects.values_list('name', flat=True).order_by('name').distinct())
        consts_by_letter = {}
        for name in names:
            consts_by_letter.setdefault(name[0].upper(), []).append(name)
        first_letter = next(iter(consts_by_letter), '')

        return render(request, "uk_elections/constituencies.html", {
            'pageview': 'home',
            'consts_by_letter': consts_by_letter,
            'first_letter': first_letter,
            'active_nav': 'constituencies',
        })

    try:
        constObjs = Constituency.objects.filter(name=const)
    except:
        return render(request, "uk_elections/constituencies.html", {'pageview':'noconst', 'active_nav': 'constituencies'})

    all_results = CandidateResult.objects.filter(constituency__in=constObjs)
    all_elections = list(set(x.election for x in all_results))
    all_elections = sorted(all_elections, key=lambda x: x.date, reverse=True)

    sep_results = []
    
    for election in all_elections:
            crs = all_results.filter(election=election).order_by('-votes')
            res_dict = {'election':election, 
                        'results':[], 
                        'notes':[election.notes,] if election.notes else []}
            for cr in crs:
                res_dict['results'].append(cr)
                if cr.notes:
                    res_dict['notes'].append(cr.notes)
            const_res = ConstituencyResult.objects.filter(constituency__in=constObjs, election=election)
            if const_res:
                res_dict['turnout'] = const_res[0]
                if const_res[0].notes:
                    res_dict['notes'].append(const_res[0].notes)
            sep_results.append(res_dict)

    # Vote share history chart (GE elections with known percentages)
    vs_script = vs_div = ''
    ge_elections = [e for e in all_elections if e.type == 'GE']
    if ge_elections:
        all_years = sorted(float(e.year.split()[0]) for e in ge_elections)
        party_data = {}
        for election in ge_elections:
            for cr in all_results.filter(election=election):
                pname = cr.party.name
                pct = 100.0 if (cr.unopposed and cr.elected) else cr.percent
                if pct is None:
                    continue
                if pname not in party_data:
                    party_data[pname] = {'colour': cr.party.colour, 'years': {}}
                party_data[pname]['years'][float(election.year.split()[0])] = float(pct)

        if party_data:
            p_vs = figure(
                height=320,
                tools="hover,reset,save",
                x_axis_label='Year', y_axis_label='Vote Share (%)',
                sizing_mode="stretch_width",
            )
            p_vs.background_fill_color = None
            p_vs.border_fill_color = None
            p_vs.outline_line_color = None
            p_vs.xgrid.grid_line_color = '#e8e8e8'
            p_vs.ygrid.grid_line_color = '#e8e8e8'
            p_vs.xaxis.ticker = FixedTicker(ticks=all_years)
            p_vs.xaxis.major_label_orientation = 0.785

            for party, data in party_data.items():
                colour = data['colour']
                pcts = [float(data['years'].get(yr, float('nan'))) for yr in all_years]
                src = ColumnDataSource(dict(
                    year=all_years,
                    pct=pcts,
                    party=[party] * len(all_years),
                ))
                p_vs.line('year', 'pct', color=colour, line_width=2, source=src)
                p_vs.scatter('year', 'pct', color=colour, size=6, source=src)

            p_vs.hover.tooltips = [('Party', '@party'), ('Year', '@year'), ('Vote Share', '@pct{0.1f}%')]
            p_vs.hover.mode = 'mouse'
            vs_script, vs_div = components(p_vs)

    context = {'pageview':'const',
               'consts': constObjs,
               'results': sep_results,
               'vs_div': vs_div,
               'vs_script': vs_script,
               'const_map_url': _get_constituency_map_url(const),
               'mini_svg': _get_constituency_mini_svg(const),
               'active_nav': 'constituencies',}
    
    return render(request, "uk_elections/constituencies.html", context=context)

def boundaryChangesView(request):

    elections = list(Election.objects.filter(type='GE').order_by('date'))

    # For years with two elections (e.g. 1910, 1974) associate boundary changes with the first
    seen_years = set()
    unique_elections = []
    for e in elections:
        cal_year = e.date.year
        if cal_year not in seen_years:
            seen_years.add(cal_year)
            unique_elections.append(e)

    changes = []
    for i, e in enumerate(unique_elections):
        if i == 0:
            # No previous election to compare: fall back to same-year match
            created  = list(Constituency.objects.filter(start_date__year=e.date.year).order_by('name'))
            abolished = list(Constituency.objects.filter(end_date__year=e.date.year).order_by('name'))
        else:
            prev_date = unique_elections[i - 1].date
            created = list(
                Constituency.objects.filter(
                    start_date__gt=prev_date,
                    start_date__lte=e.date,
                ).order_by('name')
            )
            abolished = list(
                Constituency.objects.filter(
                    end_date__gt=prev_date,
                    end_date__lte=e.date,
                ).order_by('name')
            )
        if created or abolished:
            changes.append({'election': e, 'created': created, 'abolished': abolished})

    changes.reverse()  # most recent first

    return render(request, 'uk_elections/boundary_changes.html', {
        'pageview': 'changes',
        'changes': changes,
        'active_nav': 'boundaries',
    })

def countyView(request, county):

    if county == 'home':

        NON_ENGLAND = {'Scotland', 'Wales', 'Ireland', 'Northern Ireland'}
        groups = {'England': [], 'Scotland': [], 'Wales': [], 'Ireland': [], 'Northern Ireland': []}
        for c in County.objects.select_related('region').order_by('name'):
            region = c.region.name
            if region in NON_ENGLAND:
                groups[region].append(c.name)
            else:
                groups['England'].append(c.name)
        counties_by_country = {k: v for k, v in groups.items() if v}

        return render(request, "uk_elections/county.html", {'pageview':'home', 'counties_by_country': counties_by_country, 'active_nav': 'counties'})

    try:
        countyObj = County.objects.get(name=county)
    except County.DoesNotExist:
        return render(request, "uk_elections/county.html", {'pageview':'nocounty', 'active_nav': 'counties'})

    modern_consts = list(
        countyObj.modern_counties.values_list('name', flat=True).order_by('name').distinct()
    )
    historic_consts = list(
        countyObj.historic_counties.values_list('name', flat=True)
        .order_by('name').distinct()
        .exclude(name__in=modern_consts)
    )

    # Timeline — all constituency periods linked to this county
    all_const_objs = list(
        Constituency.objects.filter(
            Q(modern_county=countyObj) | Q(historic_county=countyObj)
        ).distinct().order_by('name', 'start_date')
    )

    tl_script = tl_div = ''
    CLIP_YEAR = 1830
    current_year = datetime.now().year

    if all_const_objs:
        # Group periods by name — each unique name gets one row, multiple bars
        grouped = {}
        for c in all_const_objs:
            grouped.setdefault(c.name, []).append(c)
        unique_names = sorted(
            grouped.keys(),
            key=lambda name: min(
                c.start_date.year if c.start_date else 0 for c in grouped[name]
            )
        )
        n = len(unique_names)

        ys, names_tl, starts, ends, actual_starts, end_labels, bar_colors = [], [], [], [], [], [], []
        for row_idx, name in enumerate(unique_names):
            name_active = any(c.end_date is None for c in grouped[name])
            for c in grouped[name]:
                start_yr = c.start_date.year if c.start_date else CLIP_YEAR
                end_yr   = c.end_date.year   if c.end_date   else current_year
                ys.append(row_idx)
                names_tl.append(name)
                starts.append(max(start_yr, CLIP_YEAR))
                ends.append(end_yr)
                actual_starts.append(start_yr)
                end_labels.append('Present' if not c.end_date else str(end_yr))
                bar_colors.append('#5a9e6f' if name_active else '#da7672')

        source = ColumnDataSource(dict(
            y=ys, left=starts, right=ends,
            name=names_tl, actual_start=actual_starts, end_label=end_labels,
            bar_color=bar_colors,
        ))

        p_tl = figure(
            height=max(200, n * 28 + 50),
            x_range=(CLIP_YEAR, current_year + 5),
            y_range=(n - 0.5, -0.5),   # flipped: index 0 at top
            tools="hover,reset,save",
            sizing_mode="stretch_width",
        )
        p_tl.background_fill_color = None
        p_tl.border_fill_color = None
        p_tl.outline_line_color = None
        p_tl.ygrid.grid_line_color = None
        p_tl.xgrid.grid_line_color = '#e8e8e8'

        bar_renderer = p_tl.hbar(y='y', left='left', right='right', height=0.6,
                                  fill_color='bar_color', line_color='white', source=source)

        tap_cb = CustomJS(args=dict(source=source), code="""
            const idx = source.selected.indices;
            if (idx.length > 0) {
                const name = source.data['name'][idx[0]];
                window.location.href = '/uk/constituencies/' + encodeURIComponent(name);
            }
        """)
        source.selected.js_on_change('indices', tap_cb)
        p_tl.add_tools(TapTool(renderers=[bar_renderer]))

        p_tl.yaxis.ticker = FixedTicker(ticks=list(range(n)))
        p_tl.yaxis.major_label_overrides = {i: name for i, name in enumerate(unique_names)}
        p_tl.yaxis.major_label_text_font_size = '10pt'

        # Year scale on both top and bottom
        p_tl.add_layout(LinearAxis(), 'above')

        p_tl.hover.tooltips = [
            ('Constituency', '@name'),
            ('Created',      '@actual_start'),
            ('Ended',        '@end_label'),
        ]
        p_tl.hover.point_policy = 'follow_mouse'

        # Dashed line at clip boundary
        p_tl.add_layout(Span(location=CLIP_YEAR, dimension='height',
                             line_color='#aaaaaa', line_dash='dashed', line_width=1))

        # Labels inside bars for pre-1830 start dates
        pre_ys    = [ys[i] for i, s in enumerate(actual_starts) if s < CLIP_YEAR]
        pre_texts = [f'◄ {actual_starts[i]}' for i, s in enumerate(actual_starts) if s < CLIP_YEAR]
        if pre_ys:
            pre_src = ColumnDataSource(dict(
                x=[CLIP_YEAR] * len(pre_ys), y=pre_ys, text=pre_texts,
            ))
            p_tl.add_layout(LabelSet(
                x='x', y='y', text='text', source=pre_src,
                x_offset=4, y_offset=-7,
                text_font_size='9pt', text_color='#444444', text_align='left',
            ))

        tl_script, tl_div = components(p_tl)

    return render(request, "uk_elections/county.html", {
        'pageview':       'county',
        'county':         countyObj,
        'modern_consts':  modern_consts,
        'historic_consts': historic_consts,
        'tl_script':      tl_script,
        'tl_div':         tl_div,
        'active_nav':     'counties',
    })

def peopleView(request, person):
    sep_results = []
    if person == 'home':
        pageview = 'home'
        person = Person.objects.all()
    else:
        try:
            person = Person.objects.get(id=person)
            pageview = 'person'
            all_results = CandidateResult.objects.filter(person=person)

            all_elections = list(set(x.election for x in all_results))
            all_elections = sorted(all_elections, key=lambda x: x.date, reverse=True)
            
            for election in all_elections:
                    crs = all_results.filter(election=election).order_by('-votes')
                    res_dict = {'election':election, 
                                'results':[], 
                                'notes':[election.notes,] if election.notes else []}
                    for cr in crs:
                        res_dict['results'].append(cr)
                        if cr.notes:
                            res_dict['notes'].append(cr.notes)
                    const_res = ConstituencyResult.objects.filter(constituency=crs[0].constituency, election=election)
                    if const_res:
                        res_dict['turnout'] = const_res[0]
                        if const_res[0].notes:
                            res_dict['notes'].append(const_res[0].notes)
                    sep_results.append(res_dict)

        except:
            pageview = 'notfound'
        
    return render(request, 'uk_elections/people.html', {'pageview':pageview, 'person':person, 'results':sep_results, 'active_nav': 'people'})

def sourcesView(request):
    return render(request, "uk_elections/sources.html", {'active_nav': 'sources'})

########## FUNCTIONS AND VIEWS TO PARSE RAW DATA ##########

def hexeditor(request):
    hex_pkl = os.path.join(app_static_dir, 'uk_hex_data_ws')
    with open(hex_pkl, 'rb') as f:
        hex_df = pickle.load(f)

    hex_cols = sorted(c for c in hex_df.columns if c.endswith(' Hex'))
    available_years = [c.replace(' Hex', '') for c in hex_cols]

    base_year   = request.GET.get('base', '')
    target_year = request.GET.get('target', '')
    load_saved  = request.GET.get('saved', '') == '1'
    has_saved   = False
    editor_data = None

    if base_year and target_year and f"{base_year} Hex" in hex_df.columns:
        base_col   = f"{base_year} Hex"
        target_col = f"{target_year} Hex"
        NEIGHBORS  = [(1,-1,0),(-1,1,0),(1,0,-1),(-1,0,1),(0,1,-1),(0,-1,1)]

        base_df = hex_df[hex_df[base_col] != ''][['Constituency', base_col]]
        base_positions = {row[base_col]: row['Constituency'] for _, row in base_df.iterrows()}

        base_set = set(base_positions)
        buffer_set = set()
        frontier = base_set
        for _ in range(2):
            new_ring = set()
            for pos_str in frontier:
                x, y, z = map(int, pos_str.split(','))
                for dx, dy, dz in NEIGHBORS:
                    npos = f"{x+dx},{y+dy},{z+dz}"
                    if npos not in base_set and npos not in buffer_set:
                        new_ring.add(npos)
            buffer_set |= new_ring
            frontier = new_ring

        try:
            target_elec = Election.objects.get(year=int(target_year), type='GE')
            all_consts = list(
                CandidateResult.objects.filter(election=target_elec)
                .values_list('constituency__name', flat=True)
                .distinct().order_by('constituency__name')
            )
            seat_counts = dict(
                CandidateResult.objects.filter(election=target_elec, elected=True)
                .values('constituency__name').annotate(n=Count('id'))
                .values_list('constituency__name', 'n')
            )
        except Election.DoesNotExist:
            all_consts, seat_counts = [], {}

        # Add any constituency in the base map that has no results this election
        # (alternating ones that didn't elect, or ones whose data hasn't been entered yet)
        elected_set = set(all_consts)
        base_name_set = set(base_positions.values())
        base_missing = base_name_set - elected_set
        if base_missing:
            for const in Constituency.objects.filter(name__in=base_missing):
                all_consts.append(const.name)
                seat_counts.setdefault(const.name, const.seats or 1)
        # Also add any DB-flagged alternating constituency not covered above
        alternating_names = set(all_consts)
        for name in (Constituency.objects
                     .filter(alternating__isnull=False)
                     .exclude(alternating='')
                     .exclude(name__in=alternating_names)
                     .values_list('name', flat=True)):
            all_consts.append(name)
            seat_counts.setdefault(name, 1)
        all_consts = sorted(all_consts)

        uni_col = [f"36,{y},{-36-y}" for y in range(8, -4, -1)]
        # Four buffer hexes above and below the university column
        for r_ext in (9, 10, 11, 12, -4, -5, -6, -7):
            buffer_set.add(f"36,{r_ext},{-36-r_ext}")

        # County info for target constituencies — hex_df first, DB fallback
        const_counties = {}
        if 'County' in hex_df.columns:
            county_map = (hex_df[['Constituency', 'County']]
                          .drop_duplicates('Constituency')
                          .set_index('Constituency')['County']
                          .fillna('').to_dict())
            for name in all_consts:
                const_counties[name] = county_map.get(name, '')

        # Fill missing counties from the DB Constituency model (historic_county M2M)
        missing = [n for n in all_consts if not const_counties.get(n)]
        if missing:
            for row in (Constituency.objects
                        .filter(name__in=missing)
                        .exclude(historic_county=None)
                        .values('name', 'historic_county__name')):
                if row['historic_county__name'] and not const_counties.get(row['name']):
                    const_counties[row['name']] = row['historic_county__name']

        target_name_set = set(all_consts)

        # Split base positions: common (name in target) vs base-only (ghost)
        base_only_positions = {}   # pos → name  (grayed out, not in target)
        initial_placement   = {}   # pre-place exact name matches only

        for pos, name in base_positions.items():
            if name in target_name_set:
                seats = seat_counts.get(name, 1)
                lst = initial_placement.setdefault(name, [])
                if len(lst) < seats:
                    lst.append(pos)
            else:
                base_only_positions[pos] = name

        # Load saved column only when explicitly requested (?saved=1)
        has_saved = target_col in hex_df.columns  # noqa: F841 — used in render context
        if load_saved and has_saved:
            initial_placement = {}
            for _, row in hex_df[hex_df[target_col] != ''].iterrows():
                name, pos = row['Constituency'], row[target_col]
                initial_placement.setdefault(name, []).append(pos)
            # Any saved position not in the base map must be added to the buffer
            # so the client includes it in allPositions and renders the hex
            for positions in initial_placement.values():
                for pos in positions:
                    if pos not in base_set:
                        buffer_set.add(pos)
        else:
            # Pre-place university constituencies in the uni_col (fresh start)
            uni_idx = 0
            for name in sorted(n for n in all_consts if 'universit' in n.lower()):
                if name not in initial_placement:
                    seats = seat_counts.get(name, 1)
                    positions = []
                    for _ in range(seats):
                        if uni_idx < len(uni_col):
                            positions.append(uni_col[uni_idx])
                            uni_idx += 1
                    if positions:
                        initial_placement[name] = positions

        editor_data = {
            'base_year':              base_year,
            'target_year':            target_year,
            'base_positions':         base_positions,
            'base_only_positions':    base_only_positions,
            'buffer_positions':       sorted(buffer_set),
            'uni_col_positions':      uni_col,
            'ireland_block_positions': [],
            'target_constituencies':  all_consts,
            'seat_counts':            seat_counts,
            'initial_placement':      initial_placement,
            'const_counties':         const_counties,
        }

    return render(request, 'uk_elections/hexeditor.html', {
        'available_years':    available_years,
        'base_year':          base_year,
        'target_year':        target_year,
        'has_saved':          'true' if has_saved else 'false',
        'load_saved':         load_saved,
        'editor_data_json':   json.dumps(editor_data) if editor_data else 'null',
    })


def hexeditor_save(request):
    import pandas as pd
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    hex_pkl = os.path.join(app_static_dir, 'uk_hex_data_ws')
    body = json.loads(request.body)
    target_year = body.get('target_year', '')
    placement   = body.get('placement', {})   # {name: [pos, ...]}

    if not target_year:
        return JsonResponse({'error': 'No target year'}, status=400)

    with open(hex_pkl, 'rb') as f:
        hex_df = pickle.load(f)

    hex_col = f"{target_year} Hex"
    if hex_col in hex_df.columns:
        hex_df = hex_df.drop(columns=[hex_col])
    hex_df[hex_col] = ''

    from collections import defaultdict
    occurrence = defaultdict(int)
    for idx, row in hex_df.iterrows():
        name = row['Constituency']
        if name in placement:
            occ = occurrence[name]
            if occ < len(placement[name]):
                hex_df.at[idx, hex_col] = placement[name][occ]
                occurrence[name] = occ + 1

    meta = hex_df[['Constituency','Region','County']].drop_duplicates('Constituency').set_index('Constituency')
    extra_rows = []
    for name, positions in placement.items():
        for pos in positions[occurrence.get(name, 0):]:
            r = {col: '' for col in hex_df.columns}
            r.update({'Constituency': name, hex_col: pos,
                      'Region': meta.loc[name,'Region'] if name in meta.index else '',
                      'County': meta.loc[name,'County'] if name in meta.index else ''})
            extra_rows.append(r)
    if extra_rows:
        hex_df = pd.concat([hex_df, pd.DataFrame(extra_rows)], ignore_index=True)

    with open(hex_pkl, 'wb') as f:
        pickle.dump(hex_df, f)

    try:
        elec = Election.objects.filter(year=int(target_year), type='GE').first()
        if elec and not elec.hex:
            elec.hex = hex_col
            elec.save()
    except Exception:
        pass

    return JsonResponse({'status': 'ok', 'placed': len(placement)})


def siteadmin(request):
    '''
        View for the admin page
    '''

    status = ['No function run']

    if request.method == 'POST':

        myfile = request.FILES['myfile']
        uploader = Uploader(myfile)
        status = uploader.errors

    elections = (Election.objects
                 .filter(type='GE')
                 .order_by('date')
                 .annotate(elected_count=Count('candidateresult', filter=Q(candidateresult__elected=True))))

    election_stats = []
    for e in elections:
        active = (Constituency.objects
                  .filter(start_date__lte=e.date)
                  .filter(Q(end_date__isnull=True) | Q(end_date__gt=e.date)))
        totals = active.aggregate(constituency_count=Count('id'), seat_total=Sum('seats'))
        election_stats.append({
            'election': e,
            'constituency_count': totals['constituency_count'] or 0,
            'seat_total': totals['seat_total'] or 0,
            'elected_count': e.elected_count,
        })

    # Find constituencies where a record ended and a replacement started with a different seat count.
    # These indicate data entry errors (e.g. seats entered as 1 then corrected to 2 via a new record).
    dup_names = (Constituency.objects
                 .values('name')
                 .annotate(cnt=Count('id'))
                 .filter(cnt__gt=1)
                 .values_list('name', flat=True))

    seat_issues = []
    for name in sorted(dup_names):
        instances = list(Constituency.objects.filter(name=name).order_by('start_date'))
        for i in range(len(instances) - 1):
            old, new = instances[i], instances[i + 1]
            if old.seats != new.seats:
                seat_issues.append({
                    'name': name,
                    'old_seats': old.seats,
                    'new_seats': new.seats,
                    'old_end': old.end_date,
                    'new_start': new.start_date,
                })

    return render(request, "uk_elections/siteadmin.html", {
        'status': status,
        'election_stats': election_stats,
        'seat_issues': seat_issues,
    })

def parliamentapi(request):

    if request.method == 'POST':
        import pandas as pd
        file = request.FILES.get('file')
        if not file:
            return render(request, "uk_elections/parliamentapi.html", {'error': 'No file uploaded.'})

        df = pd.read_excel(file)
        query = TurnoutQuery()
        results = []

        for _, row in df.iterrows():
            try:
                year = row['Year']
                year = str(int(year)) if isinstance(year, (int, float)) else str(year).strip()
                turnout = query.query(str(row['Constituency']), year)
            except Exception as e:
                turnout = f'Error: {e}'
            results.append(turnout)

        df[TurnoutQuery.RESULT_COLUMN] = results

        output = io.BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="api_results.xlsx"'
        return response

    return render(request, "uk_elections/parliamentapi.html", {'result_column': TurnoutQuery.RESULT_COLUMN})


########## HOP IMPORT VIEWS ##########

def hop_import_list(request):
    from .hop_import import get_hop_constituency_list
    try:
        constituencies = get_hop_constituency_list()
    except Exception as e:
        constituencies = []
        return render(request, 'uk_elections/hop_import_list.html', {
            'constituencies': [], 'error': str(e),
        })
    return render(request, 'uk_elections/hop_import_list.html', {
        'constituencies': constituencies,
        'count': len(constituencies),
    })


def hop_import_preview(request, slug):
    from .hop_import import (
        get_hop_constituency_list, slug_to_name,
        build_preview, commit_preview,
    )
    try:
        from scrape_hop_constituencies import fetch_page, parse_elections_table
    except ImportError:
        from django.http import HttpResponse
        return HttpResponse('scrape_hop_constituencies is not available in this environment.', status=501)

    # Resolve the display name from the cached CDX list
    try:
        const_list = get_hop_constituency_list()
        match = next((c for c in const_list if c[1] == slug), None)
        constituency_name = match[0] if match else slug_to_name(slug)
        hop_url = match[2] if match else (
            f'https://www.historyofparliamentonline.org/volume/1820-1832/constituencies/{slug}'
        )
    except Exception:
        constituency_name = slug_to_name(slug)
        hop_url = f'https://www.historyofparliamentonline.org/volume/1820-1832/constituencies/{slug}'

    session_key = f'hop_html_{slug}'

    def _soup_from_html(html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'html.parser')

    def _build_from_soup(soup):
        rows = parse_elections_table(soup, constituency_name)
        if not rows:
            return None, 'No election table found in this HTML.'
        return build_preview(rows, constituency_name), None

    if request.method == 'POST':
        raw_html = request.POST.get('raw_html', '').strip()

        if raw_html:
            # User pasted page source — build preview from it
            request.session[session_key] = raw_html
            preview, err = _build_from_soup(_soup_from_html(raw_html))
            if err:
                return render(request, 'uk_elections/hop_import_preview.html', {
                    'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
                    'error': err,
                })
            return render(request, 'uk_elections/hop_import_preview.html', {
                'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
                'preview': preview, 'committed': False,
            })

        # Commit step — re-parse from session HTML or re-fetch
        stored_html = request.session.pop(session_key, None)
        if stored_html:
            soup = _soup_from_html(stored_html)
        else:
            soup, fetch_error = fetch_page(hop_url)
            if not soup:
                return render(request, 'uk_elections/hop_import_preview.html', {
                    'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
                    'error': f'Could not fetch HOP page to commit. ({fetch_error})',
                })
        rows = parse_elections_table(soup, constituency_name)
        preview = build_preview(rows, constituency_name)
        stats = commit_preview(preview)
        return render(request, 'uk_elections/hop_import_preview.html', {
            'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
            'committed': True, 'stats': stats,
        })

    # GET — try to fetch automatically
    soup, fetch_error = fetch_page(hop_url)
    if not soup:
        return render(request, 'uk_elections/hop_import_preview.html', {
            'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
            'error': f'Could not fetch HOP page automatically. ({fetch_error})',
            'show_paste_form': True,
        })
    rows = parse_elections_table(soup, constituency_name)
    if not rows:
        return render(request, 'uk_elections/hop_import_preview.html', {
            'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
            'error': 'No election table found on this HOP page.',
            'show_paste_form': True,
        })
    preview = build_preview(rows, constituency_name)
    return render(request, 'uk_elections/hop_import_preview.html', {
        'constituency_name': constituency_name, 'hop_url': hop_url, 'slug': slug,
        'preview': preview, 'committed': False,
    })


########## VALIDATION VIEWS ##########

def validate_election_select(request):
    elections = Election.objects.filter(type='GE').order_by('year')
    return render(request, 'uk_elections/validate_election_select.html', {'elections': elections})


def validate_election(request, election_id):
    election = get_object_or_404(Election, pk=election_id, type='GE')

    constituency_ids = list(
        ConstituencyResult.objects.filter(election=election)
        .order_by('constituency__name')
        .values_list('constituency_id', flat=True)
    )

    validation_map = {
        vr.constituency_id: vr
        for vr in APIValidationRecord.objects.filter(election=election)
    }

    rows = []
    for cid in constituency_ids:
        c = Constituency.objects.get(pk=cid)
        vr = validation_map.get(cid)
        rows.append({
            'constituency': c,
            'status': vr.status if vr else 'pending',
            'checked_at': vr.checked_at if vr else None,
        })

    checked = sum(1 for r in rows if r['status'] != 'pending')
    first_unchecked_id = next(
        (r['constituency'].id for r in rows if r['status'] == 'pending'), None
    )

    return render(request, 'uk_elections/validate_election.html', {
        'election': election,
        'rows': rows,
        'checked': checked,
        'total': len(rows),
        'first_unchecked_id': first_unchecked_id,
    })


def validate_constituency(request, election_id, constituency_id):
    election = get_object_or_404(Election, pk=election_id, type='GE')
    constituency = get_object_or_404(Constituency, pk=constituency_id)

    # Ordered list of all constituency IDs for this election (for navigation)
    all_ids = list(
        ConstituencyResult.objects.filter(election=election)
        .order_by('constituency__name')
        .values_list('constituency_id', flat=True)
    )

    checked_ids = set(
        APIValidationRecord.objects.filter(election=election)
        .exclude(status='pending')
        .values_list('constituency_id', flat=True)
    )

    # Next unchecked constituency after the current one (wraps around)
    try:
        cur_pos = all_ids.index(constituency_id)
    except ValueError:
        cur_pos = -1
    next_unchecked_id = None
    for cid in all_ids[cur_pos + 1:] + all_ids[:cur_pos]:
        if cid not in checked_ids:
            next_unchecked_id = cid
            break

    if request.method == 'POST':
        action = request.POST.get('action')
        vr, _ = APIValidationRecord.objects.get_or_create(
            constituency=constituency, election=election
        )

        if action == 'apply':
            # Apply name updates passed as hidden form fields
            updated = 0
            for key, new_name in request.POST.items():
                if key.startswith('name_update_'):
                    pk = int(key[len('name_update_'):])
                    CandidateResult.objects.filter(pk=pk).update(candidate=new_name)
                    updated += 1
            vr.status = 'updated' if updated else 'clean'

        elif action == 'skip':
            vr.status = 'clean'

        elif action == 'flag':
            vr.status = 'flagged'
            vr.notes = request.POST.get('notes', '')

        vr.checked_at = timezone.now()
        vr.save()

        if next_unchecked_id:
            return redirect('validate_constituency',
                            election_id=election_id,
                            constituency_id=next_unchecked_id)
        return redirect('validate_election', election_id=election_id)

    # GET — run comparison
    result = compare_constituency(constituency, election)
    vr = APIValidationRecord.objects.filter(
        constituency=constituency, election=election
    ).first()

    return render(request, 'uk_elections/validate_constituency.html', {
        'election': election,
        'constituency': constituency,
        'result': result,
        'has_diff': has_any_diff(result) if not result.get('error') else False,
        'vr': vr,
        'next_unchecked_id': next_unchecked_id,
        'checked': len(checked_ids),
        'total': len(all_ids),
        'unchecked': len(all_ids) - len(checked_ids),
    })
