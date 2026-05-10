"""URL configuration for the alerts demo app."""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('alerts/', views.AlertListView.as_view(), name='alert_list'),
    path('alerts/create/', views.AlertCreateView.as_view(), name='alert_create'),
    path('alerts/<int:pk>/', views.AlertDetailView.as_view(), name='alert_detail'),
    path('alerts/<int:pk>/evaluate/', views.AlertEvaluateView.as_view(), name='alert_evaluate'),
    path('rules/', views.RuleListView.as_view(), name='rule_list'),
    path('rules/test/', views.RuleTestView.as_view(), name='rule_test'),
]