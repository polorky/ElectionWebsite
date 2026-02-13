from django.db import models

class Region(models.Model):

    name = models.CharField(max_length=30)

    def __str__(self):
        return self.name

class County(models.Model):

    name = models.CharField(max_length=30)
    region = models.ForeignKey(Region,on_delete=models.CASCADE)
    colour = models.CharField(max_length=7,blank=True,null=True)

    def __str__(self):
        return self.name

class Party(models.Model):

    name = models.CharField(max_length=255)
    colour = models.CharField(max_length=7)
    cScale = models.CharField(max_length=255)
    parent = models.ForeignKey('self',on_delete=models.CASCADE,blank=True,null=True)

    def __str__(self):
        return self.name

class Constituency(models.Model):
    '''
    Class for UK constituencies
    '''
    name = models.CharField(max_length=255)
    alt_name = models.CharField(max_length=255,blank=True,null=True)
    modern_county = models.ManyToManyField(County, related_name='modern_county')
    historic_county = models.ManyToManyField(County, related_name='historic_county')
    start_date = models.TextField(default=None,null=True,blank=True)
    end_date = models.TextField(default=None,null=True,blank=True)
    seats = models.IntegerField(default=1)
    alternating = models.TextField(default=None,null=True,blank=True)

    # Self-referential relationship for succession
    predecessors = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='successors',
        blank=True,
        help_text="Constituencies this one was created from or replaced"
    )

    def __str__(self):
        return f'{self.name} ({self.start_date} - {self.end_date} - Seats: {self.seats})'

    def get_current_mps(self, date):

        nearest_lower_date = ''
        nearest_election = ''

        for election in Election.objects.all():
            if election.date.replace(tzinfo=None) > date:
                continue
            elif not nearest_lower_date:
                nearest_election = election
                nearest_lower_date = election.date.replace(tzinfo=None)
            elif election.date.replace(tzinfo=None) > nearest_lower_date:
                nearest_election = election
                nearest_lower_date = election.date.replace(tzinfo=None)

        results = CandidateResult.objects.filter(constituency=self).filter(election=nearest_election).filter(elected=True)
        mps = [result.candidate for result in results]

        return mps         

class Election(models.Model):
    '''
    Class for general elections
    '''
    type = models.CharField(max_length=20, choices=(('GE', 'General Election'), ('BE', 'By-Election')))
    date = models.DateTimeField()
    endDate = models.DateTimeField(blank=True,null=True)
    turnout_votes = models.FloatField(blank=True,null=True)
    turnout_percent = models.FloatField(blank=True,null=True)
    notes = models.TextField(blank=True,null=True)

    # For general elections only
    year = models.CharField(max_length=4,blank=True,null=True)
    largest_party = models.TextField(blank=True,null=True)
    prime_minister = models.TextField(blank=True,null=True)
    second_party = models.TextField(blank=True,null=True)
    opp_leader = models.TextField(blank=True,null=True)
    map = models.CharField(max_length=20,blank=True,null=True)
    hex = models.CharField(max_length=20,blank=True,null=True)

    # For byelections only
    constituency = models.ForeignKey(
        Constituency, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Only for by-elections"
    )
    oldMP = models.CharField(max_length=100,blank=True,null=True)

    def __str__(self):
        return f"{'General Election' if self.type == 'GE' else 'By-Election'} - {self.year if self.type == 'GE' else f'{self.constituency.name} {self.date}'}"

class Coalition(models.Model):

    name = models.CharField(max_length=50)
    elections = models.ManyToManyField(Election,blank=True)
    parties = models.ManyToManyField(Party,blank=True)

    def __str__(self):
        return self.name

class ConstituencyResult(models.Model):
    '''
    Class to record constituency-level results for an election
    '''

    constituency = models.ForeignKey(Constituency, on_delete=models.CASCADE)
    election = models.ForeignKey(Election, on_delete=models.CASCADE)
    turnout_votes = models.IntegerField(blank=True,null=True)
    turnout_percent = models.FloatField(blank=True,null=True)    
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        return f'{self.election.type} Result {self.election.year if self.election.type == "GE" else self.election.date} - {self.constituency.name}'

class CandidateResult(models.Model):
    '''
    Class to record results for each candidate in an election
    '''
    
    constituency = models.ForeignKey(Constituency, on_delete=models.CASCADE)
    election = models.ForeignKey(Election, on_delete=models.CASCADE)    
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    candidate = models.CharField(max_length=100)
    votes = models.IntegerField(blank=True,null=True)
    percent = models.FloatField(blank=True,null=True)
    unopposed = models.BooleanField(default=False)
    elected = models.BooleanField(default=False)
    disqualified = models.BooleanField(default=False)
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        return f'{self.election.type} Result {self.election.year if self.election.type == "GE" else self.election.date} - {self.constituency.name} - {self.candidate} ({self.party.name})'
