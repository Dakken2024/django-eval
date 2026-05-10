# django-eval Demo Project

This is a fully functional example Django project demonstrating how to integrate and use **django-eval** in a real-world application.

## Requirements

- Python 3.10+
- Django 3.2+
- django-eval (installed from parent directory)

## Project Structure

```
demo_project/
├── demo_project/          # Django project settings
│   ├── settings.py        # Project configuration with EVAL_ENGINE_* settings
│   ├── urls.py            # URL routing
│   └── wsgi.py            # WSGI application
├── alerts/                # Demo app - Alert notification system
│   ├── models.py          # Alert model with to_context() method
│   ├── views.py           # Views demonstrating rule engine integration
│   ├── utils.py           # Helper functions for rule evaluation
│   └── urls.py            # App URL configuration
├── templates/             # HTML templates
│   ├── base.html          # Base layout
│   └── alerts/            # App-specific templates
└── manage.py              # Django management script
```

## Quick Start

### 1. Install Dependencies

```bash
# From the django-eval root directory
pip install -e .
pip install djangorestframework
```

### 2. Run Migrations

```bash
cd examples/demo_project
python manage.py migrate
```

### 3. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

### 4. Load Default Rules

```bash
python manage.py init_rules --fixture ../../eval_engine/fixtures/default_rules.json
```

### 5. Run the Server

```bash
python manage.py runserver
```

Visit http://127.0.0.1:8000/ to see the demo dashboard.

## Demo Pages

| URL | Description |
|---|---|
| `/` | Dashboard with stats and quick start guide |
| `/alerts/` | List all alerts with push status |
| `/alerts/create/` | Create a new alert |
| `/alerts/<id>/` | View alert details and evaluation context |
| `/alerts/<id>/evaluate/` | Evaluate alert against rule engine |
| `/rules/` | List active rules from django-eval |
| `/rules/test/` | Interactive rule testing page |
| `/admin/` | Django Admin (manage rules, view history) |
| `/api/eval-engine/` | REST API endpoints |

## Key Integration Points

### 1. Model Integration

The `Alert` model provides a `to_context()` method that converts model data into a dictionary for rule evaluation:

```python
# alerts/models.py
class Alert(models.Model):
    # ... fields ...

    def to_context(self) -> dict:
        return {
            'severity': self.severity,
            'alert_count_1h': self.alert_count_1h,
            'predicted_weight': self.predicted_weight,
            # ... other fields
        }
```

### 2. Rule Evaluation

The `evaluate_alert_push()` utility demonstrates how to use the rule engine:

```python
# alerts/utils.py
from eval_engine.configurable_rule_engine import ConfigurableRuleEngine

def evaluate_alert_push(alert) -> dict:
    engine = ConfigurableRuleEngine()
    context = alert.to_context()
    result = engine.evaluate('default_push_decision', context)

    return {
        'should_push': result.action.get('should_push', False),
        'channel': result.action.get('channel', 'im_normal'),
        'trace_id': result.trace_id,
    }
```

### 3. Audit Logging

Custom audit callback configured in settings:

```python
# demo_project/settings.py
EVAL_ENGINE_AUDIT_LOG_ENABLED = True
EVAL_ENGINE_AUDIT_LOG_CALLBACK = 'alerts.utils.demo_audit_logger'
```

### 4. Cache Configuration

Using in-memory cache (no Redis required for demo):

```python
# demo_project/settings.py
EVAL_ENGINE_CACHE_BACKEND = 'memory'
EVAL_ENGINE_CACHE_TTL = 300
```

### 5. Django Admin Customization

The demo uses django-eval's custom admin templates:
- Inline rule testing panel on rule edit page
- Field schema reference
- Quick action links on list page

## Configuration Reference

All django-eval settings used in this demo:

```python
# Cache
EVAL_ENGINE_CACHE_BACKEND = 'memory'       # 'django' | 'memory' | 'redis' | 'dummy'
EVAL_ENGINE_CACHE_TTL = 300

# Engine
EVAL_ENGINE_DEFAULT_TIMEOUT_MS = 100
EVAL_ENGINE_EXPRESSION_MAX_LENGTH = 2000
EVAL_ENGINE_FALLBACK_ON_ERROR = True

# Watcher
EVAL_ENGINE_REGISTRY_WATCHER_ENABLED = False  # Disabled for demo

# Audit
EVAL_ENGINE_AUDIT_LOG_ENABLED = True
EVAL_ENGINE_AUDIT_LOG_CALLBACK = 'alerts.utils.demo_audit_logger'
```

## API Examples

### Evaluate a Rule

```bash
curl -X POST http://127.0.0.1:8000/api/eval-engine/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "default_push_decision",
    "context": {
      "severity": "critical",
      "alert_count_1h": 15
    }
  }'
```

### Test a Rule

```bash
curl -X POST http://127.0.0.1:8000/api/eval-engine/rules/default_push_decision/test \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "severity": "critical",
      "level": "critical"
    }
  }'
```

### Validate Expression

```bash
curl -X POST http://127.0.0.1:8000/api/eval-engine/rules/validate \
  -H "Content-Type: application/json" \
  -d '{
    "expression": "severity == '\''critical'\'' and alert_count_1h > 10"
  }'
```

## Testing

Run the demo project's tests:

```bash
cd examples/demo_project
python manage.py test alerts
```

## Next Steps

1. Explore the Django Admin at `/admin/eval_engine/ruleconfig/` to create custom rules
2. Use the interactive rule tester at `/rules/test/` to experiment with contexts
3. Check the API documentation in the main project's `README.md`
4. Review the source code in `alerts/utils.py` for integration patterns