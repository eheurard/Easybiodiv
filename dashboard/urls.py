from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
    path('transition-risk/', views.transition_risk, name='transition_risk'),
    path('api/company/<int:pk>/transition-risk/', views.transition_risk_data, name='transition_risk_data'),
]
