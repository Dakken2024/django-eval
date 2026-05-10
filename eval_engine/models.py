from django.db import models


class RuleConfig(models.Model):
    RULE_ENGINE_CHOICES = [
        ('simpleeval', 'SimpleEval (Expression)'),
    ]
    RULE_TYPE_CHOICES = [
        ('push_decision', 'Push Decision'),
        ('feedback_threshold', 'Feedback Threshold'),
        ('time_window', 'Time Window'),
        ('custom', 'Custom'),
    ]
    SCOPE_CHOICES = [
        ('global', 'Global'),
        ('business', 'Business'),
        ('business_group', 'Business Group'),
        ('category', 'Category'),
        ('user', 'User'),
    ]

    rule_id = models.CharField(max_length=100, primary_key=True, help_text="Rule unique ID")
    rule_name = models.CharField(max_length=200, help_text="Rule name")
    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES, help_text="Rule type")
    engine_type = models.CharField(max_length=20, choices=RULE_ENGINE_CHOICES, default='simpleeval', help_text="Rule engine type")

    rule_content = models.JSONField(blank=True, null=True, help_text="SimpleEval rule content (JSON format)")

    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Priority, smaller number = higher priority")

    business_id = models.CharField(max_length=50, blank=True, db_index=True)
    business_group = models.CharField(max_length=100, blank=True, db_index=True, help_text="Business group for group-level isolation")
    category_key = models.CharField(max_length=100, blank=True, db_index=True)

    threshold_value = models.IntegerField(null=True, blank=True, help_text="Threshold value")
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='global', help_text="Rule scope")
    user_id = models.CharField(max_length=64, blank=True, db_index=True, help_text="Target user (for user-level rules)")

    description = models.TextField(blank=True, help_text="Rule description")
    created_by = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['rule_type', 'is_active']),
            models.Index(fields=['business_id', 'category_key']),
            models.Index(fields=['business_group', 'is_active']),
            models.Index(fields=['scope', 'is_active']),
            models.Index(fields=['user_id', 'category_key']),
        ]
        verbose_name = 'Rule Config'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.rule_name} ({self.rule_id}) [{self.rule_type}]"


class RuleVersionHistory(models.Model):
    rule_id = models.CharField(max_length=100, db_index=True)
    version = models.IntegerField()
    rule_content = models.JSONField(blank=True, null=True)
    changed_by = models.CharField(max_length=64)
    change_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('rule_id', 'version')
        indexes = [
            models.Index(fields=['rule_id', 'created_at']),
        ]
        verbose_name = 'Rule Version History'
        verbose_name_plural = verbose_name