from django.contrib import admin
from .models import REGION, COUNTY, PARTY, ELECTION, ELECTIONSEATS, COALITION
from .models import CONSTITUENCY, CONSTINSTANCE, CONSTSEATS, BYELECTION
from .models import GENERALRESULT, BYRESULT, GENERALTURNOUT, BYTURNOUT

class PartyAdmin(admin.ModelAdmin):
    list_display = ('name','parent')

class RegionAdmin(admin.ModelAdmin):
    list_display = ('name',)

class CountyAdmin(admin.ModelAdmin):
    list_display = ('name','region')

class ElectionAdmin(admin.ModelAdmin):
    list_display = ('year',)

class ElectionSeatsAdmin(admin.ModelAdmin):
    list_display = ('election','party','seats')

class CoalitionAdmin(admin.ModelAdmin):
    list_display = ('name',)

class ConstituencyAdmin(admin.ModelAdmin):
    list_display = ('name','originally_created','modern_county','historic_county')
    list_filter = ['name']

class ConstInstanceAdmin(admin.ModelAdmin):
    list_display = ('constituency','created','abolished')

class ConstSeatsAdmin(admin.ModelAdmin):
    list_display = ('constituency','election','name','seats')
    list_filter = ['constituency','election']
    list_editable = ['seats','winner_found']

class ByelectionAdmin(admin.ModelAdmin):
    list_display = ('constituency','date','oldMP')
    list_filter = ['constituency']

class GeneralResultAdmin(admin.ModelAdmin):
    list_display = ('constituency','election','party','candidate','votes','percent','unopposed','elected','disqualified')
    list_filter = ['constituency','election']

class ByResultAdmin(admin.ModelAdmin):
    list_display = ('byelection','party','candidate','votes','percent','unopposed','elected','disqualified')
    list_filter = ['byelection__constituency']

class GeneralTurnoutAdmin(admin.ModelAdmin):
    list_display = ('constituency','election','votes','percent')
    list_filter = ['constituency','election']

class ByTurnoutAdmin(admin.ModelAdmin):
    list_display = ('byelection','votes','percent')
    list_filter = ['byelection__constituency']

admin.site.register(PARTY, PartyAdmin)
admin.site.register(REGION, RegionAdmin)
admin.site.register(COUNTY, CountyAdmin)
admin.site.register(ELECTION, ElectionAdmin)
admin.site.register(ELECTIONSEATS, ElectionSeatsAdmin)
admin.site.register(COALITION, CoalitionAdmin)
admin.site.register(CONSTITUENCY, ConstituencyAdmin)
admin.site.register(CONSTINSTANCE, ConstInstanceAdmin)
admin.site.register(CONSTSEATS, ConstSeatsAdmin)
admin.site.register(BYELECTION, ByelectionAdmin)
admin.site.register(GENERALRESULT, GeneralResultAdmin)
admin.site.register(BYRESULT,ByResultAdmin)
admin.site.register(GENERALTURNOUT,GeneralTurnoutAdmin)
admin.site.register(BYTURNOUT,ByTurnoutAdmin)
