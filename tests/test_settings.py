import os
import tempfile

SECRET_KEY = 'test-secret-key-for-eval-engine-tests'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'eval_engine',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(tempfile.gettempdir(), 'eval_engine_test.db'),
        'TEST': {
            'NAME': os.path.join(tempfile.gettempdir(), 'eval_engine_test.db'),
        },
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

ROOT_URLCONF = 'tests.test_urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Eval Engine Settings
EVAL_ENGINE_DEFAULT_TIMEOUT_MS = 100
EVAL_ENGINE_EXPRESSION_MAX_LENGTH = 2000
EVAL_ENGINE_CACHE_TTL = 300
EVAL_ENGINE_CACHE_ENABLED = True
EVAL_ENGINE_CACHE_BACKEND = 'django'
EVAL_ENGINE_FALLBACK_ON_ERROR = True
EVAL_ENGINE_REGISTRY_WATCHER_ENABLED = False
