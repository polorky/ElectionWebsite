import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ElectionWebsite.settings')
django.setup()

from uk_elections.models import Constituency

checks = [
    'Barrow', 'Caernarvon', 'Caernarfon', 'Llanell', 'Richmond', 'Stoke',
    'Durham', 'Wellington', 'Gorton', 'Southgate', 'Cotswold', 'Finsbury',
    'Hammersmith', 'Wolverhampton', 'Middlesbrough', 'Marylebone', 'Huddersfield',
    'Walthamstow', 'Newcastle upon Tyne', 'Kingston upon Hull', 'Aberdeen',
    'Reading', 'Milton Keynes', 'Swindon', 'Bethnal Green', 'Peebles',
    'Pembroke', 'Kinross', 'Southwark', 'Fulham', 'Maldon', 'Colchester',
    'Newington', 'Clackmannan', 'Fylde',
]

for term in checks:
    names = sorted(set(Constituency.objects.filter(name__icontains=term).values_list('name', flat=True)))
    if names:
        print(f'{term}: {names[:8]}{"..." if len(names) > 8 else ""}')
