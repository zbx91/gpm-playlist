from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^user$', views.user, name='user'),
    url(r'^setpassword$', views.setpassword, name='setpassword'),
    url(r'^testsongs$', views.testsongs, name='testsongs'),
    url(r'^testssl$', views.testssl, name='testssl'),
    url(r'^load_library$', views.load_library, name='load_library'),
]