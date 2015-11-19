from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^user$', views.user, name='user'),
    url(r'^setpassword$', views.setpassword, name='setpassword'),
    url(r'^erase_library$', views.erase_library, name='erase_library'),
]