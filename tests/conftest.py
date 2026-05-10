import pytest
from eval_engine.cache import reset_cache


@pytest.fixture
def rule_db_setup(db):
    from eval_engine.models import RuleConfig, RuleVersionHistory
    push_rule = {
        "name": "test_push_decision",
        "kind": "DecisionTable",
        "inputs": [
            {"name": "alert_count_1h", "type": "number"},
            {"name": "alert_severity", "type": "string"}
        ],
        "outputs": [
            {"name": "action", "type": "string"}
        ],
        "rules": [
            {"when": {"alert_count_1h": 1}, "then": {"action": "send"}},
            {"when": {"alert_count_1h": ">1"}, "then": {"action": "suppress"}}
        ]
    }
    RuleConfig.objects.create(
        rule_id="test_push_rule",
        rule_name="Test Push Rule",
        rule_type="push_decision",
        engine_type="simpleeval",
        rule_content={"conditions": {"format": "decision_table", "table": push_rule}, "actions": {}},
        is_active=True
    )

    return push_rule


@pytest.fixture(autouse=True)
def clear_cache():
    reset_cache()
    yield
    reset_cache()