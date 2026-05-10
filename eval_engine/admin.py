from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from .models import RuleConfig, RuleVersionHistory


class RuleVersionHistoryInline(admin.TabularInline):
    """Read-only inline display of rule version history."""
    model = RuleVersionHistory
    extra = 0
    readonly_fields = ('version', 'changed_by', 'change_comment', 'created_at')
    can_delete = False
    max_num = 0
    ordering = ('-version',)
    fields = ('version', 'changed_by', 'change_comment', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RuleConfig)
class RuleConfigAdmin(admin.ModelAdmin):
    """Admin interface for RuleConfig with custom templates for testing and field schema."""

    list_display = (
        'rule_id', 'rule_name', 'rule_type', 'engine_type', 'scope',
        'priority', 'is_active', 'version', 'updated_at'
    )
    list_filter = ('rule_type', 'engine_type', 'scope', 'is_active')
    search_fields = ('rule_id', 'rule_name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'version')
    inlines = [RuleVersionHistoryInline]
    change_form_template = 'eval_engine/admin/ruleconfig/change_form.html'
    change_list_template = 'eval_engine/admin/ruleconfig/change_list.html'

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('rule_id', 'rule_name', 'rule_type', 'engine_type', 'description')
        }),
        (_('Scope & Priority'), {
            'fields': (
                'scope', 'priority', 'is_active',
                'business_id', 'business_group', 'category_key', 'user_id'
            )
        }),
        (_('Rule Content'), {
            'fields': ('rule_content',),
            'description': _(
                'Define rule content in JSON format. Supports "decision_table" '
                'and "simpleeval" formats. Use the Quick Rule Test panel below to validate.'
            )
        }),
        (_('Metadata'), {
            'fields': ('version', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['activate_rules', 'deactivate_rules']

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.append('rule_id')
        return readonly

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('ruleversionhistory_set')

    @admin.action(description=_('Activate selected rules'))
    def activate_rules(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, _('%(count)d rule(s) activated.') % {'count': updated})

    @admin.action(description=_('Deactivate selected rules'))
    def deactivate_rules(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, _('%(count)d rule(s) deactivated.') % {'count': updated})


@admin.register(RuleVersionHistory)
class RuleVersionHistoryAdmin(admin.ModelAdmin):
    """Read-only admin for viewing rule version history."""

    list_display = ('rule_id', 'version', 'changed_by', 'create_time')
    list_filter = ('rule_id',)
    search_fields = ('rule_id', 'changed_by')
    readonly_fields = (
        'rule_id', 'version', 'rule_content',
        'changed_by', 'change_comment', 'create_time'
    )

    def create_time(self, obj):
        return obj.created_at
    create_time.short_description = _('Created At')
    create_time.admin_order_field = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False