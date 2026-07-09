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
    list_display = ('name','api_names','formatted_start_date','formatted_end_date','seats','get_predecessors_display','get_modern_county_display')
    list_filter = ['name', 'modern_county']
    #form = ConstituencyAdminForm
    #filter_horizontal = ['predecessors']
    
    readonly_fields = ['get_predecessors','get_successors']

    def formatted_start_date(self, obj):
        return obj.start_date.strftime('%Y/%m/%d') if obj.start_date else "None"
    formatted_start_date.short_description = 'Start Date'
    formatted_start_date.admin_order_field = 'start_date'

    def formatted_end_date(self, obj):
        return obj.end_date.strftime('%Y/%m/%d') if obj.end_date else "Present"
    formatted_end_date.short_description = 'End Date'
    formatted_end_date.admin_order_field = 'end_date' 

    def get_modern_county_display(self, obj):
        counties = obj.modern_county.all()
        if counties:
            return ", ".join([c.name for c in counties])
        return "-"
    get_modern_county_display.short_description = 'Modern County'

    def get_predecessors_display(self, obj):
        """Show predecessors in list view"""
        predecessors = obj.predecessors.all()[:3]  # Limit to first 3
        if predecessors:
            return ", ".join([p.name for p in predecessors])
        return "-"
    get_predecessors_display.short_description = 'Predecessors'

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'predecessors':
            kwargs['queryset'] = Constituency.objects.order_by('name')
        return super().formfield_for_manytomany(db_field, request, **kwargs)

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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'party':
            kwargs['queryset'] = Party.objects.order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

admin.site.register(Region, RegionAdmin)
admin.site.register(County, CountyAdmin)
admin.site.register(Party, PartyAdmin)
admin.site.register(Constituency, ConstituencyAdmin)
admin.site.register(Election, ElectionAdmin)
admin.site.register(Coalition, CoalitionAdmin)
admin.site.register(ConstituencyResult, ConstituencyResultAdmin)
admin.site.register(CandidateResult, CandidateResultAdmin)

