from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('esg-data/', views.esg, name='esg'),
    path('api/company/<int:pk>/esg-data/', views.esg_data, name='esg_data'),
    path('api/company/<int:pk>/esg-market/', views.esg_market, name='esg_market'),
    path('api/company/<int:pk>/', views.company_data, name='company_data'),
    path('mesure-empreinte/', views.mesure_empreinte, name='mesure_empreinte'),
    path('api/company/<int:pk>/mesure-empreinte/', views.mesure_empreinte_data, name='mesure_empreinte_data'),
    path('leap/locate/', views.leap_locate, name='leap_locate'),
    path('api/company/<int:pk>/leap-locate/', views.leap_locate_data, name='leap_locate_data'),
    path('leap/evaluate/', views.leap_evaluate, name='leap_evaluate'),
    path('leap/prepare/', views.leap_prepare, name='leap_prepare'),
    path('dependencies/', views.dependencies, name='dependencies'),
    path('api/company/<int:pk>/dependencies/', views.dependencies_data, name='dependencies_data'),
    path('physical-risk/', views.physical_risk, name='physical_risk'),
    path('api/company/<int:pk>/physical-risk/', views.physical_risk_data, name='physical_risk_data'),
    path('dette-ecologique/', views.dette_ecologique, name='dette_ecologique'),
    path('api/company/<int:pk>/dette-ecologique/', views.dette_ecologique_data, name='dette_ecologique_data'),
    path('compare/', views.compare, name='compare'),
    path('api/company/<int:pk>/compare/', views.compare_data, name='compare_data'),
    path('compliance/', views.compliance, name='compliance'),
    path('api/company/<int:pk>/compliance/', views.compliance_data, name='compliance_data'),
]
