from .models import REGION, COUNTY, PARTY, ELECTION, COALITION
from .models import CONSTITUENCY, CONSTINSTANCE, CONSTSEATS, BYELECTION
from .models import GENERALRESULT, BYRESULT, GENERALTURNOUT, BYTURNOUT
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

def get_election_list(df,row):

    created = str(df['Created'][row])
    if int(created.split(' ')[0]) < 1830:
        created = ['1830']
    else:
        created = [created]

    if df['Re-created'][row] != '':
        created += str(df['Re-created'][row]).split('|')
    abolished = str(df['Abolished'][row]).split('|')

    created.reverse()
    abolished.reverse()
    exists = False
    electionList = []

    if abolished[-1] == '1832':
        abolished.pop()
        created.pop()

    allElections = reversed(allElectionList)

    for election in allElections:
        if created and created[-1] == election:
            exists = True
            created.pop()
        elif abolished and abolished[-1] == election:
            exists = False
            abolished.pop()
        if exists:
            electionList.append(election)

    return electionList

def parse_results(df,byelection_run=False):

    byYear = ''
    byRows = []

    df.fillna('',axis=1,inplace=True)

    #earliest_election = ELECTION.objects.get(year=fullElectionList[0]).startDate.replace(tzinfo=None)

    for row in df.index:

        year = str(df['Year'][row])
        const = get_const_object(df['Constituency'][row])

        # Skip results for elections not yet covered
        #if year[-1] == 'B' and (df['Date'][row] == '' or df['Date'][row] < earliest_election):
            #continue
        #elif year[-1] != 'B' and year not in fullElectionList:
            #continue

        # Skip byelection results for normal run and non-byelections for byelection run
        # Noting that byelections are only created after all rows have been picked up
        if byelection_run and year[-1] != 'B' and not byYear:
            continue
        elif not byelection_run and year[-1] == 'B':
            continue

        # Check whether there is byelection data stored and whether to add to it or parse it
        if byYear:
            if byYear == year: # still same byelection
                byRows.append(row)
                continue
            elif year[-1] == 'B': # new byelection, parse previous byelection, start new one
                status = parse_byelection(df.loc[byRows].to_dict('records'))
                if status != 'success':
                    return status
                byYear = year
                byRows = [row]
                continue
            else: # new election, parse byelection and reset values
                status = parse_byelection(df.loc[byRows].to_dict('records'))
                if status != 'success':
                    return status
                byYear = ''
                byRows = []
                if byelection_run:
                    continue

        # New byelection encountered
        if year[-1] == 'B':
            byYear = year
            byRows = [row]
            continue

        # If row is turnout
        if df['Party'][row] == "Turnout":
            if isinstance(df['Percent'][row],str):
                percent = df['Percent'][row].split(' ')[0]
                if percent == '':
                    percent = None
                else:
                    percent = float(percent)
            else:
                percent = df['Percent'][row]
            t = GENERALTURNOUT(election=ELECTION.objects.get(year=df['Year'][row]),
                               constituency=const,
                               votes=df['Votes'][row],
                               percent=percent,
                               notes=df['Notes'][row])
            t.save()
        # Otherwise row is general election result
        else:
            if df['Votes'][row] == 'Unopposed':
                votes = '0'
                percent = '0'
                unopposed = True
                elected = True
                disqualified = False
            else:
                if isinstance(df['Votes'][row],str) and '*' in df['Votes'][row]:
                    votes = int(df['Votes'][row].replace('*',''))
                    disqualified = True
                else:
                    votes = df['Votes'][row]
                    disqualified = False
                if isinstance(df['Percent'][row],str):
                    percent = df['Percent'][row].split(' ')[0]
                else:
                    percent = df['Percent'][row]
                unopposed = False
                elected = False

            try:
                party = PARTY.objects.get(name=df['Party'][row])
            except:
                party = PARTY(name=df['Party'][row],colour="#DCDCDC")
                party.save()

            r = GENERALRESULT(election=ELECTION.objects.get(year=df['Year'][row]),
                              constituency=const,
                              party=party,
                              candidate=df['Candidate'][row],
                              votes=votes,
                              percent=percent,
                              unopposed=unopposed,
                              disqualified=disqualified,
                              elected=elected,
                              notes=df['Notes'][row])
            r.save()

    return 'success'

def parse_byelection(rows):

    numElected = 1

    for row in rows:
        if row['Notes'] != '':
            notes = row['Notes']

    c = get_const_object(rows[0]['Constituency'])

    if rows[0]['Date']:
        if isinstance(rows[0]['Date'],str):
            be_date = datetime.strptime(rows[0]['Date'],'%d/%m/%Y')
        else:
            be_date = rows[0]['Date']
    else:
        str_year = rows[0]['Year'][:-1]
        if str_year[-1] == 'B':
            str_year = str_year[:-1]
        if ' ' in str_year:
            if len(str_year) > 8:
                be_date = datetime.strptime(str_year,'%Y %d%b')
            else:
                be_date = datetime.strptime(str_year,'%Y %b')
        else:
            be_date = datetime.strptime(str_year,'%Y')

    if isinstance(be_date,str):
        return 'error - date is string - ' + c.name + ' ' + str(be_date)

    current_mps = c.get_current_mps(be_date)
    oldMP = ''

    if len(current_mps) == 1:
        oldMP = current_mps[0]
    elif len(current_mps) == 0:
        return 'error - no current MP - ' + c.name + ' ' + str(be_date)
    else:
        if ']' not in notes:
            return 'error - no bracket - ' + c.name + ' ' + str(be_date) + ' ' + notes
        surname = notes.split(']')[0][1:]
        notes = notes.split(']')[1]
        if surname == 'Both':
            oldMP = ', '.join(current_mps)
            numElected = 2
        else:
            for mp in current_mps:
                if mp.split(' ')[-1] == surname:
                    oldMP = mp

    if oldMP == '':
        return 'error - blank current MP - ' + c.name + ' ' + str(be_date)

    try:
        BYELECTION.objects.get(constituency=c, date=be_date)
        return 'success'
    except:
        pass

    #b = BYELECTION.objects.get(constituency=c, date=be_date)

    b = BYELECTION(constituency=c,
                  date=be_date,
                  oldMP=oldMP,
                  notes=notes)
    b.save()

    br = BYRESULT.objects.filter(byelection=b)
    bt = BYTURNOUT.objects.filter(byelection=b)
    if len(br) + len(bt) == len(rows):
        return 'success'

    allVotes = []
    for i,row in enumerate(rows):
        if isinstance(row['Votes'],str) and '*' in row['Votes']:
            continue
        if row['Party'] == "Turnout":
            continue
        allVotes.append((i,row['Votes']))

    allVotes.sort(key=lambda x: x[1], reverse=True)
    allVotes = allVotes[0:numElected]
    winners = [x[0] for x in allVotes]

    for i,row in enumerate(rows):

        if isinstance(row['Percent'],str):
            percent = row['Percent'].split(' ')[0]
            if percent == '':
                percent = None
            else:
                percent = float(percent)
        else:
            percent = row['Percent']

        if row['Party'] == "Turnout":
            t = BYTURNOUT(byelection=b,
                          votes=row['Votes'],
                          percent=percent,
                          notes=row['Notes'])
            t.save()
        else:
            disqualified = False
            if row['Votes'] == 'Unopposed':
                votes = '0'
                percent = '0'
                unopposed = True
            else:
                if isinstance(row['Votes'],str) and '*' in row['Votes']:
                    votes = row['Votes'].replace('*','')
                    disqualified = True
                else:
                    votes = row['Votes']
                unopposed = False

            try:
                party = PARTY.objects.get(name=row['Party'])
            except:
                party = PARTY(name=row['Party'],colour="#DCDCDC")
                party.save()

            if i in winners:
                elected = True
            else:
                elected = False

            r = BYRESULT(byelection=b,
                         party=party,
                         candidate=row['Candidate'],
                         votes=votes,
                         percent=percent,
                         elected=elected,
                         disqualified=disqualified,
                         unopposed=unopposed)
            r.save()

    return 'success'

def find_winners():

    consts = CONSTITUENCY.objects.all()
    all_cs = CONSTSEATS.objects.filter(winner_found=False)
    not_done_consts = list(set([x.constituency for x in all_cs]))

    for const in consts:

        if const not in not_done_consts:
            continue

        for election in const.election_list.split(','):

            if not election:
                continue

            elect = ELECTION.objects.get(year=election)
            results = GENERALRESULT.objects.filter(constituency=const).filter(election=elect)

            if len(results) == 0:
                return 'no results: ' + const.name + ' - ' + election

            try:
                cs = CONSTSEATS.objects.get(constituency=const,election=elect)
            except:
                return 'error: ' + const.name + ' - ' + election

            if results[0].unopposed:
                cs.winner_found = True
                cs.save()
                continue

            votes = [(x,results[x].votes) for x in range(0,len(results)) if not results[x].disqualified]
            votes.sort(key=lambda x: x[1], reverse=True)

            seats = cs.seats

            for i in range(0,seats):
                res = results[votes[i][0]]
                res.elected = True
                res.save()

            cs.winner_found = True
            cs.save()

    return 'success'

def update_consts(df):

    for row in df.index:

        const = df.loc[row,'Name']
        constObj = CONSTITUENCY.objects.get(name=const)

        constObj.orig_preds = df.loc[row,'Original Predecessors']
        constObj.abolished = df.loc[row,'Abolished']
        constObj.successors = df.loc[row,'Successors']
        constObj.recreated = df.loc[row,'Re-created']
        constObj.predecessors = df.loc[row,'Predecessors']
        constObj.prev_names = df.loc[row,'Previous Name']
        constObj.name_changed = df.loc[row,'Changed']
        constObj.four_mps = df.loc[row,'4 MPs']
        constObj.three_mps = df.loc[row,'3 MPs']
        constObj.two_mps = df.loc[row,'2 MPs']
        constObj.alternating = df.loc[row, 'Alt']
        constObj.save()

def check_historic_const():

    known_missing = ['Lancashire','Shropshire','Hampshire','[Irish Free State]','Sussex','Kent','Gloucestershire','Clackmannanshire','Kinross-shire','Worcestershire',
    'Norfolk','Bletchingley','Gatton','Surrey','County Durham','Elginshire','Nairnshire','Linlithgow Burghs','Yorkshire','Newtown','Cheshire','Glasgow Burghs','Dysart Burghs',
    'Devon','Essex','Warwickshire','Wiltshire','Cornwall','Penryn','Aberdeen Burghs','Perth Burghs','Derbyshire','Leicestershire','Northamptonshire','Staffordshire','Suffolk',
    'Cumberland','Ross-shire','Cromartyshire','Anstruther Burghs','Higham Ferrers','Somerset','Tain Burghs','Lincolnshire','Northumberland',"Bishop's Castle",'Clyde Burghs',
    'Bossiney','Callington','Camelford','East Looe','Lostwithiel','St Germans','Saltash','West Looe','St Mawes','Nottinghamshire','Aldeburgh','Dunwich','Orford','Haslemere',
    'County Donegal','County Down','Dublin County','County Fermanagh','County Kerry','County Kildare','County Mayo','County Meath','County Monaghan','County Roscommon','County Tipperary','County Tyrone','County Wicklow']
    all_consts = CONSTITUENCY.objects.all()
    count = 0
    no_const = []

    for const in all_consts:
        count += 1
        const_fields = [const.orig_preds.split('|'),const.successors.split('|'),const.predecessors.split('|')]
        related_consts = []

        for const_list in const_fields:
            for r_const in const_list:
                for r in r_const.split('/'):
                    if r == '':
                        continue
                    if r in known_missing:
                        continue
                    related_consts.append(r)

        for r_const in related_consts:

            if not get_const_object(r_const):
                #no_const.append(r_const)
                return const.name + ': ' + r_const + ' not found ' + str(count) + '/' + str(len(all_consts))

    return 'Success'

def update_election_list(df):

    df = df[['Year','Constituency']]
    df.drop_duplicates(inplace=True,ignore_index=True)

    for row in df.index:
        const = df.loc[row,'Constituency']
        election = str(df.loc[row,'Year'])

        const_obj = get_const_object(const)

        if not const_obj:
            return 'Const not found: ' + const

        election_list = const_obj.election_list.split(',')
        if election not in election_list:
            election_list.append(election)
            const_obj.election_list = ','.join(election_list)
            const_obj.save()

        try:
            CONSTSEATS.get(constituency=const_obj, election=ELECTION.objects.get(year=election))
        except:
            cs = CONSTSEATS(constituency=const_obj,
                           election=ELECTION.objects.get(year=election),
                           name=const,
                           seats=1)
            cs.save()

    return 'Success'

def siteadmin(request):
    '''
        View for the admin page
    '''

    status = 'No function run'

    if request.method == 'POST':

        #status = check_historic_const()

        myfile = request.FILES['myfile']
        #region_df = pd.read_excel(myfile,sheet_name="Regions")
        #county_df = pd.read_excel(myfile,sheet_name="Counties")
        #party_df = pd.read_excel(myfile,sheet_name="Parties")
        #election_df = pd.read_excel(myfile,sheet_name="Elections")
        #const_df = pd.read_excel(myfile,sheet_name="Const_sum")
        #results_df = pd.read_excel(myfile,sheet_name="Const_full")
        #results_df.fillna('',axis=1,inplace=True)
        #update_consts(const_df)
        #parse_regions(region_df)
        #parse_counties(county_df)
        #parse_parties(party_df)
        #parse_elections(election_df)
        #parse_consts(const_df)
        #status = update_election_list(results_df)
        #if status == 'Success':
        #parse_results(results_df)
        status = find_winners()
        #parse_results(results_df,byelection_run=True)
        # byelections = list(set(results_df.YearConst))
        # for byelection in byelections:
        #     results = results_df[results_df.YearConst == byelection].to_dict('records')
        #     status = parse_byelection(results)
        #     if status != 'success':
        #         break

    return render(request, "uk_elections/siteadmin.html", {'status':status})
