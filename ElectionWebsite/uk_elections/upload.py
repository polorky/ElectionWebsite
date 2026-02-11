import datetime

from ElectionWebsite.uk_elections.views import create_const_seats_db
from .models import *
from.utility_functions import get_date_from_election_year_string

class Uploader:

    def __init__(self, file, datatype):
        self.file = file
        p = Parser(datatype)

class Parser:

    def __init__(self, datatype, df):
        self.datatype = datatype
        self.df = df

    def parse(self):
        return getattr(self, f'parse_{self.datatype}')()
    
    def parse_region(self):

        for row in self.df.index:
            r = Region(name=self.df.loc[row,'Region'])
            r.save()

    def parse_county(self):

        for row in self.df.index:
            try:
                County.objects.get(name=self.df.loc[row,'County'])
            except:
                c = County(name=self.df.loc[row,'County'],
                        region=Region.objects.get(name=self.df.loc[row,'Region']),
                        colour=self.df.loc[row,'Colour'])
                c.save()

    def parse_party(self):

        self.df.fillna('',axis=1,inplace=True)
        for row in self.df.index:
            try:
                Party.objects.get(name=self.df.loc[row,'Party'])
            except:
                if self.df.loc[row,'Main Party'] != '':
                    parent = Party.objects.get(name=self.df.loc[row,'Main Party'])
                else:
                    parent = None

                p = Party(name=self.df.loc[row,'Party'],
                        colour=self.df.loc[row,'Colour'],
                        cScale=self.df.loc[row,'Colour Scale'],
                        parent=parent)
                p.save()

    def parse_general_election(self):

        self.df.fillna('',axis=1,inplace=True)

        for row in self.df.index:
            
            try:
                Election.objects.get(year=self.df.loc[row,'Year'])
            except:
                if isinstance(self.df.loc[row,'Date'],str):
                    startDate, endDate = self.df.loc[row,'Date'].split('-')
                    startDate = datetime.strptime(startDate, "%d/%m/%Y")
                    endDate = datetime.strptime(endDate, "%d/%m/%Y")
                else:
                    startDate = self.df.loc[row,'Date']
                    endDate = None
                e = Election(
                            type='GE',
                            year=self.df.loc[row,'Year'],
                            date=startDate,
                            endDate=endDate,
                            turnout_percent=self.df.loc[row,'Turnout'],
                            largest_party=self.df.loc[row,'Largest Party'],
                            prime_minister=self.df.loc[row,'Prime Minister'],
                            second_party=self.df.loc[row,'Party'],
                            opp_leader=self.df.loc[row,'Losing Leader'],
                            map=self.df.loc[row,'SVG File'],
                            hex=self.df.loc[row,'Hex Col']
                        )
                e.save()

    def parse_constituency(self):

        df = self.df
        df.fillna('',axis=1,inplace=True)
        string_cols = ['Created','Abolished','Re-created','Changed','Changed 2','4 MPs','3 MPs','2 MPs']

        for col in string_cols:
            df[col] = df[col].apply(str)

        for row in df.index:
            modern_county = df.loc[row,'Modern County'],
            historic_county = df.loc[row,'Historic County']
            alt_name = df.loc[row,'Alternative Name']
            alternating = df.loc[row,'Alt']

            # start, end, pred, succ
            events, dates_sorted = self.get_const_instances(df,row)

            creation_details = [dates_sorted[0], *events[dates_sorted[0]]]
            for i, date in enumerate(dates_sorted):
                event = events[date]
                if event[0] == 'abolished':
                    c = Constituency(
                        name=df.loc[row,'Name'],
                        modern_county=County.objects.get(name=modern_county),
                        historic_county=County.objects.get(name=historic_county),
                        alt_name=alt_name,
                        alternating=alternating,
                        start_date=creation_details[0],
                        end_date=date,
                        predecessor=creation_details[2],
                        successor=event[1],
                        seats=creation_details[2]
                    )
                elif event[0] == 'recreated':
                    creation_details = [date, event[0], event[1], event[2]]
                elif event[0] == 'seat_change':
                    c = Constituency(
                        name=df.loc[row,'Name'],
                        modern_county=County.objects.get(name=modern_county),
                        historic_county=County.objects.get(name=historic_county),
                        alt_name=alt_name,
                        alternating=alternating,
                        start_date=creation_details[0],
                        end_date=date,
                        seats=creation_details[2]
                    )
                    creation_details = [date, event[0], df.loc[row,'Name'], event[2]]
            try:
                Constituency.objects.get(name=df.loc[row,'Name'],)
            except:
                electionList = get_election_list(df,row)
                c = CONSTITUENCY(
                        name=df.loc[row,'Name'],
                        modern_county=County.objects.get(name=modern_county),
                        historic_county=County.objects.get(name=historic_county),
                        alt_name=alt_name,
                        alternating=alternating,
                        start_date=creation_details[0],
                        end_date=date,
                        seats=creation_details[2]
                    )
                c.save()
        
        for row in df.index:
            for i, date in enumerate(dates_sorted):
                event = events[date]
                if event[0] == 'abolished':
                    c = Constituency.objects.get(name=df.loc[row,'Name'],start_date=events[dates_sorted[i-1]][0])
                    succ_names = [s.strip() for s in event[1].split('/') if s.strip()]
                    succ_objs = []
                    for successor in succ_names:
                        # try exact match for the given date first
                        obj = Constituency.objects.filter(name=successor, start_date=date).first()
                        # if no exact match, get the most recent start_date before the date
                        if not obj:
                            obj = Constituency.objects.filter(name=successor, start_date__lt=date).order_by('-start_date').first()
                        if obj:
                            succ_objs.append(obj)
                    # keep the original successor string for backward compatibility
                    c.successor.set(succ_objs)
                    c.save()
                elif event[0] == 'recreated':
                    c = Constituency.objects.get(name=df.loc[row,'Name'],start_date=date)
                    prec_names = [p.strip() for p in event[1].split('/') if p.strip()]
                    prec_objs = []
                    for predecessor in prec_names:
                        # try exact match for the given date first
                        obj = Constituency.objects.filter(name=predecessor, start_date=date).first()
                        # if no exact match, get the most recent start_date before the date
                        if not obj:
                            obj = Constituency.objects.filter(name=predecessor, start_date__lt=date).order_by('-start_date').first()
                        if obj:
                            prec_objs.append(obj)
                    c.predecessor.set(prec_objs)
                    c.save()
                elif event[0] == 'seat_change':
                    c = Constituency.objects.get(name=df.loc[row,'Name'],start_date=date)
                    c.seats = event[2]
                    c.save()

    def get_const_instances(self, df, row):
        '''
       Returns a dictionary of events, with date as key and 
       value a list of [event type, predecessor/successor, seats]. 
       Also returns a list of the dates in chronological order.
        '''
        def check_seat_key(events, seats, date):
            if date in events:
                events[date][2] = seats
            else:
                events[date] = ['seat_change','',seats]
            return events

        events = {}

        # Deal with creation and abolition/recreation
        org_preds = df.loc[row,'Original Predecessors']
        preds = df.loc[row,'Predecessors'].split('|')
        succs = df.loc[row,'Successors'].split('|')

        created = get_date_from_election_year_string(df.loc[row,'Created'])
        events[created] = ['created',org_preds,1]

        abolished = [get_date_from_election_year_string(x) for x in df.loc[row,'Abolished'].split('|') if x != '']
        for i, date in enumerate(abolished):
            events[date] = ['abolished',succs[i],1]
        recreated = [get_date_from_election_year_string(x) for x in df.loc[row,'Re-created'].split('|') if x != '']
        for i, date in enumerate(recreated):
            events[date] = ['recreated',preds[i],1]
        
        # Deal with number of seats
        four_mps = [get_date_from_election_year_string(x) for x in df.loc[row,'4 MPs'].split('|') if x != '']
        three_mps = [get_date_from_election_year_string(x) for x in df.loc[row,'3 MPs'].split('|') if x != '']
        two_mps = [get_date_from_election_year_string(x) for x in df.loc[row,'2 MPs'].split('|') if x != '']
        events = check_seat_key(events, 1, four_mps[1])
        events = check_seat_key(events, 1, three_mps[1])
        events = check_seat_key(events, 1, two_mps[1])
        events = check_seat_key(events, 4, four_mps[0])
        events = check_seat_key(events, 3, three_mps[0])
        events = check_seat_key(events, 2, two_mps[0])        

        # Sort events chronologically
        dates_sorted = sorted(events.keys())

        return events, dates_sorted

    def parse_result(self):

        df.fillna('',axis=1,inplace=True)

        filter_df = df[['Year', 'Constituency']].drop_duplicates()

        for row in filter_df.index:
            year = filter_df.loc[row,'Year']
            constituency_name = filter_df.loc[row,'Constituency']
            constituency = Constituency.objects.get(name=constituency_name)
            sub_df = df[(df['Year'] == year) & (df['Constituency'] == constituency_name)]
            num_disqualified = 0

            if 'B' in year:
                be_obj = self.create_byelection(year, constituency, sub_df)

                for row in sub_df.index:
                    if sub_df.loc[row,'Party'] == 'Turnout':
                        continue
                    
                    num_disqualified = self.create_candidate_result(be_obj, constituency, sub_df, row, num_disqualified)

            else:
                election = Election.objects.get(year=year)
                self.create_constituency_result(election, constituency, sub_df)

                for row in sub_df.index:
                    if sub_df.loc[row,'Party'] == 'Turnout':
                        continue
                    
                    num_disqualified = self.create_candidate_result(election, constituency, sub_df, row, num_disqualified)
    
    def create_candidate_result(self, election, constituency, sub_df, row, num_disqualified):

        unopposed = sub_df.loc[row,'Votes'] == 'Unopposed'

        if isinstance(sub_df.loc[row,'Votes'],str) and '*' in sub_df.loc[row,'Votes']:
            votes = sub_df.loc[row,'Votes'].replace('*','')
            disqualified = True
            num_disqualified += 1
        else:
            votes = sub_df.loc[row,'Votes']
            disqualified = False

        notes = sub_df[sub_df['Notes'] != '']['Notes'].values
        if len(notes) > 1:
            raise ValueError(f'Multiple non-empty notes found for {constituency_name} {year}: {notes}')
        elif len(notes) == 0:
            raise ValueError(f'No notes found for {constituency_name} {year}')
        else:
            notes = notes[0]

        elected = not disqualified and (unopposed or row - num_disqualified < constituency.seats)

        CandidateResult.objects.create(
            constituency = constituency,
            election = election,
            party = sub_df.loc[row,'Party'],
            candidate = sub_df.loc[row,'Candidate'],
            votes = votes,
            percent = sub_df.loc[row,'Percent'],
            unopposed = unopposed,
            elected = elected,
            disqualified = disqualified,
            notes = sub_df.loc[row,'Notes']
        )

        return num_disqualified

    def create_constituency_result(self, election, constituency, sub_df):
                
        if 'Turnout' in sub_df['Party'].values:
            turnout_votes = sub_df[sub_df['Party'] == 'Turnout']['Votes'].values[0]
            turnout_percent = sub_df[sub_df['Party'] == 'Turnout']['Percent'].values[0]
        else:
            turnout_votes = None
            turnout_percent = None
            if not (sub_df['Votes'] == 'Unopposed').all():
                raise ValueError(f'No turnout data for {constituency.name} {year}, but not all candidates are unopposed')

        notes = sub_df[sub_df['Notes'] != '']['Notes'].values
        if len(notes) > 1:
            raise ValueError(f'Multiple non-empty notes found for {constituency.name} {year}: {notes}')
        elif len(notes) == 0:
            raise ValueError(f'No notes found for {constituency.name} {year}')
        else:
            notes = notes[0]

        result = ConstituencyResult.objects.create(
            election=election,
            constituency=constituency,
            turnout_votes=turnout_votes,
            turnout_percent=turnout_percent,
            notes=notes
        )
    
    def create_byelection(self,year, constituency, sub_df):

        year = year.replace('BB','').replace('B','')

        if len(year) > 8:
            date = datetime.strptime(year, "%Y %d%b")
        elif len(year) > 4:
            date = datetime.strptime(year, "%Y %b")
        else:
            date = datetime.strptime(year, "%Y")

        if 'Turnout' in sub_df['Party'].values:
            turnout_votes = sub_df[sub_df['Party'] == 'Turnout']['Votes'].values[0]
            turnout_percent = sub_df[sub_df['Party'] == 'Turnout']['Percent'].values[0]
        else:
            turnout_votes = None
            turnout_percent = None
            if not (sub_df['Votes'] == 'Unopposed').all():
                raise ValueError(f'No turnout data for by-election in {constituency_name} {year}, but not all candidates are unopposed')

        notes = sub_df[sub_df['Notes'] != '']['Notes'].values
        if len(notes) > 1:
            raise ValueError(f'Multiple non-empty notes found for {constituency_name} {year}: {notes}')
        elif len(notes) == 0:
            raise ValueError(f'No notes found for {constituency_name} {year}')
        else:
            notes = notes[0]

        current_mps = constituency.get_current_mps(date)
        if ']' in notes:
            oldMP, notes = notes.replace('[','').split(']')
            if oldMP not in [mp.split(' ')[-1] for mp in current_mps]:
                raise ValueError(f'Predecessor MP {oldMP} listed in notes for {constituency_name} {year} not found among current MPs: {current_mps}')
        else:
            oldMP = None
            if constituency.seats > 1:
                raise ValueError(f'No predecessor MP found in notes for {constituency_name} {year}, but constituency has more than 1 seat')
        
        by_election = Election.objects.create(
            type='BE',
            year=year,
            date=date,
            turnout_votes=turnout_votes,
            turnout_percent=turnout_percent,
            notes=notes,
            constituency=constituency,
            oldMP=oldMP
        )

        return by_election

        


