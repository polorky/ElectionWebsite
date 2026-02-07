from .models import Election
from datetime import datetime

def get_date_from_election_year_string(year_str):

    try:
        election = Election.objects.get(year=str(year_str))
        return election.date
    except:
        return datetime(int(year_str),1,1)