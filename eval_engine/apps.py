from django.apps import AppConfig


class EvalEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'eval_engine'
    verbose_name = 'Eval Engine - Rule Engine Module'

    def ready(self):
        self._init_compiled_registry()

    def _init_compiled_registry(self):
        try:
            from .compiled_rule_engine import RuleRegistry
            from .registry_watcher import RegistryWatcher

            registry = RuleRegistry()
            loaded = registry.load_from_db()
            if loaded > 0:
                watcher = RegistryWatcher()
                watcher.start(interval=5)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Compiled registry init skipped: {e}")