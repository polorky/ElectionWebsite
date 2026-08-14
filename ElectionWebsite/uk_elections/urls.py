from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    #path('fixtures/<str:pagename>', views.fixtures, name='fixtures'),
    #path('fixtures/<str:pagename>/<status>', views.fixupdate, name='fixupdate'),
    path('elections/<str:election>', views.electionView, name='elections'),
    path('elections/<str:election>/<str:map_type>', views.electionView, name='elections'),
    path('constituencies/<str:const>', views.constituencyView, name='consts'),
    path('counties/<str:county>', views.countyView, name='counties'),
    path('sources', views.sourcesView, name='sources'),
    path('siteadmin', views.siteadmin, name='siteadmin'),
    path('siteadmin/hexeditor', views.hexeditor, name='hexeditor'),
    path('siteadmin/hexeditor/save', views.hexeditor_save, name='hexeditor_save'),
    path('parliamentapi', views.parliamentapi, name='parliamentapi'),
    path('siteadmin/hop-import', views.hop_import_list, name='hop_import_list'),
    path('siteadmin/hop-import/<str:slug>', views.hop_import_preview, name='hop_import_preview'),
    path('validate/', views.validate_election_select, name='validate_election_select'),
    path('validate/<int:election_id>/', views.validate_election, name='validate_election'),
    path('validate/<int:election_id>/<int:constituency_id>/', views.validate_constituency, name='validate_constituency'),
    path('boundaries', views.boundaryChangesView, name='boundaries'),
    path('people/<str:person>', views.peopleView, name='people'),
    path('', TemplateView.as_view(template_name="uk_elections/ukhome.html", extra_context={'active_nav': 'home'}), name='home'),
]
