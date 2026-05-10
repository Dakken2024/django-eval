"""
Demo models for the alerts application.

These models simulate an alert/notification system that uses
django-eval to decide whether to push alerts to different channels.
"""
from django.db import models


class Alert(models.Model):
    """Represents an alert/notification in the system."""

    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('warning', 'Warning'),
        ('info', 'Info'),
        ('remind', 'Remind'),
    ]

    alert_id = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    source = models.CharField(max_length=100, blank=True)
    business_id = models.CharField(max_length=50, blank=True)
    alert_count_1h = models.PositiveIntegerField(default=0)
    alert_count_1d = models.PositiveIntegerField(default=0)
    predicted_weight = models.FloatField(default=0.0)
    associate_count = models.PositiveIntegerField(default=0)
    content = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    pushed = models.BooleanField(default=False)
    push_channel = models.CharField(max_length=50, blank=True)
    push_reason = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"

    def to_context(self) -> dict:
        """Convert this alert to a rule evaluation context dict."""
        return {
            'severity': self.severity,
            'level': self.severity,
            'alert_count_1h': self.alert_count_1h,
            'alert_count_1d': self.alert_count_1d,
            'predicted_weight': self.predicted_weight,
            'associate_count': self.associate_count,
            'business_id': self.business_id,
            'source_name': self.source,
            'content': self.content,
        }