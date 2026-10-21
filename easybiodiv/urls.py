from django.contrib import admin
from django.urls import path, include
from django.views.i18n import JavaScriptCatalog

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('imports/', include('imports.urls')),
    # Bascule FR/EN (vue set_language, POST) et catalogue de traductions JS.
    path('i18n/', include('django.conf.urls.i18n')),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    path('', include('dashboard.urls')),
]
