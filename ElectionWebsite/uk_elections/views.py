from .models import *
from .upload import Uploader
from .map_functions import ElectionMap
from .parliament_api import TurnoutQuery
from .validation import compare_constituency, has_any_diff
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.db.models import Q
from django.utils import timezone
import io
import pandas as pd
from datetime import datetime
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

    return render(request, "uk_elections/elections.html", context)

def constituencyView(request, const):

    if const == 'home':

        names = list(Constituency.objects.values_list('name', flat=True).order_by('name').distinct())

        return render(request, "uk_elections/constituencies.html", {'pageview':'home', 'consts': names})

    try:
        constObjs = Constituency.objects.filter(name=const)
    except:
        return render(request, "uk_elections/constituencies.html", {'pageview':'noconst'})

    parties = Party.objects.all()
    colours = {p.name:p.colour for p in parties}

    results = pd.DataFrame(list(CandidateResult.objects.filter(constituency__in=constObjs).order_by('-votes','-election__date').values('election__type','election__year','election__date','candidate','party__name','votes','percent','unopposed','elected')))
    turnouts = pd.DataFrame(list(ConstituencyResult.objects.filter(constituency__in=constObjs).order_by('-election__date').values('election__type','election__year','election__date','turnout_votes','turnout_percent')))

    if len(results) == 0:
        context = {'pageview':'const',
                   'consts': constObjs,
                   'results': [],}
        return render(request, "uk_elections/constituencies.html", context=context)

    results.rename(columns={'party__name':'party','election__type':'type','election__date':'date','election__year':'election'},inplace=True)
    results["colour"] = results.party.apply(lambda x: colours[x])
    turnouts.rename(columns={'election__type':'type','election__date':'date','election__year':'election'},inplace=True)

    results.sort_values(by=['votes','date'],ascending=False,inplace=True)

    # Vote share history chart (GE elections with known percentages)
    vs_script = vs_div = ''
    ge = results[(results['type'] == 'GE') & results['percent'].notna()].copy()
    if not ge.empty:
        ge['year'] = pd.to_datetime(ge['date']).dt.year

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
        p_vs.xaxis.ticker = FixedTicker(ticks=sorted(ge['year'].unique().tolist()))
        p_vs.xaxis.major_label_orientation = 0.785  # 45 degrees

        all_years = sorted(ge['year'].unique().tolist())
        for party, grp in ge.groupby('party'):
            grp = grp.sort_values('year')
            party_pcts = dict(zip(grp['year'], grp['percent']))
            colour = grp['colour'].iloc[0]
            pcts = [float(party_pcts.get(yr, float('nan'))) for yr in all_years]
            src = ColumnDataSource(dict(
                year=all_years,
                pct=pcts,
                party=[party] * len(all_years),
            ))
            p_vs.line('year', 'pct', color=colour, line_width=2, source=src)
            p_vs.scatter('year', 'pct', color=colour, size=6, source=src)

        p_vs.hover.tooltips = [('Party', '@party'), ('Year', '@year'), ('Vote Share', '@pct{0.1f}%')]
        p_vs.hover.mode = 'mouse'
        p_vs.legend.visible = False
        vs_script, vs_div = components(p_vs)

    sep_results = []
    allelections = list(set([(results.loc[row,'election'],results.loc[row,'date']) for row in results.index]))
    allelections.sort(key=lambda x: x[1],reverse=True)

    for election in allelections:

            sep_results.append(
                                (results[results.election == election[0]].to_dict('records'),
                                turnouts[turnouts.election == election[0]].to_dict('records'))
                                )

    context = {'pageview':'const',
               'consts': constObjs,
               'results': sep_results,
               'vs_div': vs_div,
               'vs_script': vs_script,}
    
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
    for e in unique_elections:
        cal_year = e.date.year
        created  = list(Constituency.objects.filter(start_date__year=cal_year).order_by('name'))
        abolished = list(Constituency.objects.filter(end_date__year=cal_year).order_by('name'))
        if created or abolished:
            changes.append({'election': e, 'created': created, 'abolished': abolished})

    changes.reverse()  # most recent first

    return render(request, 'uk_elections/boundary_changes.html', {
        'pageview': 'changes',
        'changes': changes,
    })

def countyView(request, county):

    if county == 'home':

        names = list(County.objects.values_list('name', flat=True).order_by('name').distinct())

        return render(request, "uk_elections/county.html", {'pageview':'home', 'counties': names})

    try:
        countyObj = County.objects.get(name=county)
    except County.DoesNotExist:
        return render(request, "uk_elections/county.html", {'pageview':'nocounty'})

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
    })

########## FUNCTIONS AND VIEWS TO PARSE RAW DATA ##########

def siteadmin(request):
    '''
        View for the admin page
    '''

    status = ['No function run']

    if request.method == 'POST':

        myfile = request.FILES['myfile']
        uploader = Uploader(myfile)
        status = uploader.errors

    return render(request, "uk_elections/siteadmin.html", {'status':status})

def parliamentapi(request):

    if request.method == 'POST':
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
