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
                    pass
            try:
                Constituency.objects.get(name=df.loc[row,'Name'],)
            except:
                electionList = get_election_list(df,row)
                c = CONSTITUENCY(
                                name=df.loc[row,'Name'],
                                originally_created=datetime.strptime(df.loc[row,'Created'].split(' ')[0], "%Y"),
                                modern_county=df.loc[row,'Modern County'],
                                historic_county=df.loc[row,'Historic County'],
                                election_list=','.join(electionList),
                                orig_preds = df.loc[row,'Original Predecessors'],
                                abolished = df.loc[row,'Abolished'],
                                successors = df.loc[row,'Successors'],
                                recreated = df.loc[row,'Re-created'],
                                predecessors = df.loc[row,'Predecessors'],
                                prev_name1 = df.loc[row,'Previous Name'],
                                name_changed1 = df.loc[row,'Changed'],
                                prev_name2 = df.loc[row,'Previous Name 2'],
                                name_changed2 = df.loc[row,'Changed 2'],
                                four_mps = df.loc[row,'4 MPs'],
                                three_mps = df.loc[row,'3 MPs'],
                                two_mps = df.loc[row,'2 MPs'],
                                alternating = df.loc[row, 'Alt'],
                                )
                c.save()

                #create_const_instances(df,row,c)
                create_const_seats_db(c)
                #create_const_seats(df,row,c,electionList)

    def get_const_instances(self, df, row):

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
        for date in four_mps:
            events = check_seat_key(events, 4, date)
        three_mps = [get_date_from_election_year_string(x) for x in df.loc[row,'3 MPs'].split('|') if x != '']
        for date in three_mps:
            events = check_seat_key(events, 3, date)
        two_mps = [get_date_from_election_year_string(x) for x in df.loc[row,'2 MPs'].split('|') if x != '']
        for date in two_mps:
            events = check_seat_key(events, 2, date)
        one_mp = [get_date_from_election_year_string(x) for x in df.loc[row,'1 MP'].split('|') if x != '']
        for date in one_mp:
            events = check_seat_key(events, 1, date)

        # Sort events chronologically
        dates_sorted = sorted(events.keys())

        return events, dates_sorted




