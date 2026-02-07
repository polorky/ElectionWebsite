from django.db import models

class Region(models.Model):

    name = models.CharField(max_length=30)

    def __str__(self):
        return self.name

class County(models.Model):

    name = models.CharField(max_length=30)
    region = models.ForeignKey(REGION,on_delete=models.CASCADE)
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

class Coalition(models.Model):

    name = models.CharField(max_length=50)
    elections = models.ManyToManyField(ELECTION,blank=True)
    parties = models.ManyToManyField(PARTY,blank=True)

    def __str__(self):
        return self.name

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
        if self.type == 'GE':
            return 'General Election - ' + self.year
        else:
            return 'By-Election - ' + self.constituency.name + ' ' + str(self.date)

class Constituency(models.Model):
    '''
    Class for UK constituencies
    '''
    name = models.CharField(max_length=255)
    alt_name = models.CharField(max_length=255,blank=True,null=True)
    dedupe_name = models.CharField(max_length=255)
    originally_created = models.DateTimeField()
    modern_county = models.ForeignKey(COUNTY, on_delete=models.CASCADE, related_name='modern_county')
    historic_county = models.ForeignKey(COUNTY, on_delete=models.CASCADE, related_name='historic_county')
    election_list = models.TextField()
    created = models.TextField(default=None,null=True,blank=True)
    abolished = models.TextField(default=None,null=True,blank=True)
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
        return self.name

    def get_current_mps(self, date):

        nearest_lower_date = ''
        nearest_election = ''

        for election in ELECTION.objects.all():
            if election.startDate.replace(tzinfo=None) > date:
                continue
            elif not nearest_lower_date:
                nearest_election = election
                nearest_lower_date = election.startDate.replace(tzinfo=None)
            elif election.startDate.replace(tzinfo=None) > nearest_lower_date:
                nearest_election = election
                nearest_lower_date = election.startDate.replace(tzinfo=None)

        results = GENERALRESULT.objects.filter(constituency=self).filter(election=nearest_election).filter(elected=True)
        mps = [result.candidate for result in results]

        return mps

class ConstituencyResult(models.Model):
    '''
    Class to record constituency-level results for an election
    '''

    constituency = models.ForeignKey(CONSTITUENCY, on_delete=models.CASCADE)
    election = models.ForeignKey(ELECTION, on_delete=models.CASCADE)
    turnout_votes = models.IntegerField(blank=True,null=True)
    turnout_percent = models.FloatField(blank=True,null=True)    
    seat_number = models.IntegerField(default=1)
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        if self.election.type == 'GE':
            return f'General Election Result {self.constituency.name} - {self.election.year}'
        else:
            return f'By-Election Result {self.constituency.name} - {self.election.date}'

class CandidateResult(models.Model):
    '''
    Class to record results for each candidate in an election
    '''
    
    constituency = models.ForeignKey(CONSTITUENCY, on_delete=models.CASCADE)
    election = models.ForeignKey(ELECTION, on_delete=models.CASCADE)    
    party = models.ForeignKey(PARTY, on_delete=models.CASCADE)
    candidate = models.CharField(max_length=100)
    votes = models.IntegerField(blank=True,null=True)
    percent = models.FloatField(blank=True,null=True)
    unopposed = models.BooleanField(default=False)
    elected = models.BooleanField(default=False)
    disqualified = models.BooleanField(default=False)
    byelection = models.ForeignKey(ELECTION, on_delete=models.CASCADE)
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        return f'By-Election Result {self.byelection.constituency.name} - {self.byelection.date}'
