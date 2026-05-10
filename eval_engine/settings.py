from django.conf import settings


class EvalEngineSettings:
    """Centralized settings for django-eval with sensible defaults.

    All settings can be overridden via Django settings module using the
    EVAL_ENGINE_ prefix. For example:
        EVAL_ENGINE_CACHE_ENABLED = False
        EVAL_ENGINE_DEFAULT_TIMEOUT_MS = 200
    """

    _PREFIX = 'EVAL_ENGINE_'

    # Cache settings
    CACHE_ENABLED = True
    CACHE_BACKEND = 'django'  # 'django' | 'redis' | 'memory' | 'dummy'
    CACHE_KEY_PREFIX = 'ee:'
    CACHE_TTL = 300  # seconds
    CACHE_VERSION_KEY = 'ee:registry:version'

    # Engine settings
    DEFAULT_TIMEOUT_MS = 100
    EXPRESSION_MAX_LENGTH = 2000
    FALLBACK_ON_ERROR = True
    FALLBACK_ACTION = {
        'should_push': True,
        'reason': 'rule_fallback',
        'channel': 'im_normal',
        'delay_seconds': 0,
    }

    # Registry watcher settings
    REGISTRY_WATCHER_ENABLED = True
    REGISTRY_WATCHER_INTERVAL = 5  # seconds
    REGISTRY_WATCHER_MAX_ERRORS = 10

    # Audit log settings
    AUDIT_LOG_ENABLED = False
    AUDIT_LOG_CALLBACK = None  # dotted path to callable

    # Security settings
    FORBIDDEN_PATTERNS = None  # defaults to configurable_rule_engine.FORBIDDEN_PATTERNS
    ALLOWED_FUNCTIONS = None   # defaults to configurable_rule_engine.ALLOWED_FUNCTIONS

    @classmethod
    def get(cls, name, default=None):
        django_name = cls._PREFIX + name
        return getattr(settings, django_name, getattr(cls, name, default))

    @classmethod
    def cache_enabled(cls):
        return cls.get('CACHE_ENABLED')

    @classmethod
    def cache_ttl(cls):
        return cls.get('CACHE_TTL')

    @classmethod
    def default_timeout_ms(cls):
        return cls.get('DEFAULT_TIMEOUT_MS')

    @classmethod
    def expression_max_length(cls):
        return cls.get('EXPRESSION_MAX_LENGTH')

    @classmethod
    def fallback_on_error(cls):
        return cls.get('FALLBACK_ON_ERROR')

    @classmethod
    def fallback_action(cls):
        return cls.get('FALLBACK_ACTION')

    @classmethod
    def registry_watcher_enabled(cls):
        return cls.get('REGISTRY_WATCHER_ENABLED')

    @classmethod
    def registry_watcher_interval(cls):
        return cls.get('REGISTRY_WATCHER_INTERVAL')

    @classmethod
    def audit_log_enabled(cls):
        return cls.get('AUDIT_LOG_ENABLED')

    @classmethod
    def audit_log_callback(cls):
        callback = cls.get('AUDIT_LOG_CALLBACK')
        if isinstance(callback, str):
            return cls._import_dotted_path(callback)
        return callback

    @staticmethod
    def _import_dotted_path(path):
        module_path, attr_name = path.rsplit('.', 1)
        module = __import__(module_path, fromlist=[attr_name])
        return getattr(module, attr_name)


# Backwards-compatible module-level accessors
def get_setting(name, default=None):
    return EvalEngineSettings.get(name, default)