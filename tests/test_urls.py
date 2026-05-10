from django.urls import path, include

urlpatterns = [
    path('api/eval-engine/', include('eval_engine.urls')),
]