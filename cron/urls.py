from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^autoload_libraries$', views.autoload_libraries, name='autoload_libraries'),
]