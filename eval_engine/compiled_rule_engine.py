import logging
import threading
from typing import Dict, Any, List, Callable, Optional

from simpleeval import SimpleEval

logger = logging.getLogger(__name__)


class CompiledChecker:
    __slots__ = ('field', 'fn')

    def __init__(self, field: str, fn: Callable[[Dict], bool]):
        self.field = field
        self.fn = fn

    def __call__(self, context: dict) -> bool:
        try:
            return self.fn(context)
        except Exception:
            return False


class CompiledDecisionRow:
    __slots__ = ('rule_id', 'checkers', 'then', 'is_passthrough')

    def __init__(self, rule_id: str, checkers: List[CompiledChecker],
                 then: dict, is_passthrough: bool = False):
        self.rule_id = rule_id
        self.checkers = checkers
        self.then = then if isinstance(then, dict) else {}
        self.is_passthrough = is_passthrough

    def match(self, context: dict) -> bool:
        if self.is_passthrough:
            return True
        for checker in self.checkers:
            if not checker(context):
                return False
        return True


class CompiledDecisionTable:
    __slots__ = ('rule_id', 'rule_name', 'priority', 'rule_type', 'rows')

    def __init__(self, rule_id: str, rule_name: str, priority: int,
                 rows: List[CompiledDecisionRow], rule_type: str = ''):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.priority = priority
        self.rule_type = rule_type
        self.rows = rows

    def evaluate(self, context: dict) -> dict:
        for row in self.rows:
            if row.match(context):
                return row.then
        return {"action": "suppress", "fallback": True}


class RuleCompiler:
    _evaluator = SimpleEval()

    @classmethod
    def compile_table(cls, rule_id: str, rule_name: str, priority: int,
                      table: dict, rule_type: str = '') -> CompiledDecisionTable:
        rules = table.get("rules", [])
        inputs = table.get("inputs", [])
        compiled_rows = []

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            when = rule.get("when")
            then = rule.get("then", {})

            if when is None or (isinstance(when, dict) and len(when) == 0):
                compiled_rows.append(
                    CompiledDecisionRow(rule.get("id", ""), [], then, is_passthrough=True)
                )
                continue

            checkers = cls._compile_conditions(when, inputs)
            compiled_rows.append(
                CompiledDecisionRow(rule.get("id", ""), checkers, then)
            )

        return CompiledDecisionTable(rule_id, rule_name, priority, compiled_rows, rule_type)

    @classmethod
    def _compile_conditions(cls, conditions, inputs: list = None) -> List[CompiledChecker]:
        if isinstance(conditions, dict):
            if "and" in conditions:
                return cls._compile_and(conditions["and"], inputs)
            if "or" in conditions:
                return cls._compile_or(conditions["or"], inputs)
            return cls._compile_dict(conditions)

        if isinstance(conditions, list):
            return cls._compile_list(conditions, inputs)

        return []

    @classmethod
    def _compile_dict(cls, conditions: dict) -> List[CompiledChecker]:
        checkers = []
        for field, expr in conditions.items():
            checkers.append(cls._compile_single(field, expr))
        return checkers

    @classmethod
    def _compile_and(cls, sub_conditions: list, inputs: list) -> List[CompiledChecker]:
        all_checkers = []
        for sub in sub_conditions:
            all_checkers.extend(cls._compile_conditions(sub, inputs))

        def and_checker(context: dict) -> bool:
            for c in all_checkers:
                if not c(context):
                    return False
            return True

        return [CompiledChecker("__and__", and_checker)]

    @classmethod
    def _compile_or(cls, sub_conditions: list, inputs: list) -> List[CompiledChecker]:
        sub_checkers_list = [cls._compile_conditions(sub, inputs) for sub in sub_conditions]

        def or_checker(context: dict) -> bool:
            for checkers in sub_checkers_list:
                all_pass = True
                for c in checkers:
                    if not c(context):
                        all_pass = False
                        break
                if all_pass:
                    return True
            return False

        return [CompiledChecker("__or__", or_checker)]

    @classmethod
    def _compile_list(cls, conditions: list, inputs: list) -> List[CompiledChecker]:
        if not inputs:
            return []
        checkers = []
        for idx, expr in enumerate(conditions):
            if idx >= len(inputs):
                break
            if expr is None:
                continue
            field_name = inputs[idx].get('field') or inputs[idx].get('name')
            if field_name:
                checkers.append(cls._compile_single(field_name, expr))
        return checkers

    @classmethod
    def _compile_single(cls, field: str, expr) -> CompiledChecker:
        if isinstance(expr, list):
            if len(expr) == 2 and all(isinstance(v, (int, float)) for v in expr):
                min_val, max_val = expr[0], expr[1]
                return CompiledChecker(
                    field,
                    lambda ctx, f=field, lo=min_val, hi=max_val:
                        lo <= ctx.get(f, 0) <= hi
                )
            else:
                allowed_set = frozenset(str(v) for v in expr)
                return CompiledChecker(
                    field,
                    lambda ctx, f=field, s=allowed_set: str(ctx.get(f, '')) in s
                )

        expr_str = str(expr).strip()

        if isinstance(expr, str) and not any(
            expr.startswith(op) for op in ['>', '<', '=', '!', '>=', '<=', '!=', '==']
        ):
            try:
                float(expr_str)
            except ValueError:
                return CompiledChecker(
                    field,
                    lambda ctx, f=field, v=expr_str: ctx.get(f) == v
                )

        if expr_str.startswith('>='):
            right = expr_str[2:].strip()
            if right.startswith("'") or right.startswith('"'):
                rv = right[1:-1]
                return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, '') >= v)
            try:
                rv = float(right)
            except ValueError:
                rv = right
            return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, 0) >= v)

        if expr_str.startswith('<='):
            right = expr_str[2:].strip()
            if right.startswith("'") or right.startswith('"'):
                rv = right[1:-1]
                return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, '') <= v)
            try:
                rv = float(right)
            except ValueError:
                rv = right
            return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, 0) <= v)

        if expr_str.startswith('!='):
            right = expr_str[2:].strip()
            if right.startswith("'") or right.startswith('"'):
                rv = right[1:-1]
                return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f) != v)
            try:
                rv = float(right)
            except ValueError:
                rv = right
            return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f) != v)

        if expr_str.startswith('=='):
            right = expr_str[2:].strip()
            if right.startswith("'") or right.startswith('"'):
                rv = right[1:-1]
                return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f) == v)
            try:
                rv = float(right)
            except ValueError:
                rv = right
            return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, 0) == v)

        if expr_str.startswith('>'):
            right = expr_str[1:].strip()
            if right.startswith("'") or right.startswith('"'):
                rv = right[1:-1]
                return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, '') > v)
            try:
                rv = float(right)
            except ValueError:
                rv = right
            return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, 0) > v)

        if expr_str.startswith('<'):
            right = expr_str[1:].strip()
            if right.startswith("'") or right.startswith('"'):
                rv = right[1:-1]
                return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, '') < v)
            try:
                rv = float(right)
            except ValueError:
                rv = right
            return CompiledChecker(field, lambda ctx, f=field, v=rv: ctx.get(f, 0) < v)

        try:
            parsed = cls._evaluator.parse(expr_str)
        except Exception:
            return CompiledChecker(field, lambda ctx: False)

        def _eval_precompiled(context: dict, f=field, p=parsed) -> bool:
            try:
                cls._evaluator.names = {"actual": context.get(f)}
                return bool(cls._evaluator.eval('', previously_parsed=p))
            except Exception:
                return False

        return CompiledChecker(field, _eval_precompiled)


class RuleRegistry:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tables = {}
            cls._instance._versions = {}
            cls._instance._loaded = False
        return cls._instance

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get(self, rule_id: str) -> Optional[CompiledDecisionTable]:
        with self._lock:
            return self._tables.get(rule_id)

    def get_all_active(self, rule_type: str = None) -> List[CompiledDecisionTable]:
        with self._lock:
            tables = list(self._tables.values())
        if rule_type:
            tables = [t for t in tables if t.rule_type == rule_type]
        return sorted(tables, key=lambda t: t.priority)

    def register(self, rule_id: str, table: CompiledDecisionTable, version: int = 0):
        with self._lock:
            self._tables[rule_id] = table
            self._versions[rule_id] = version

    def invalidate(self, rule_id: str):
        with self._lock:
            self._tables.pop(rule_id, None)
            self._versions.pop(rule_id, None)

    def clear(self):
        with self._lock:
            self._tables.clear()
            self._versions.clear()
            self._loaded = False

    def load_from_db(self, rule_type: str = None) -> int:
        try:
            from .models import RuleConfig
        except Exception as e:
            logger.error(f"RuleRegistry: failed to import RuleConfig: {e}")
            return 0

        qs = RuleConfig.objects.filter(is_active=True)
        if rule_type:
            qs = qs.filter(rule_type=rule_type)

        loaded = 0
        for rule in qs:
            try:
                compiled = self._compile_rule(rule)
                if compiled is not None:
                    self.register(rule.rule_id, compiled, version=rule.version)
                    loaded += 1
            except Exception as e:
                logger.error(f"RuleRegistry: failed to compile rule {rule.rule_id}: {e}")

        self._loaded = True
        logger.info(f"RuleRegistry: loaded {loaded} compiled rules into memory")
        return loaded

    def reload_single(self, rule_id: str) -> bool:
        try:
            from .models import RuleConfig
        except Exception:
            return False

        try:
            rule = RuleConfig.objects.get(rule_id=rule_id, is_active=True)
        except RuleConfig.DoesNotExist:
            self.invalidate(rule_id)
            return True
        except Exception as e:
            logger.error(f"RuleRegistry: failed to reload rule {rule_id}: {e}")
            return False

        compiled = self._compile_rule(rule)
        if compiled is not None:
            self.register(rule.rule_id, compiled, version=rule.version)
            return True
        return False

    def _compile_rule(self, rule) -> Optional[CompiledDecisionTable]:
        rule_content = rule.rule_content or {}
        table_data = self._extract_table(rule_content)

        if not table_data:
            return None

        return RuleCompiler.compile_table(
            rule.rule_id, rule.rule_name, rule.priority,
            table_data, rule_type=getattr(rule, 'rule_type', '')
        )

    @staticmethod
    def _extract_table(rule_content: dict) -> Optional[dict]:
        if rule_content.get("format") == "decision_table":
            table = rule_content.get("table")
            if table and isinstance(table, dict):
                return table

        conditions = rule_content.get("conditions", {})
        if isinstance(conditions, dict) and "table" in conditions:
            table = conditions["table"]
            if table and isinstance(table, dict):
                return table

        if isinstance(rule_content, dict) and rule_content.get("kind") == "DecisionTable":
            return rule_content

        return None

    @property
    def size(self) -> int:
        return len(self._tables)

    @property
    def version_map(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._versions)