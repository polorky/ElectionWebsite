from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    #path('fixtures/<str:pagename>', views.fixtures, name='fixtures'),
    #path('fixtures/<str:pagename>/<status>', views.fixupdate, name='fixupdate'),
    path('elections/<str:election>', views.electionView, name='elections'),
    path('elections/<str:election>/<str:map_type>', views.electionView, name='elections'),
    path('constituencies/<str:const>', views.constView, name='consts'),
    path('siteadmin', views.siteadmin, name='siteadmin'),
    path('', TemplateView.as_view(template_name="uk_elections/ukhome.html"), name='home'),
]
