from django.db import models

class Region(models.Model):

    name = models.CharField(max_length=30)

    def __str__(self):
        return self.name

class County(models.Model):

    name = models.CharField(max_length=30)
    region = models.ForeignKey(Region,on_delete=models.CASCADE)
    colour = models.CharField(max_length=7,blank=True,null=True)

    class Meta:
        verbose_name_plural = 'Counties'

    def __str__(self):
        return self.name

class Party(models.Model):

    name = models.CharField(max_length=255)
    colour = models.CharField(max_length=7)
    cScale = models.CharField(max_length=255,blank=True,null=True)
    parent = models.ForeignKey('self',on_delete=models.CASCADE,blank=True,null=True)

    class Meta:
        verbose_name_plural = 'Parties'

    def __str__(self):
        return self.name

class Constituency(models.Model):
    '''
    Class for UK constituencies
    '''
    name = models.CharField(max_length=255)
    alt_name = models.CharField(max_length=255,blank=True,null=True)
    api_names = models.JSONField(default=list, blank=True)
    hop_name = models.CharField(max_length=255,blank=True,null=True)
    modern_county = models.ManyToManyField(County, related_name='modern_counties')
    historic_county = models.ManyToManyField(County, related_name='historic_counties')
    start_date = models.DateTimeField(default=None,null=True,blank=True)
    end_date = models.DateTimeField(default=None,null=True,blank=True)
    seats = models.IntegerField(default=1)
    alternating = models.CharField(max_length=20,default=None,null=True,blank=True)

    # Self-referential relationship for succession
    predecessors = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='successors',
        blank=True,
        help_text="Constituencies this one was created from or replaced"
    )

    class Meta:
        verbose_name_plural = 'Constituencies'

    def __str__(self):
        return f'{self.name} ({self.start_date.strftime("%Y/%m/%d")} - {self.end_date.strftime("%Y/%m/%d") if self.end_date else "Present"} - Seats: {self.seats})'

    def get_current_mps(self, date):
        # Find the most recent GE with results for this constituency
        last_ge = (
            Election.objects
            .filter(
                type='GE',
                candidateresult__constituency=self,
                candidateresult__elected=True,
                date__date__lte=date,
            )
            .order_by('-date')
            .first()
        )
        if not last_ge:
            return []

        mps = list(
            CandidateResult.objects
            .filter(constituency=self, election=last_ge, elected=True)
            .values_list('candidate', flat=True)
        )

        # Apply any BEs for this constituency that fall between the GE and the given date
        bes = (
            Election.objects
            .filter(
                type='BE',
                constituency=self,
                date__date__gt=last_ge.date.date(),
                date__date__lte=date,
            )
            .order_by('date')
        )
        for be in bes:
            be_winners = list(
                CandidateResult.objects
                .filter(constituency=self, election=be, elected=True)
                .values_list('candidate', flat=True)
            )
            if not be_winners:
                continue
            if be.oldMP:
                old = be.oldMP.strip().lower()
                mps = [mp for mp in mps if mp.strip().lower() if old not in mp]
            mps.extend(be_winners)

        return mps

class Election(models.Model):
    '''
    Class for general elections
    '''
    type = models.CharField(max_length=20, choices=(('GE', 'General Election'), ('BE', 'By-Election')))
    year = models.CharField(max_length=10,blank=True,null=True)
    date = models.DateTimeField()
    endDate = models.DateTimeField(blank=True,null=True)
    turnout_votes = models.IntegerField(blank=True,null=True)
    turnout_percent = models.FloatField(blank=True,null=True)
    alternate = models.IntegerField(default=1)
    notes = models.TextField(blank=True,null=True)
    description = models.TextField(blank=True,null=True)

    # For general elections only
    largest_party = models.CharField(max_length=100,blank=True,null=True)
    prime_minister = models.CharField(max_length=100,blank=True,null=True)
    second_party = models.CharField(max_length=100,blank=True,null=True)
    opp_leader = models.CharField(max_length=100,blank=True,null=True)
    map = models.CharField(max_length=20,blank=True,null=True)
    hex = models.CharField(max_length=20,blank=True,null=True)
    gj = models.CharField(max_length=20,blank=True,null=True)

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

class Person(models.Model):
    HOP_BASE = 'https://www.historyofparliamentonline.org/volume/'

    name    = models.TextField()
    hop_id  = models.CharField(max_length=150, unique=True, null=True, blank=True)
    elected = models.BooleanField(default=False)

    @property
    def hop_url(self):
        return self.HOP_BASE + self.hop_id if self.hop_id else ''

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
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL)
    votes = models.IntegerField(blank=True,null=True)
    percent = models.FloatField(blank=True,null=True)
    unopposed = models.BooleanField(default=False)
    elected = models.BooleanField(default=False)
    disqualified = models.BooleanField(default=False)
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        return f'{self.election.type} Result {self.election.year if self.election.type == "GE" else self.election.date} - {self.constituency.name} - {self.candidate} ({self.party.name})'

    @property
    def candidate_display(self):
        return self.person or self.candidate

class APIValidationRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('clean', 'Clean'),
        ('updated', 'Updated'),
        ('flagged', 'Flagged'),
    ]
    constituency = models.ForeignKey(Constituency, on_delete=models.CASCADE, related_name='validation_records')
    election = models.ForeignKey('Election', on_delete=models.CASCADE, related_name='validation_records')
    checked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('constituency', 'election')

    def __str__(self):
        return f'{self.constituency.name} / {self.election.year} — {self.status}'

