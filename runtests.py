import os
import sys
import django
from django.conf import settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run_tests():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.test_settings'

    if not settings.configured:
        settings_module = 'tests.test_settings'
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings_module)

    django.setup()

    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2, interactive=False)
    failures = test_runner.run_tests(['tests'])
    sys.exit(bool(failures))


if __name__ == '__main__':
    run_tests()