#!/usr/bin/env python
import os
from setuptools import setup, find_packages

with open(os.path.join(os.path.dirname(__file__), 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='django-eval',
    version='0.1.0',
    description='A Django reusable app providing a secure, configurable rule engine powered by SimpleEval',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    author='Dakken Django Team',
    license='MIT',
    url='https://github.com/your-org/django-eval',
    packages=find_packages(exclude=['tests', 'tests.*', 'examples', 'examples.*']),
    include_package_data=True,
    install_requires=[
        'Django>=3.2,<=6.0',
        'djangorestframework>=3.11',
        'simpleeval>=0.9.13',
    ],
    extras_require={
        'redis': [
            'redis>=3.5',
            'django-redis>=5.4',
        ],
        'test': [
            'pytest>=6.0',
            'pytest-django>=4.0',
        ],
    },
    python_requires='>=3.10',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 3.2',
        'Framework :: Django :: 4.0',
        'Framework :: Django :: 4.1',
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.2',
        'Framework :: Django :: 6.0',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='django simpleeval rule-engine decision-table expression-evaluator',
    project_urls={
        'Source': 'https://github.com/your-org/django-eval',
        'Bug Reports': 'https://github.com/your-org/django-eval/issues',
    },
)