"""
Demo views showcasing django-eval integration.

These views demonstrate:
1. How to evaluate rules against model instances
2. How to display rule engine results in templates
3. How to test rules with custom contexts
"""
from typing import Any

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.contrib import messages

from eval_engine.configurable_rule_engine import ConfigurableRuleEngine
from eval_engine.models import RuleConfig

from .models import Alert
from .utils import evaluate_alert_push


class DashboardView(View):
    """Main dashboard showing system overview."""

    def get(self, request):
        total_alerts = Alert.objects.count()
        pushed_alerts = Alert.objects.filter(pushed=True).count()
        total_rules = RuleConfig.objects.filter(is_active=True).count()

        context = {
            'total_alerts': total_alerts,
            'pushed_alerts': pushed_alerts,
            'total_rules': total_rules,
        }
        return render(request, 'alerts/dashboard.html', context)


class AlertListView(ListView):
    """List all alerts with their push status."""

    model = Alert
    template_name = 'alerts/alert_list.html'
    context_object_name = 'alerts'
    paginate_by = 20


class AlertCreateView(CreateView):
    """Create a new alert and optionally evaluate it."""

    model = Alert
    template_name = 'alerts/alert_form.html'
    fields = [
        'alert_id', 'title', 'severity', 'source',
        'business_id', 'alert_count_1h', 'alert_count_1d',
        'predicted_weight', 'associate_count', 'content',
    ]
    success_url = reverse_lazy('alert_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Alert '{self.object.title}' created successfully.")
        return response


class AlertDetailView(DetailView):
    """Show alert details with rule evaluation result."""

    model = Alert
    template_name = 'alerts/alert_detail.html'
    context_object_name = 'alert'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        alert = self.object

        # Show the context that would be passed to the rule engine
        context['rule_context'] = alert.to_context()

        # Show evaluation result if already evaluated
        if alert.pushed:
            context['evaluation_result'] = {
                'should_push': True,
                'channel': alert.push_channel,
                'reason': alert.push_reason,
            }

        return context


class AlertEvaluateView(View):
    """Evaluate an alert against the rule engine and update its push status."""

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk)

        # Evaluate using django-eval
        result = evaluate_alert_push(alert)

        # Update alert based on evaluation
        alert.pushed = result['should_push']
        alert.push_channel = result.get('channel', '')
        alert.push_reason = result.get('reason', '')
        alert.save()

        messages.success(
            request,
            f"Alert evaluated: {'PUSHED' if result['should_push'] else 'SUPPRESSED'} "
            f"via {result.get('channel', 'N/A')} (latency: {result.get('latency_ms', 0):.2f}ms)"
        )
        return redirect('alert_detail', pk=alert.pk)


class RuleListView(ListView):
    """List active rules from django-eval."""

    model = RuleConfig
    template_name = 'alerts/rule_list.html'
    context_object_name = 'rules'

    def get_queryset(self):
        return RuleConfig.objects.filter(is_active=True).order_by('priority')


class RuleTestView(View):
    """Interactive rule testing page."""

    template_name = 'alerts/rule_test.html'

    def get(self, request):
        rules = RuleConfig.objects.filter(is_active=True).order_by('priority')
        return render(request, self.template_name, {
            'rules': rules,
            'result': None,
        })

    def post(self, request):
        rule_id = request.POST.get('rule_id', '')
        context_json = request.POST.get('context', '{}')

        result = None
        error = None

        try:
            import json
            context = json.loads(context_json)
        except json.JSONDecodeError as e:
            error = f"Invalid JSON context: {e}"
            context = {}

        if not error and rule_id:
            engine = ConfigurableRuleEngine()
            result = engine.test_rule(rule_id, context)

        rules = RuleConfig.objects.filter(is_active=True).order_by('priority')
        return render(request, self.template_name, {
            'rules': rules,
            'selected_rule': rule_id,
            'context_json': context_json,
            'result': result,
            'error': error,
        })