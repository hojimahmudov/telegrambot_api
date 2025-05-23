"""
URL configuration for backend_config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# backend_config/urls.py
from django.conf import settings
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # API ilovasining URL'larini /api/v1/ prefiksi bilan qo'shamiz
    path('api/v1/', include('api.urls')),  # <-- Shu qatorni qo'shing
]

# --- DEBUG TOOLBAR URL'LARINI QO'SHISH ---
if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [
                          path('__debug__/', include(debug_toolbar.urls)),
                      ] + urlpatterns
    except ImportError:
        pass
