from django.urls import path
from . import views

app_name = 'imports'

urlpatterns = [
    path('', views.index, name='index'),
    path('template/', views.download_template, name='download_template'),
    path('upload/', views.upload, name='upload'),
    path('preview/', views.preview, name='preview'),
    path('confirm/', views.confirm, name='confirm'),
]
