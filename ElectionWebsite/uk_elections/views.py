from .models import *
from .upload import Uploader
from .parliament_api import TurnoutQuery
from .validation import compare_constituency, has_any_diff, db_year_to_api_year
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.utils import timezone
import io
import pandas as pd
import numpy as np
from datetime import datetime
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import CustomJS, Div, TapTool, ColumnDataSource, MultiPolygons, Plot, LinearAxis, Grid, GeoJSONDataSource
from bokeh.layouts import column as bkCol
from bokeh.layouts import row as bkRow
import pickle, os, urllib, json, geojson
from matplotlib.patches import RegularPolygon
from django.templatetags.static import static
from django.conf import settings
import os

########## GLOBAL VARIABLES ##########

# Construct path to app's static directory
app_static_dir = os.path.join(os.path.dirname(__file__), 'static')

# Template for the text to be displayed when a constituency is clicked on the map
bokeh_display_text = """div.text = "<style>table {font-family: arial, sans-serif;border-collapse: collapse;width: 60%;}" +
        "td {border: 0.5px solid #000000;text-align: left;padding: 1px 5px 1px 5px;}" +
        "th {border: 0.5px solid #000000;background-color: #E7E6E7;text-align: center;padding: 1px 5px 1px 5px;}" +
        ".blank {border: none;}</style>" +
        "<h2>" + cds.data['name'][cb_obj.indices] + "</h2><h3>" + election + " General Election Results</h3><br>" +
          "<b>Winning Party:</b> " + cds.data['results'][cb_obj.indices]['Party'][0] + "<br><br>" +
          "<table>" +
          "<tr>" +
            "<th style='width:1px;'> </th>" +
            "<th>Party</th>" +
            "<th>Candidate</th>" +
            "<th style='width:60px;'>Votes</th>" +
            "<th style='width:60px;'>Percent</th>" +
          "</tr>"
          let partyList = cds.data['results'][cb_obj.indices]['Party']
          for (let i = 0; i < Object.keys(partyList).length; i++) {
            div.text += "<tr><td style='width:1px;background-color:" + cds.data['results'][cb_obj.indices]['Party Colour'][i] + ";'> </td>";
            div.text += "<td>" + cds.data['results'][cb_obj.indices]['Party'][i] + "</td>";
            div.text += "<td>" + cds.data['results'][cb_obj.indices]['Candidate'][i] + "</td>";
            div.text += "<td style='width:60px;'>" + cds.data['results'][cb_obj.indices]['Votes'][i] + "</td>";
            div.text += "<td style='width:60px;'>" + cds.data['results'][cb_obj.indices]['Percent'][i] + "</td></tr>";
            }
          div.text += "</table><br>"
          div.text += "<p><a href='/uk/constituencies/" + cds.data['name'][cb_obj.indices] + "'>Constituency Page</a>"
       """

########## AUXILLERY FUNCTIONS ##########

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
    results = CandidateResult.objects.filter(election=electionObj).filter(elected=True)
    winners = []
    for const in consts:
        constObj = Constituency.objects.get(name=const)
        res = results.filter(constituency=constObj)
        winners.append(res[0].party)

    colours = [party.colour for party in winners]

    return colours

def get_results(consts, election):

        all_results = []
        electionObj = Election.objects.get(year=election, type='GE')

        for const in consts:
            constObj = Constituency.objects.get(name=const)
            results = CandidateResult.objects.filter(constituency=constObj).filter(election=electionObj)
            resDict = {'Party Colour':[],'Party':[],'Candidate':[],'Votes':[],'Percent':[]}
            for res in results:
                resDict['Party Colour'].append(res.party.colour)
                resDict['Party'].append(res.party.name)
                resDict['Candidate'].append(res.candidate)
                resDict['Votes'].append(res.votes)
                resDict['Percent'].append(res.percent)
            all_results.append(resDict)

        return all_results

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

########## PAGE VIEWS ##########

def electionView(request, election, map_type='None'):

    module_dir = os.path.dirname(__file__)   #get current directory

    # Get all general elections
    all_elections = list(Election.objects.filter(type='GE').order_by('-date'))

    # If home requested return election list
    if election == 'home':
        return render(request, "uk_elections/elections.html", {'pageview':'home', 'elections': all_elections})

    # Other set pageview to 'results'
    context = {'pageview':'results'}

    # Get election instance requested, add to context and get index
    electionObj = Election.objects.get(year=election, type='GE')
    context['election'] = electionObj
    index = all_elections.index(electionObj)

    # all_elections is ordered -date (newest first)
    # so index+1 = older = "Previous" and index-1 = newer = "Next"
    context['next'] = all_elections[index - 1] if index > 0 else None
    context['last'] = all_elections[index + 1] if index < len(all_elections) - 1 else None

    # Get all parties and colours
    parties = Party.objects.all()
    colours = {p.name:p.colour for p in parties}
    
    # Get all candidate results
    cand_results = CandidateResult.objects.filter(election=electionObj, elected=True).order_by('constituency__name')

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
                    'Candidate':result.candidate}
        const_results.append(res_dict)

    overall_results = [(k,overall_results[k],colours[k]) for k in overall_results.keys()]
    overall_results.sort(key=lambda x: x[1], reverse=True)
    context['overall_results'] = overall_results
    context['const_results'] = const_results

    if electionObj.map and map_type == 'map':
        
        context['pageview'] = 'map'

        if electionObj.year in []:

            file_path = os.path.join(app_static_dir, 'Test.geojson')

            with open(file_path) as f:
                gj = geojson.load(f)
            #from bokeh.sampledata.sample_geojson import geojson as test_gj
            #gj = json.loads(test_gj)

            #gj2 = {'features':gj['features'][:2]}
            geo_source = GeoJSONDataSource(geojson=json.dumps(gj))
            p = figure(x_range=(-2000000, 6000000), y_range=(-1000000, 7000000),
                       x_axis_type="mercator", y_axis_type="mercator")
            #TOOLTIPS = [('Organisation', '@OrganisationName')]
            TOOLS = "pan,wheel_zoom,box_zoom,reset,hover,save"
            #p = figure(x_axis_location=None, y_axis_location=None,tools=TOOLS)
            #p.add_tile(xyz.OpenStreetMap.Mapnik)
            p.multi_polygons(xs="x",ys="y",line_width=1,line_color='black',source=geo_source)
            #p.scatter(x='x', y='y', size=15, color='Color', alpha=0.7, source=geo_source)
            indicator_div = Div(text="", sizing_mode="stretch_width")
            layout = bkCol(bkRow(p, indicator_div, sizing_mode="stretch_width"), sizing_mode="stretch_width")

            script, div = components(layout)

        else:

            file_path = os.path.join(app_static_dir, 'uk_svg_data_ws')
            with open(file_path, "rb") as f:
                svgs = pickle.load(f)
            file_path = os.path.join(app_static_dir, 'uk_colour_data_ws')
            with open(file_path, "rb") as f:
                all_colours = pickle.load(f)
            file_path = os.path.join(app_static_dir, 'uk_results_data_ws')
            with open(file_path, "rb") as f:
                all_results = pickle.load(f)

            svg_dict = svgs[electionObj.map]

            names = svg_dict['names']
            #colours = get_colours(names, election)
            #results = get_results(names, election)
            colours = all_colours[election]
            results = all_results[election]

            data = dict(x=svg_dict['xs'],y=svg_dict['ys'],name=names,colours=colours,results=results)

            cds = ColumnDataSource(data)

            TOOLS = "wheel_zoom,reset,save"
            placeholder = ("<div style='padding:20px 16px;color:#6a7480;font-style:italic;"
                           "border:1px solid #dde3ea;border-radius:4px;'>"
                           "Click a constituency to see results.</div>")

            p = figure(tools=TOOLS, tooltips=[("Name", "@name")],
                x_axis_location=None, y_axis_location=None, aspect_ratio=0.5,
                sizing_mode="stretch_width")
            p.background_fill_color = None
            p.border_fill_color = None
            p.outline_line_color = None

            patch_renderer = p.multi_polygons(xs="x", ys="y", line_width=1,
                                              fill_color="colours", line_color='black',
                                              name="names", source=cds)

            p.hover.point_policy = "follow_mouse"

            indicator_div = Div(text=placeholder, width=340, sizing_mode="fixed",
                                styles={"position": "sticky", "top": "20px", "align-self": "flex-start"})
            layout = bkCol(bkRow(p, indicator_div, sizing_mode="stretch_width"), sizing_mode="stretch_width")

            tap_tool = TapTool(renderers=[patch_renderer])
            p.add_tools(tap_tool)
            patch_indicator_callback = CustomJS(args=dict(cds=cds, div=indicator_div, election=election),
                                                code=bokeh_display_text)

            cds.selected.js_on_change('indices', patch_indicator_callback)

            script, div = components(layout)
        
        context['script'] = script
        context['div'] = div            

    elif electionObj.hex and map_type == 'hex':

        hex_col = electionObj.hex
        if hex_col == '':
            return render(request, "uk_elections/elections.html", context={'pageview':'NoHex'})

        file_path = os.path.join(app_static_dir, 'uk_hex_data_ws')
        with open(file_path, "rb") as f:
            hex_df = pickle.load(f)
        file_path = os.path.join(app_static_dir, 'uk_hex_colour_data_ws')
        with open(file_path, "rb") as f:
            all_colours = pickle.load(f)
        file_path = os.path.join(app_static_dir, 'uk_hex_results_data_ws')
        with open(file_path, "rb") as f:
            all_results = pickle.load(f)

        hex_df = hex_df[hex_df[hex_col] != ""]

        names = list(hex_df['Constituency'])
        coords = list(hex_df[hex_col])
        xs, ys = get_hex_coords(coords)
        colours = all_colours[election]
        results = all_results[election]

        data = dict(x=xs, y=ys, name=names, colours=colours, results=results)

        cds = ColumnDataSource(data)

        TOOLS = "wheel_zoom,reset,save"
        placeholder = ("<div style='padding:20px 16px;color:#6a7480;font-style:italic;"
                       "border:1px solid #dde3ea;border-radius:4px;'>"
                       "Click a constituency to see results.</div>")

        p = figure(tools=TOOLS, x_axis_location=None, y_axis_location=None,
                   tooltips=[("Name", "@name")], aspect_ratio=1, sizing_mode="stretch_width")
        p.background_fill_color = None
        p.border_fill_color = None
        p.outline_line_color = None

        p.grid.grid_line_color = None
        p.hover.point_policy = "follow_mouse"

        patch_renderer = p.patches('x', 'y', source=cds,
                  fill_color={"field": "colours"},
                  fill_alpha=0.7, line_color="white", line_width=0.5)

        indicator_div = Div(text=placeholder, width=340, sizing_mode="fixed",
                            styles={"position": "sticky", "top": "20px", "align-self": "flex-start"})
        layout = bkCol(bkRow(p, indicator_div, sizing_mode="stretch_width"), sizing_mode="stretch_width")

        tap_tool = TapTool(renderers=[patch_renderer])
        p.add_tools(tap_tool)

        patch_indicator_callback = CustomJS(args=dict(cds=cds, div=indicator_div, election=election),
                                            code=bokeh_display_text)

        cds.selected.js_on_change('indices', patch_indicator_callback)

        script, div = components(layout)
        context['script'] = script
        context['div'] = div
        context['pageview'] = 'hex'
    
    return render(request, "uk_elections/elections.html", context=context)

def constituencyView(request, const):

    if const == 'home':

        consts = Constituency.objects.all().order_by('name')
        names = list({const.name for const in consts})

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
               'results': sep_results,}
    
    return render(request, "uk_elections/constituencies.html", context=context)

def countyView(request, county):

    if county == 'home':

        counties = County.objects.all().order_by('name')
        names = list({county.name for county in counties})

        return render(request, "uk_elections/county.html", {'pageview':'home', 'counties': names})

    try:
        countyObj = County.objects.get(name=county)
        return render(request, "uk_elections/county.html", {'pageview':'county', 'county':countyObj})
    except:
        return render(request, "uk_elections/county.html", {'pageview':'nocounty'})

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
