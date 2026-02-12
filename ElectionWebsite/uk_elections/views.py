from .models import *
from .upload import Uploader
from django.shortcuts import render
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

########## GLOBAL VARIABLES ##########

allElectionList = [
'2024','2019','2017','2015','2010','2005','2001','1997','1992','1987','1983','1979','1974 Oct','1974 Feb',
'1970','1966','1964','1959','1955','1951','1950','1945','1935','1931','1929','1924','1923','1922',
'1918','1910 Dec','1910 Jan','1906','1900','1895','1892','1886','1885','1880','1874','1868','1865',
'1859','1857','1852','1847','1841','1837','1835','1832','1831','1830',
]
fullElectionList = [
'2024','2019','2017','2015','2010','2005','2001','1997','1992','1987','1983','1979','1974 Oct','1974 Feb',
'1970','1966','1964','1959','1955','1951','1950','1945','1935','1931','1929','1924','1923','1922',
'1918','1910 Dec','1910 Jan','1906','1900','1895','1892','1886','1885',
]
displayElectionList = [
'2024','2019','2017','2015','2010','2005','2001','1997','1992','1987','1983','1979','1974 Oct','1974 Feb',
'1970','1966','1964','1959','1955','1951','1950',
]
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
            if PARTY.party_list[party].coalition != '':
                coalition = PARTY.party_list[party].coalition

            if party in PARTY.party_list and PARTY.party_list[party].colour_scale != []:
                colour_scale = PARTY.party_list[party].colour_scale
            else:
                colour_scale = ['#403943','#5F5763','#7F7484','#A199A5','#C4BEC6']

            percents = []

            for const in consts:
                if const not in CONSTITUENCY.const_list.keys():
                    try:
                        const_obj = CONSTITUENCY.previous_list[const]
                    except:
                        raise Exception('Constituency not in database',const,election)
                else:
                    const_obj = CONSTITUENCY.const_list[const]
                df = const_obj.election_list[election].results
                if party in list(df.Party):
                    percent_series = df.loc[df['Party'] == party, 'Percent']
                    if percent_series[percent_series.index[0]] != '':
                        percents.append(percent_series[percent_series.index[0]])

            arrays = np.array_split(sorted(percents,reverse=True),5)

            const_count = 0
            colour_count = 0
            for const in consts:
                if const not in CONSTITUENCY.const_list.keys():
                    try:
                        const_obj = CONSTITUENCY.previous_list[const]
                    except:
                        raise Exception('Constituency not in database',const,election)
                else:
                    const_obj = CONSTITUENCY.const_list[const]
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

    electionObj = ELECTION.objects.get(year=election)
    results = GENERALRESULT.objects.filter(election=electionObj).filter(elected=True)
    winners = []
    for const in consts:
        constObj = CONSTITUENCY.objects.get(name=const)
        res = results.filter(constituency=constObj)
        winners.append(res[0].party)

    colours = [party.colour for party in winners]

    return colours

def get_results(consts, election):

        all_results = []
        electionObj = ELECTION.objects.get(year=election)

        for const in consts:
            constObj = CONSTITUENCY.objects.get(name=const)
            results = GENERALRESULT.objects.filter(constituency=constObj).filter(election=electionObj)
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

def get_const_inst(const):

    const_inst = []
    origin = const.originally_created.strftime('%Y')
    if const.abolished == '':
        const_inst.append({'start':origin,'end':'Present','preds':const.orig_preds.split('/'),'succs':[]})
    else:
        starts = list(reversed([origin] + const.recreated.split('|')))
        ends = list(reversed(const.abolished.split('|')))
        preds = list(reversed([const.orig_preds] + const.predecessors.split('|')))
        succs = list(reversed(const.successors.split('|')))
        while starts != []:
            start = starts.pop()
            if start == '':
                break
            if ends:
                end = ends.pop()
            else:
                end = 'Present'
            if preds:
                pred = preds.pop().split('/')
            else:
                pred = []
            if succs:
                succ = succs.pop().split('/')
            else:
                succ = []
            const_inst.append({'start':start,'end':end,'preds':pred,'succs':succ})

    return const_inst

def get_const_object(name):

    try:
        co = CONSTITUENCY.objects.get(name=name)
    except:
        try:
            co = CONSTITUENCY.objects.get(prev_name1=name)
        except:
            try:
                co = CONSTITUENCY.objects.get(prev_name2=name)
            except:
                return None

    return co

########## PAGE VIEWS ##########

def electionView(request, election, map_type='None'):

    module_dir = os.path.dirname(__file__)   #get current directory

    if election == 'home':
        display_elections = []
        partial_elections = []
        for election in fullElectionList:
            if election in displayElectionList:
                display_elections.append(ELECTION.objects.get(year=election))
            else:
                partial_elections.append(ELECTION.objects.get(year=election))

        return render(request, "uk_elections/elections.html", {'pageview':'home', 'display': display_elections, 'partial': partial_elections})

    electionObj = ELECTION.objects.get(year=election)

    if election not in fullElectionList:
        partial = True
    else:
        partial = False

    index = allElectionList.index(election)
    if index == len(allElectionList) - 1:
        next_election = ELECTION.objects.get(year=allElectionList[index-1])
        last_election = None
    elif index == 0:
        next_election = None
        last_election = ELECTION.objects.get(year=allElectionList[index+1])
    else:
        next_election = ELECTION.objects.get(year=allElectionList[index-1])
        last_election = ELECTION.objects.get(year=allElectionList[index+1])

    parties = PARTY.objects.all()
    colours = {p.name:p.colour for p in parties}
    results = GENERALRESULT.objects.filter(election=electionObj).filter(elected=True).order_by('constituency__name')

    overall_results = {}
    const_results = []

    for result in results:
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
    pageview = 'results'

    if election in displayElectionList and map_type == 'map':

        if election in []:

            file_path = os.path.join(module_dir, 'Test.geojson')
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
            indicator_div = Div(text="",min_width=700)
            layout = bkCol(bkRow(p, indicator_div),width_policy="max")

            #tap_tool = TapTool(renderers=[patch_renderer])
            #p.add_tools(tap_tool)
            #patch_indicator_callback = CustomJS(args=dict(cds=cds, div=indicator_div, election=election),
                                                #code=bokeh_display_text)

            #cds.selected.js_on_change('indices', patch_indicator_callback)

            script, div = components(layout)
            pageview = 'map'

        else:

            file_path = os.path.join(module_dir, 'uk_svg_data_ws')
            with open(file_path, "rb") as f:
                svgs = pickle.load(f)
            file_path = os.path.join(module_dir, 'uk_colour_data_ws')
            with open(file_path, "rb") as f:
                all_colours = pickle.load(f)
            file_path = os.path.join(module_dir, 'uk_results_data_ws')
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

            TOOLS = "pan,wheel_zoom,box_zoom,reset,hover,save"

            p = figure(title="General Election " + election, tools=TOOLS, tooltips=[("Name", "@name")],
                x_axis_location=None, y_axis_location=None, aspect_ratio=0.5)

            patch_renderer = p.multi_polygons(xs="x",ys="y",line_width=1,color="colours",line_color='black',
                                              name="names",source=cds)

            p.hover.point_policy = "follow_mouse"

            indicator_div = Div(text="",min_width=700)
            layout = bkCol(bkRow(p, indicator_div),width_policy="max")

            tap_tool = TapTool(renderers=[patch_renderer])
            p.add_tools(tap_tool)
            patch_indicator_callback = CustomJS(args=dict(cds=cds, div=indicator_div, election=election),
                                                code=bokeh_display_text)

            cds.selected.js_on_change('indices', patch_indicator_callback)

            script, div = components(layout)
            pageview = 'map'

    elif election in displayElectionList and map_type == 'hex':

        hex_col = electionObj.hex
        if hex_col == '':
            return render(request, "uk_elections/elections.html", context={'pageview':'NoHex'})

        file_path = os.path.join(module_dir, 'uk_hex_data_ws')
        with open(file_path, "rb") as f:
            hex_df = pickle.load(f)
        file_path = os.path.join(module_dir, 'uk_hex_colour_data_ws')
        with open(file_path, "rb") as f:
            all_colours = pickle.load(f)
        file_path = os.path.join(module_dir, 'uk_hex_results_data_ws')
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

        TOOLS = "pan,wheel_zoom,box_zoom,reset,hover,save"

        p = figure(title="General Election " + election, tools=TOOLS, x_axis_location=None, y_axis_location=None,
                   tooltips=[("Name", "@name")], aspect_ratio=1)

        p.grid.grid_line_color = None
        p.hover.point_policy = "follow_mouse"

        patch_renderer  = p.patches('x', 'y', source=cds,
                  fill_color={"field":"colours"},
                  fill_alpha=0.7, line_color="white", line_width=0.5)

        indicator_div = Div(text="",min_width=700)
        layout = bkCol(bkRow(p, indicator_div),width_policy="max")

        tap_tool = TapTool(renderers=[patch_renderer])
        p.add_tools(tap_tool)

        patch_indicator_callback = CustomJS(args=dict(cds=cds, div=indicator_div, election=election),
                                            code=bokeh_display_text)

        cds.selected.js_on_change('indices', patch_indicator_callback)

        script, div = components(layout)
        pageview = 'hex'

    else:

        context = {'pageview':pageview,
                   'election': electionObj,
                   'overall_results': overall_results,
                   'const_results': const_results,
                   'last': last_election,
                   'next': next_election,
                   'partial':partial}

        return render(request, "uk_elections/elections.html", context=context)



    context = {'pageview':pageview,
               'election': electionObj,
               'overall_results': overall_results,
               'const_results': const_results,
               'script': script,
               'div': div,
               'last': last_election,
               'next': next_election,
               'partial':partial}

    return render(request, "uk_elections/elections.html", context=context)

def constView(request, const):

    if const == 'home':

        consts = CONSTITUENCY.objects.all().order_by('name')

        return render(request, "uk_elections/constituencies.html", {'pageview':'home', 'consts': consts})

    constObj = get_const_object(const)

    if not constObj:
        return render(request, "uk_elections/constituencies.html", {'pageview':'noconst'})

    parties = PARTY.objects.all()
    colours = {p.name:p.colour for p in parties}

    results = pd.DataFrame(list(GENERALRESULT.objects.filter(constituency=constObj).order_by('-votes','-election__startDate').values('election__year','election__startDate','candidate','party__name','votes','percent','unopposed','elected')))
    turnouts = pd.DataFrame(list(GENERALTURNOUT.objects.filter(constituency=constObj).order_by('-election__startDate').values('election__year','election__startDate','votes','percent')))

    if len(results) == 0:
        context = {'pageview':'const',
                   'const': constObj,
                   'results': [],
                   'bydict': {},
                   'const_inst': [],
                   'multi_seats': {},}
        return render(request, "uk_elections/constituencies.html", context=context)

    results.rename(columns={'party__name':'party','election__startDate':'date','election__year':'election'},inplace=True)
    results["colour"] = results.party.apply(lambda x: colours[x])
    results["type"] = "General"
    turnouts.rename(columns={'election__startDate':'date','election__year':'election'},inplace=True)

    byelections = BYELECTION.objects.filter(constituency=constObj)

    if len(byelections) > 0:
        bydict = byelections.values('notes','oldMP')

        byresults = pd.DataFrame(list(BYRESULT.objects.filter(byelection__in=byelections).order_by('-byelection__date').values('byelection__id','byelection__date','byelection__notes','byelection__oldMP','candidate','party__name','votes','percent','unopposed','elected')))
        byturnouts = pd.DataFrame(list(BYTURNOUT.objects.filter(byelection__in=byelections).order_by('-byelection__date').values('byelection__id','byelection__date','votes','percent')))

        byresults.rename(columns={'party__name':'party','byelection__date':'date','byelection__id':'type'},inplace=True)
        byresults["colour"] = results.party.apply(lambda x: colours[x])
        byresults["election"] = byresults.date.apply(lambda x: x.strftime("%Y %B"))
        if len(byturnouts) > 0:
            byturnouts.rename(columns={'byelection__date':'date','byelection__id':'election'},inplace=True)
            byturnouts["election"] = byturnouts.date.apply(lambda x: x.strftime("%Y %B"))

        allresults = pd.concat([results,byresults])
        allturnouts = pd.concat([turnouts,byturnouts])
        allresults.reset_index(inplace=True)
    else:
        allresults = results
        allturnouts = turnouts
        bydict = {}

    allresults.sort_values(by=['votes','date'],ascending=False,inplace=True)
    sep_results = []
    allelections = list(set([(allresults.loc[row,'election'],allresults.loc[row,'date']) for row in allresults.index]))
    allelections.sort(key=lambda x: x[1],reverse=True)

    for election in allelections:

            sep_results.append(
                                (allresults[allresults.election == election[0]].to_dict('records'),
                                allturnouts[allturnouts.election == election[0]].to_dict('records'))
                                )

    instances = get_const_inst(constObj)
    multi_seats = {'four':[],'three':[],'two':[]}
    if constObj.four_mps:
        multi_seats['four'] = constObj.four_mps.split('|')
    if constObj.three_mps:
        multi_seats['three'] = constObj.three_mps.split('|')
    if constObj.two_mps:
        multi_seats['two'] = constObj.two_mps.split('|')

    context = {'pageview':'const',
               'const': constObj,
               'results': sep_results,
               'bydict': bydict,
               'const_inst': instances,
               'multi_seats': multi_seats,}
               #'turnouts': sep_turnouts,}

    return render(request, "uk_elections/constituencies.html", context=context)

########## FUNCTIONS AND VIEWS TO PARSE RAW DATA ##########

def siteadmin(request):
    '''
        View for the admin page
    '''

    status = 'No function run'

    if request.method == 'POST':

        myfile = request.FILES['myfile']
        uploader = Uploader(myfile)
        status = uploader.status

    return render(request, "uk_elections/siteadmin.html", {'status':status})
