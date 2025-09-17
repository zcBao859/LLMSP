# backend/openai_api/__init__.py
"""
JIUTIAN API Service - Django OpenAI-compatible API
"""
__version__ = "1.0.0"

default_app_config = 'openai_api.apps.OpenaiApiConfig'


# backend/openai_api/apps.py
from django.apps import AppConfig


class OpenaiApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'openai_api'
    verbose_name = 'OpenAI API'