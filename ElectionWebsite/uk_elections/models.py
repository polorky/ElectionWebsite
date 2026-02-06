from django.db import models

class REGION(models.Model):

    name = models.CharField(max_length=30)

    def __str__(self):
        return self.name

class COUNTY(models.Model):

    name = models.CharField(max_length=30)
    region = models.ForeignKey(REGION,on_delete=models.CASCADE)
    colour = models.CharField(max_length=7,blank=True,null=True)

    def __str__(self):
        return self.name

class PARTY(models.Model):

    name = models.CharField(max_length=255)
    colour = models.CharField(max_length=7)
    cScale = models.CharField(max_length=255)
    parent = models.ForeignKey('self',on_delete=models.CASCADE,blank=True,null=True)

    def __str__(self):
        return self.name

class ELECTION(models.Model):
    '''
    Class for general elections
    '''
    year = models.CharField(max_length=9)
    startDate = models.DateTimeField()
    endDate = models.DateTimeField(blank=True,null=True)
    turnout = models.FloatField()
    largest_party = models.TextField(blank=True,null=True)
    prime_minister = models.TextField(blank=True,null=True)
    second_party = models.TextField(blank=True,null=True)
    opp_leader = models.TextField(blank=True,null=True)
    map = models.CharField(max_length=20,blank=True,null=True)
    hex = models.CharField(max_length=20,blank=True,null=True)

    def __str__(self):
        return self.year

class ELECTIONSEATS(models.Model):
    '''
    Gives number of seats won by a party at an election
    '''
    election = models.ForeignKey(ELECTION, on_delete=models.CASCADE)
    party = models.ForeignKey(PARTY, on_delete=models.CASCADE)
    seats = models.IntegerField()

    def __str__(self):
        return 'ELECTIONSEATS - ' + self.election.year + ' - ' + self.party.name

class COALITION(models.Model):

    name = models.CharField(max_length=50)
    elections = models.ManyToManyField(ELECTION,blank=True)
    parties = models.ManyToManyField(PARTY,blank=True)

    def __str__(self):
        return self.name

class CONSTITUENCY(models.Model):
    '''
    Class for UK constituencies
    '''
    name = models.CharField(max_length=255)
    originally_created = models.DateTimeField()
    modern_county = models.ForeignKey(COUNTY, on_delete=models.CASCADE, related_name='modern_county')
    historic_county = models.ForeignKey(COUNTY, on_delete=models.CASCADE, related_name='historic_county')
    election_list = models.TextField()
    orig_preds = models.TextField(default=None,null=True,blank=True)
    abolished = models.TextField(default=None,null=True,blank=True)
    successors = models.TextField(default=None,null=True,blank=True)
    recreated = models.TextField(default=None,null=True,blank=True)
    predecessors = models.TextField(default=None,null=True,blank=True)
    prev_name1 = models.TextField(default=None,null=True,blank=True)
    name_changed1 = models.TextField(default=None,null=True,blank=True)
    prev_name2 = models.TextField(default=None,null=True,blank=True)
    name_changed2 = models.TextField(default=None,null=True,blank=True)
    four_mps = models.TextField(default=None,null=True,blank=True)
    three_mps = models.TextField(default=None,null=True,blank=True)
    two_mps = models.TextField(default=None,null=True,blank=True)
    alternating = models.TextField(default=None,null=True,blank=True)

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

class CONSTINSTANCE(models.Model):
    '''
    Continuous period of election for which a constituency existed with predecessors and successors
    '''
    constituency = models.ForeignKey(CONSTITUENCY, on_delete=models.CASCADE)
    created = models.ForeignKey(ELECTION, on_delete=models.CASCADE,related_name='created')
    abolished = models.ForeignKey(ELECTION, on_delete=models.CASCADE, blank=True,null=True,related_name='abolished')
    predecessors = models.TextField(blank=True,null=True)
    successors = models.TextField(blank=True,null=True)

    #def __str__(self):
        #return self.constituency.name + ' - ' + self.created.year + ' to ' + self.abolished.year

class CONSTSEATS(models.Model):
    '''
    Gives number of MPs for a constituency for a given election and its name at that point
    '''
    election = models.ForeignKey(ELECTION,on_delete=models.CASCADE)
    constituency = models.ForeignKey(CONSTITUENCY,on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    seats = models.IntegerField()
    winner_found = models.BooleanField(default=False)

    def __str__(self):
        return 'CONSTSEATS - ' + self.election.year + ' - ' + self.constituency.name

class BYELECTION(models.Model):
    '''
    Class for by-elections
    '''
    constituency = models.ForeignKey(CONSTITUENCY, on_delete=models.CASCADE)
    date = models.DateTimeField()
    oldMP = models.CharField(max_length=100,blank=True,null=True)
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        return 'Byelection - ' + self.constituency.name + ' ' + str(self.date)

class RESULT(models.Model):
    '''
    Class to record candidate level results for general elections
    '''
    party = models.ForeignKey(PARTY, on_delete=models.CASCADE)
    candidate = models.CharField(max_length=100)
    votes = models.IntegerField(blank=True,null=True)
    percent = models.FloatField(blank=True,null=True)
    unopposed = models.BooleanField(default=False)
    elected = models.BooleanField(default=False)
    disqualified = models.BooleanField(default=False)

    class Meta:
        abstract = True

class GENERALRESULT(RESULT):

    constituency = models.ForeignKey(CONSTITUENCY, on_delete=models.CASCADE)
    election = models.ForeignKey(ELECTION, on_delete=models.CASCADE)
    notes = models.TextField(blank=True,null=True)

    def __str__(self):
        return 'Result ' + self.constituency.name + ' - '+ self.election.year

class BYRESULT(RESULT):
    '''
    Class to record candidate level results for byelections
    '''
    byelection = models.ForeignKey(BYELECTION, on_delete=models.CASCADE)

    def __str__(self):
        return 'Byelection Result ' + self.byelection.constituency.name + ' - ' + str(self.byelection.date)

class TURNOUT(models.Model):
    '''
    Class to record turnout and notes for an election and constituency
    '''
    votes = models.IntegerField(blank=True,null=True)
    percent = models.FloatField(blank=True,null=True)
    notes = models.TextField(blank=True,null=True)

    class Meta:
        abstract = True

class GENERALTURNOUT(TURNOUT):

    election = models.ForeignKey(ELECTION, on_delete=models.CASCADE)
    constituency = models.ForeignKey(CONSTITUENCY, on_delete=models.CASCADE)

    def __str__(self):
        return 'Turnout ' + self.constituency.name + ' - '+ self.election.year

class BYTURNOUT(TURNOUT):

    byelection = models.ForeignKey(BYELECTION, on_delete=models.CASCADE)

    def __str__(self):
        return 'Byelection Turnout ' + self.byelection.constituency.name + ' - '+ str(self.byelection.date)

# class HEX(models.Model):
#     '''
#     Class to record hex coordinates for constituencies for each election
#     '''
#     x = models.IntegerField()
#     y = models.IntegerField()
#     z = models.IntegerField()
#     constituency = models.ForeignKey(CONSTITUENCY,on_delete=models.CASCADE)
#     elections = models.ManyToManyField(ELECTION)
