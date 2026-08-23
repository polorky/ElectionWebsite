from django.urls import path
from . import views
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required

urlpatterns = [
    #path('fixtures/<str:pagename>', views.fixtures, name='fixtures'),
    #path('fixtures/<str:pagename>/<status>', views.fixupdate, name='fixupdate'),
    path('elections/<str:election>', views.electionView, name='elections'),
    path('elections/<str:election>/<str:map_type>', views.electionView, name='elections'),
    path('constituencies/<str:const>', views.constituencyView, name='consts'),
    path('counties/<str:county>', views.countyView, name='counties'),
    path('sources', views.sourcesView, name='sources'),
    path('siteadmin', login_required(views.siteadmin), name='siteadmin'),
    path('siteadmin/hexeditor', login_required(views.hexeditor), name='hexeditor'),
    path('siteadmin/hexeditor/save', login_required(views.hexeditor_save), name='hexeditor_save'),
    path('parliamentapi', views.parliamentapi, name='parliamentapi'),
    path('siteadmin/hop-import', login_required(views.hop_import_list), name='hop_import_list'),
    path('siteadmin/hop-import/<str:slug>', login_required(views.hop_import_preview), name='hop_import_preview'),
    path('validate/', login_required(views.validate_election_select), name='validate_election_select'),
    path('validate/<int:election_id>/', login_required(views.validate_election), name='validate_election'),
    path('validate/<int:election_id>/<int:constituency_id>/', login_required(views.validate_constituency), name='validate_constituency'),
    path('boundaries', views.boundaryChangesView, name='boundaries'),
    path('people/<str:person>', views.peopleView, name='people'),
    path('', TemplateView.as_view(template_name="uk_elections/ukhome.html", extra_context={'active_nav': 'home'}), name='home'),
]
