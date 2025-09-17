# evaluation/services/base.py
"""基础服务类"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class BaseService:
    """基础服务类"""

    def __init__(self):
        self.base_dir = Path(settings.BASE_DIR)
        self.evaluation_dir = self.base_dir / 'evaluation'
        self.setup_directories()

    def setup_directories(self):
        """确保必要的目录存在"""
        directories = [
            self.evaluation_dir / 'opencompass_datasets',
            self.evaluation_dir / 'configs',
            self.evaluation_dir / 'outputs',
            self.evaluation_dir / 'task_logs',
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def handle_error(self, operation: str, error: Exception) -> Dict[str, Any]:
        """统一的错误处理"""
        logger.error(f"{operation} failed: {error}", exc_info=True)
        return {
            'success': False,
            'error': str(error),
            'operation': operation
        }

    def validate_path(self, path: Path, must_exist: bool = True) -> Optional[Path]:
        """验证路径安全性"""
        try:
            resolved = path.resolve()
            # 确保路径在允许的目录内
            if not str(resolved).startswith(str(self.base_dir)):
                raise ValueError("路径不在允许的范围内")
            if must_exist and not resolved.exists():
                raise FileNotFoundError(f"路径不存在: {resolved}")
            return resolved
        except Exception as e:
            logger.error(f"路径验证失败: {e}")
            return None