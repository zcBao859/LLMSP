# evaluation/apps.py
from django.apps import AppConfig


class EvaluationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'evaluation'
    verbose_name = '模型评测'

    def ready(self):
        """应用启动时执行"""
        # 确保必要的目录存在
        import os
        from pathlib import Path
        from django.conf import settings

        base_dir = Path(settings.BASE_DIR)

        # 创建必要的目录
        directories = [
            base_dir / 'evaluation' / 'opencompass_datasets',
            base_dir / 'evaluation' / 'configs',
            base_dir / 'evaluation' / 'outputs',
            base_dir / 'evaluation' / 'opencompass',
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)