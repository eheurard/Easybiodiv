from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
    path('mesure-empreinte/', views.mesure_empreinte, name='mesure_empreinte'),
    path('api/company/<int:pk>/mesure-empreinte/', views.mesure_empreinte_data, name='mesure_empreinte_data'),
    path('dependencies/', views.dependencies, name='dependencies'),
    path('api/company/<int:pk>/dependencies/', views.dependencies_data, name='dependencies_data'),
    path('physical-risk/', views.physical_risk, name='physical_risk'),
    path('api/company/<int:pk>/physical-risk/', views.physical_risk_data, name='physical_risk_data'),
]
