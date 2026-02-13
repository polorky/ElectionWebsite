from .models import Election
from datetime import datetime
from django.utils import timezone


def get_date_from_election_year_string(year_str):

    try:
        election = Election.objects.get(year=str(year_str))
        return election.date
    except:
        # Return a timezone-aware datetime to match Election.date
        dt = datetime(int(str(year_str)), 1, 1)
        try:
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except Exception:
            return dt