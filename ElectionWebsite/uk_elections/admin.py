from django.contrib import admin
from .models import *

class RegionAdmin(admin.ModelAdmin):
    list_display = ('name',)

class CountyAdmin(admin.ModelAdmin):
    list_display = ('name','region')

class PartyAdmin(admin.ModelAdmin):
    list_display = ('name','parent')

class ConstituencyAdmin(admin.ModelAdmin):
    list_display = ('name','start_date','seats')
    list_filter = ['name']

class ElectionAdmin(admin.ModelAdmin):
    list_display = ('type','year','date')

class CoalitionAdmin(admin.ModelAdmin):
    list_display = ('name',)

class ConstituencyResultAdmin(admin.ModelAdmin):
    list_display = ('constituency','election')

class CandidateResultAdmin(admin.ModelAdmin):
    list_display = ('constituency','election','party','candidate')
    list_filter = ['constituency','election']

admin.site.register(Region, RegionAdmin)
admin.site.register(County, CountyAdmin)
admin.site.register(Party, PartyAdmin)
admin.site.register(Constituency, ConstituencyAdmin)
admin.site.register(Election, ElectionAdmin)
admin.site.register(Coalition, CoalitionAdmin)
admin.site.register(ConstituencyResult, ConstituencyResultAdmin)
admin.site.register(CandidateResult, CandidateResultAdmin)

