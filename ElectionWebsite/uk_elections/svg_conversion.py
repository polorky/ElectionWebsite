from svgpath2mpl import parse_path
import xml.etree.ElementTree as etree

def convert_svg(filename, election):

    def parse_svg(root,election):

        def transform_path(path,transforms,election=''):

            if transforms == 'Shetland':
                a,b,c,d,e,f = [0.7,0,0,0.7,-60,-180]
                # if election == '1997':
                #     a,b,c,d,e,f = [0.7,0,0,0.7,-60,-180]
                # elif election in ['1992','1987','1983']:
                #     a,b,c,d,e,f = [0.3,0,0,0.3,60,-190]
                # elif election == '1979':
                #     a,b,c,d,e,f = [0.7,0,0,0.7,0,-280]
                # elif election == '1970':
                #     a,b,c,d,e,f = [1.5,0,0,1.5,-200,-1000]
                # elif election == '1951':
                #     a,b,c,d,e,f = [0.6,0,0,0.6,60,-190]

                count = 0
                for coords in path.vertices:
                    x = a * coords[0] + c * coords[1] + e
                    y = b * coords[0] + d * coords[1] + f
                    path.vertices[count][0] = x
                    path.vertices[count][1] = y
                    count += 1    
            
            else:
                
                transforms.reverse()
               
                for transform in transforms:
                    
                    if transform[:6] == 'matrix':
                        a,b,c,d,e,f = [float(i) for i in transform[7:-1].split(',')]
                        count = 0
                        for coords in path.vertices:
                            x = a * coords[0] + c * coords[1] + e
                            y = b * coords[0] + d * coords[1] + f
                            path.vertices[count][0] = x
                            path.vertices[count][1] = y
                            count += 1

                    elif transform[:9] == 'translate':
                        coords_split = [float(i) for i in transform[10:-1].split(',')]
                        if len(coords_split) == 2:
                            x_shift, y_shift = coords_split
                        count = 0
                        for coords in path.vertices:
                            x = coords[0] + x_shift
                            y = coords[1] + y_shift
                            path.vertices[count][0] = x
                            path.vertices[count][1] = y
                            count += 1

            return path

        def check_element(paths, names, element, incoming_transform, election):
            
            try:
                transform = incoming_transform.copy()
            except:
                raise ValueError(str(incoming_transform))
            
            if 'transform' in element.keys():
                transform.append(element.attrib['transform'])

            if element.tag != '{http://www.w3.org/2000/svg}path':
                
                for e in element:
                    paths, names = check_element(paths,names,e,transform,election)
            
            else:
                
                if 'd' in element.keys() and element.attrib['d'] != '':

                    path = element.attrib['d']
                    if path[-1] not in ('z','Z') and path[-2] not in ('z','Z'):
                        path = path + 'z'
                    try:
                        parsed = parse_path(path)
                    except:
                        print(element.attrib['id'])
                        parsed = parse_path(path)
                    if 'id' in element.keys():
                        names.append(element.attrib['id'])
                    if 'id' in element.keys() and element.attrib['id'] == 'Orkney and Shetland':
                        parsed = transform_path(parsed,'Shetland',election=election)
                    elif transform:
                        parsed = transform_path(parsed,transform)
                    if parsed:
                        paths.append(parsed)

                    return paths, names

            return paths, names

        tree = etree.parse(filename)
        root = tree.getroot()
        paths = []
        names = []

        for element in root:
            transform = []
            paths, names = check_element(paths, names, element,transform,election)

        return paths, names

    def convert_paths(paths, names, election):

        def convert_path_into_polygons(path,pg_x,pg_y,count=-1):

            if count == -1:

                vertices = path.vertices
                codes = path.codes

                cur_pg = []

                for i in range(0,len(vertices)):
                    if codes[i] == 79:
                        pg_x.append([[c[0] for c in cur_pg]])
                        pg_y.append([[c[1]*-1 for c in cur_pg]]) # multiply by -1 to invert
                        cur_pg = []
                    else:
                        cur_pg.append(vertices[i])

            elif names[count] == 'Milton Keynes North East':

                vertices = []
                vertices += list(path.vertices[:6])
                vertices += list(paths[count+1].vertices[1:10])
                vertices += list(path.vertices[15:])
                codes = [1,]
                codes += [2] * (len(vertices)-2) 
                codes.append(79)

                cur_pg = []
                names[count] = 'Milton Keynes'

                for i in range(0,len(vertices)):
                    if codes[i] == 79:
                        pg_x.append([[c[0] for c in cur_pg]])
                        pg_y.append([[c[1]*-1 for c in cur_pg]]) # multiply by -1 to invert
                        cur_pg = []
                    else:
                        cur_pg.append(vertices[i])

            return pg_x, pg_y

        xs = []
        ys = []
        x_temp = []
        y_temp = []
        anomalies = {}
        count = 0

        for path in paths:

            if names and 'Milton' in names[count] and election in ('1987','1983'):
                x_temp, y_temp = convert_path_into_polygons(path,x_temp,y_temp,count)
                if names[count] == 'Milton Keynes':
                    xs.append(x_temp)
                    ys.append(y_temp)
                x_temp = []
                y_temp = []
            elif names and election in ('1992','1987','1983') and names[count] in ('path4893','Glasgow Central'):
                anomalies[names[count]] = path
            else:    
                x_temp, y_temp = convert_path_into_polygons(path,x_temp,y_temp)
                if not names or count == len(paths)-1 or names[count+1] != names[count]:       
                    xs.append(x_temp)
                    ys.append(y_temp)
                    x_temp = []
                    y_temp = []

            count += 1

        return xs, ys, anomalies

    def correct_glasgow(names,xs,ys,anomalies):

        names.remove('Glasgow Central')
        names.remove('path4893')
        names.append('Glasgow Central')

        vertices = []
        vertices += list(anomalies['path4893'].vertices[0:11])
        vertices += list(anomalies['Glasgow Central'].vertices[0:6])
        vertices += list(anomalies['path4893'].vertices[16:])
        codes = [1,]
        codes += [2] * (len(vertices)-2) 
        codes.append(79)

        cur_pg = []

        for i in range(0,len(vertices)):
            if codes[i] == 79:
                xs.append([[[c[0] for c in cur_pg]]])
                ys.append([[[c[1]*-1 for c in cur_pg]]]) # multiply by -1 to invert
                cur_pg = []
            else:
                cur_pg.append(vertices[i])

        return names, xs, ys

    def check_for_holes(xs, ys, election):

        const_holes = {
            '1951':
                   {'PENRITH AND THE BORDER':['CARLISLE'],
                    'DON VALLEY':['DONCASTER'],
                    'CIRENCESTER AND TEWKESBURY':['CHELTENHAM'],
                    'NORTH SOMERSET':['BATH'],
                    'CAMBRIDGESHIRE':['CAMBRIDGE'],
                    'CENTRAL NORFOLK':['NORWICH NORTH','NORWICH SOUTH']},
            '1970':
                   {'PENRITH AND THE BORDER':['CARLISLE'],
                    'DON VALLEY':['DONCASTER'],
                    'CIRENCESTER AND TEWKESBURY':['CHELTENHAM'],
                    'NORTH SOMERSET':['BATH'],
                    'CAMBRIDGESHIRE':['CAMBRIDGE'],
                    'CENTRAL NORFOLK':['NORWICH NORTH','NORWICH SOUTH']},
            '1979':
                   {'PENRITH AND THE BORDER':['CARLISLE'],
                    'CIRENCESTER AND TEWKESBURY':['CHELTENHAM'],
                    'NORTH SOMERSET':['BATH'],
                    'CAMBRIDGESHIRE':['CAMBRIDGE'],
                    'DAVENTRY':['NORTHAMPTON NORTH','NORTHAMPTON SOUTH']},
            '1992':
                   {'PENRITH AND THE BORDER':['CARLISLE'],
                    'WANSDYKE':['BATH'],
                    'CIRENCESTER AND TEWKESBURY':['CHELTENHAM']},
            '1997':
                   {'NORTH ESSEX':['COLCHESTER']}
                  }

        for key in const_holes.keys():

            if election == key:

                for const_key in const_holes[key].keys():
                    
                    for const in const_holes[key][const_key]:
                        count = 0
                        outer = 0
                        inner = 0
                        
                        for name in names:
                            if name.upper() == const_key:
                                outer = count
                            elif name.upper() == const:
                                inner = count
                            count += 1
                        
                        xs[outer][0].append(xs[inner][0][0])
                        ys[outer][0].append(ys[inner][0][0])

        return xs, ys

    tree = etree.parse(filename)
    root = tree.getroot()
    path_elems = root.findall('.//{http://www.w3.org/2000/svg}path')
    paths, names = parse_svg(root, election)
    
    xs, ys, anomalies = convert_paths(paths, names, election)
    
    if election in ('1987','1983'):
        names.remove('Milton Keynes South West')
        count = 0
        mlcount = 0
        for name in names:
            if name == 'Milton Keynes North East':
                mlcount = count
                print(count)
            count += 1
        names[mlcount] = 'Milton Keynes'
    if election in ('1992','1987','1983'):
        names, xs, ys = correct_glasgow(names,xs,ys,anomalies)
    
    for i in range(len(names)-1,-1,-1):
        if i != 0 and names[i]==names[i-1]:
            names.pop(i)
    
    xs, ys = check_for_holes(xs,ys,election)
    
    return xs, ys, names
