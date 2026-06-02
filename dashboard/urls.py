from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
    path('transition-risk/', views.transition_risk, name='transition_risk'),
    path('api/company/<int:pk>/transition-risk/', views.transition_risk_data, name='transition_risk_data'),
    path('dependencies/', views.dependencies, name='dependencies'),
    path('api/company/<int:pk>/dependencies/', views.dependencies_data, name='dependencies_data'),
    path('physical-risk/', views.physical_risk, name='physical_risk'),
    path('api/company/<int:pk>/physical-risk/', views.physical_risk_data, name='physical_risk_data'),
]
