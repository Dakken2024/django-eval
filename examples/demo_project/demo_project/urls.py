"""
URL configuration for demo_project.

Includes django-eval URLs and demo app URLs.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # django-eval API endpoints
    path('api/eval-engine/', include('eval_engine.urls')),
    # Demo app views
    path('', include('alerts.urls')),
]