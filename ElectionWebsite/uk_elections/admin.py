from django.contrib import admin
from django import forms
from .models import *

class RegionAdmin(admin.ModelAdmin):
    list_display = ('name',)

class CountyAdmin(admin.ModelAdmin):
    list_display = ('name','region')

class PartyAdmin(admin.ModelAdmin):
    list_display = ('name','parent')

class ConstituencyAdminForm(forms.ModelForm):
    class Meta:
        model = Constituency
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter predecessors to only show constituencies that ended before this one started
        if self.instance.pk:
            # Exclude self
            queryset = Constituency.objects.exclude(pk=self.instance.pk)
            
            # Only show constituencies that ended before this one started
            if self.instance.start_date:
                queryset = queryset.filter(end_date__lt=self.instance.start_date)
            
            self.fields['predecessors'].queryset = queryset
        else:
            # For new constituencies, show all except those without an end date
            self.fields['predecessors'].queryset = Constituency.objects.filter(end_date__isnull=False)

class ConstituencyAdmin(admin.ModelAdmin):
    list_display = ('name','start_date','seats','get_predecessors_display')
    list_filter = ['name']
    #form = ConstituencyAdminForm
    #filter_horizontal = ['predecessors']
    
    readonly_fields = ['get_predecessors','get_successors']

    def get_predecessors_display(self, obj):
        """Show predecessors in list view"""
        predecessors = obj.predecessors.all()[:3]  # Limit to first 3
        if predecessors:
            return ", ".join([p.name for p in predecessors])
        return "-"
    get_predecessors_display.short_description = 'Predecessors'

    def get_predecessors(self, obj):
        if obj.pk:
            return ", ".join([str(s) for s in obj.predecessors.all()])
        return "None"
    get_predecessors.short_description = 'Predecessors'

    def get_successors(self, obj):
        if obj.pk:
            return ", ".join([str(s) for s in obj.successors.all()])
        return "None"
    get_successors.short_description = 'Successors'

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

