import pytest
from django.test import TestCase, override_settings

from eval_engine.cache import (
    get_cache, reset_cache,
    DjangoCacheBackend, MemoryCacheBackend, DummyCacheBackend,
)
from eval_engine.settings import EvalEngineSettings


class TestMemoryCacheBackend(TestCase):
    def setUp(self):
        self.cache = MemoryCacheBackend()

    def test_basic_set_get(self):
        self.cache.set('key1', 'value1')
        self.assertEqual(self.cache.get('key1'), 'value1')

    def test_get_missing_returns_default(self):
        self.assertIsNone(self.cache.get('missing'))
        self.assertEqual(self.cache.get('missing', 'default'), 'default')

    def test_delete(self):
        self.cache.set('key', 'value')
        self.cache.delete('key')
        self.assertIsNone(self.cache.get('key'))

    def test_ttl_expiration(self):
        import time
        self.cache.set('temp', 'value', timeout=1)
        self.assertEqual(self.cache.get('temp'), 'value')
        time.sleep(1.1)
        self.assertIsNone(self.cache.get('temp'))

    def test_no_ttl_persists(self):
        self.cache.set('perm', 'value')
        self.assertEqual(self.cache.get('perm'), 'value')

    def test_clear(self):
        self.cache.set('a', 1)
        self.cache.set('b', 2)
        self.cache.clear()
        self.assertIsNone(self.cache.get('a'))
        self.assertIsNone(self.cache.get('b'))

    def test_get_many(self):
        self.cache.set('a', 1)
        self.cache.set('b', 2)
        result = self.cache.get_many(['a', 'b', 'c'])
        self.assertEqual(result['a'], 1)
        self.assertEqual(result['b'], 2)
        self.assertIsNone(result['c'])

    def test_set_many(self):
        self.cache.set_many({'x': 10, 'y': 20})
        self.assertEqual(self.cache.get('x'), 10)
        self.assertEqual(self.cache.get('y'), 20)

    def test_thread_safety(self):
        import threading
        errors = []

        def worker(n):
            try:
                for i in range(100):
                    self.cache.set(f'key_{n}_{i}', i)
                    val = self.cache.get(f'key_{n}_{i}')
                    if val != i:
                        errors.append(f'Expected {i}, got {val}')
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestDummyCacheBackend(TestCase):
    def setUp(self):
        self.cache = DummyCacheBackend()

    def test_always_returns_default(self):
        self.cache.set('key', 'value')
        self.assertIsNone(self.cache.get('key'))
        self.assertEqual(self.cache.get('key', 'default'), 'default')

    def test_delete_noop(self):
        self.cache.delete('key')  # should not raise

    def test_clear_noop(self):
        self.cache.clear()  # should not raise


class TestCacheSettings(TestCase):
    def tearDown(self):
        reset_cache()

    @override_settings(EVAL_ENGINE_CACHE_ENABLED=False)
    def test_disabled_cache_returns_dummy(self):
        reset_cache()
        cache = get_cache()
        self.assertIsInstance(cache, DummyCacheBackend)

    @override_settings(EVAL_ENGINE_CACHE_BACKEND='memory')
    def test_memory_backend_setting(self):
        reset_cache()
        cache = get_cache()
        self.assertIsInstance(cache, MemoryCacheBackend)

    def test_singleton_behavior(self):
        reset_cache()
        c1 = get_cache()
        c2 = get_cache()
        self.assertIs(c1, c2)

    @override_settings(EVAL_ENGINE_CACHE_BACKEND='nonexistent')
    def test_invalid_backend_falls_back_to_django(self):
        reset_cache()
        cache = get_cache()
        self.assertIsInstance(cache, DjangoCacheBackend)


class TestEvalEngineSettings(TestCase):
    @override_settings(EVAL_ENGINE_DEFAULT_TIMEOUT_MS=500)
    def test_custom_timeout(self):
        self.assertEqual(EvalEngineSettings.default_timeout_ms(), 500)

    @override_settings(EVAL_ENGINE_EXPRESSION_MAX_LENGTH=5000)
    def test_custom_max_length(self):
        self.assertEqual(EvalEngineSettings.expression_max_length(), 5000)

    @override_settings(EVAL_ENGINE_CACHE_TTL=600)
    def test_custom_cache_ttl(self):
        self.assertEqual(EvalEngineSettings.cache_ttl(), 600)

    def test_default_values(self):
        self.assertEqual(EvalEngineSettings.default_timeout_ms(), 100)
        self.assertEqual(EvalEngineSettings.expression_max_length(), 2000)
        self.assertEqual(EvalEngineSettings.cache_ttl(), 300)
        self.assertTrue(EvalEngineSettings.cache_enabled())
        self.assertTrue(EvalEngineSettings.fallback_on_error())

    @override_settings(EVAL_ENGINE_AUDIT_LOG_CALLBACK='tests.test_cache.sample_callback')
    def test_dotted_path_callback(self):
        callback = EvalEngineSettings.audit_log_callback()
        self.assertEqual(callback, sample_callback)


# Sample callback for dotted path test
def sample_callback(data):
    pass