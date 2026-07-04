# GeoJSON name → DB name corrections (where the boundary file uses a different spelling)
GEOJSON_NAME_MAP = {
    'North Swindon':    'Swindon North',
    'South Swindon':    'Swindon South',
    'Richmond (Yorks)': 'Richmond (Yorkshire)',
    "Ealing Acton and Shepherd's Bush": "Ealing, Acton and Shepherd's Bush",
    'Angus East': 'East Angus'
}


# Template for the text to be displayed when a constituency is clicked on the map
def _build_results_html_js(name_expr, res_expr, year_expr):
    """Returns a JS snippet that builds the results HTML into a variable called `html`,
    using the given JS expressions for name, results object, and election year."""
    return f"""
          const _name = {name_expr};
          const _res = {res_expr};
          const _year = {year_expr};
          const _seats = Object.values(_res['Elected']).filter(e => e).length;
          let html = "<style>table{{font-family:arial,sans-serif;border-collapse:collapse;width:60%;}}";
          html += "td{{border:0.5px solid #000;text-align:left;padding:1px 5px;}}";
          html += "th{{border:0.5px solid #000;text-align:center;padding:1px 5px;}}</style>";
          html += "<h2>" + _name + "</h2><h3>" + _year + " General Election Results</h3><br>";
          html += "<b>Winning Party:</b> " + _res['Party'][0] + "<br><br>";
          if (_seats > 1) html += "<p><em>" + _seats + "-seat constituency</em></p>";
          html += "<table><tr><th style='width:1px;'> </th><th>Party</th><th>Candidate</th>";
          html += "<th style='width:60px;'>Votes</th><th style='width:60px;'>Percent</th></tr>";
          const _pl = _res['Party'];
          for (let i = 0; i < Object.keys(_pl).length; i++) {{
            html += "<tr><td style='width:1px;background-color:" + _res['Party Colour'][i] + ";'> </td>";
            html += "<td>" + _res['Party'][i] + "</td><td>" + _res['Candidate'][i] + "</td>";
            if (_res['Votes'][i] === null) {{
              html += "<td colspan='2' style='text-align:center;font-style:italic;'>Unopposed</td>";
            }} else {{
              html += "<td style='width:60px;'>" + _res['Votes'][i] + "</td>";
              html += "<td style='width:60px;'>" + _res['Percent'][i] + "</td>";
            }}
            html += "</tr>";
          }}
          html += "</table><br><p><a href='/uk/constituencies/" + _name + "'>Constituency Page</a>";
    """


BOKEH_DISPLAY_TEXT = """
          const idx = cb_obj.indices[0];
          if (idx === undefined) return;
          """ + _build_results_html_js(
    "cds.data['name'][idx]",
    "cds.data['results'][idx]",
    "election",
) + """
          const panel = document.getElementById('map-results');
          if (panel) panel.innerHTML = html;
       """