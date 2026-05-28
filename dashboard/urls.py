from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
]
