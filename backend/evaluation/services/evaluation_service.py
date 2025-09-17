# evaluation/services/evaluation_service.py
"""评测服务 - 使用用户上传的配置文件运行OpenCompass"""
import os
import subprocess
import logging
import time
import re
from pathlib import Path
from typing import Dict, Optional, Callable, List, Any
from django.conf import settings
import sys

from .base import BaseService
from .result_parser import ResultParser
from ..constants import DEFAULT_LIMITS, CACHE_TIMEOUT

logger = logging.getLogger(__name__)


class EvaluationService(BaseService):
    """评测服务"""

    def __init__(self):
        super().__init__()
        self.opencompass_path = self.evaluation_dir / 'opencompass'
        self.run_script = self.evaluation_dir / 'run.py'
        # 修正输出目录路径
        self.outputs_dir = self.evaluation_dir / 'outputs'
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.task_logs_dir = self.evaluation_dir / 'task_logs'
        self.task_logs_dir.mkdir(parents=True, exist_ok=True)
        self.result_parser = ResultParser()

    def get_task_work_dir(self, task) -> Optional[Path]:
        """获取任务的工作目录"""
        if not task.work_dir:
            return None

        work_path = Path(task.work_dir)

        # 如果是相对路径，转换为绝对路径
        if not work_path.is_absolute():
            work_path = self.base_dir / work_path

        # 验证路径存在
        if work_path.exists():
            return work_path

        # 如果不存在，尝试在outputs目录下查找
        if task.work_dir.startswith('./') or task.work_dir.startswith('../'):
            alt_path = self.base_dir / task.work_dir.lstrip('./')
            if alt_path.exists():
                return alt_path

        # 尝试在evaluation/outputs目录查找
        # 处理可能的路径格式，如：outputs/deepseek_advanced_safety_eval/20250726_190224
        work_dir_parts = Path(task.work_dir).parts
        if 'outputs' in work_dir_parts:
            # 从outputs开始的路径部分
            idx = work_dir_parts.index('outputs')
            relative_path = Path(*work_dir_parts[idx + 1:])
            outputs_path = self.outputs_dir / relative_path
            if outputs_path.exists():
                return outputs_path

        # 直接在outputs目录下查找
        task_dir_name = Path(task.work_dir).name
        direct_path = self.outputs_dir / task_dir_name
        if direct_path.exists():
            return direct_path

        # 在outputs的子目录中查找
        for subdir in self.outputs_dir.iterdir():
            if subdir.is_dir():
                candidate = subdir / task_dir_name
                if candidate.exists():
                    return candidate

        return None

    def run_evaluation(self, task_id: int, config_path: str,
                       progress_callback: Optional[Callable] = None) -> Dict:
        """运行评测任务"""
        start_time = time.time()
        log_file = self.task_logs_dir / f'task_{task_id}_run.log'

        try:
            # 验证配置文件
            config_path_obj = self.validate_path(Path(config_path))
            if not config_path_obj:
                raise FileNotFoundError(f"Invalid config path: {config_path}")

            # 构建命令
            cmd = [sys.executable, str(self.run_script.absolute()), str(config_path_obj)]
            env = self._setup_environment()

            # 运行评测
            work_dir = self._run_evaluation_process(cmd, env, log_file, progress_callback)

            # 解析结果
            results = self._parse_results_from_work_dir(work_dir) if work_dir else None

            # 更新任务信息
            self._update_task_info(task_id, work_dir, log_file)

            return {
                'work_dir': str(work_dir) if work_dir else None,
                'log_file': str(log_file),
                'results': results,
                'duration': time.time() - start_time
            }

        except Exception as e:
            return self.handle_error(f"Evaluation task {task_id}", e)

    def _setup_environment(self) -> Dict[str, str]:
        """设置环境变量"""
        env = os.environ.copy()

        pythonpath_parts = [
            str(self.evaluation_dir),
            str(self.opencompass_path),
        ]

        # 添加site-packages
        import site
        pythonpath_parts.extend(site.getsitepackages())

        if 'PYTHONPATH' in env:
            pythonpath_parts.append(env['PYTHONPATH'])

        env['PYTHONPATH'] = os.pathsep.join(pythonpath_parts)
        env['OPENCOMPASS_ROOT'] = str(self.opencompass_path)
        env['OPENCOMPASS_RUN_FROM_SERVICE'] = '1'

        # 添加API密钥
        for key in ['OPENAI_API_KEY', 'DEEPSEEK_API_KEY']:
            if hasattr(settings, key):
                env[key] = getattr(settings, key)

        return env

    def _run_evaluation_process(self, cmd: List[str], env: Dict[str, str],
                                log_file: Path, progress_callback: Optional[Callable]) -> Optional[Path]:
        """运行评测进程"""
        work_dir = None

        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== Evaluation Start ===\n")
            f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write("=" * 50 + "\n\n")
            f.flush()

            process = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT,
                text=True, env=env, cwd=str(self.base_dir), bufsize=1
            )

            # 监控进度
            while process.poll() is None:
                progress_info = self._parse_progress_from_log(log_file)

                if progress_info:
                    if progress_info.get('work_dir'):
                        work_dir = progress_info['work_dir']

                    if progress_callback:
                        progress_callback({
                            'progress': progress_info.get('progress', 0),
                            'work_dir': work_dir,
                            'log_file': str(log_file)
                        })

                time.sleep(5)

        if process.returncode != 0:
            self._handle_process_error(process.returncode, log_file)

        # 如果没有找到工作目录，尝试查找最新的
        if not work_dir:
            work_dir = self._find_latest_work_dir()

        return work_dir

    def _parse_progress_from_log(self, log_file: Path) -> Optional[Dict]:
        """从日志解析进度"""
        try:
            if not log_file.exists():
                return None

            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-1000:]  # 最后1000行

            progress_info = {}

            # 查找工作目录
            for line in lines:
                if 'Current exp folder:' in line:
                    match = re.search(r'Current exp folder:\s*(.+)', line)
                    if match:
                        work_dir_str = match.group(1).strip()
                        work_dir = self._resolve_work_dir(work_dir_str)
                        if work_dir and work_dir.exists():
                            progress_info['work_dir'] = work_dir
                            break
                # 也尝试匹配其他可能的工作目录格式
                elif 'Work dir:' in line or 'Output directory:' in line:
                    match = re.search(r'(?:Work dir:|Output directory:)\s*(.+)', line)
                    if match:
                        work_dir_str = match.group(1).strip()
                        work_dir = self._resolve_work_dir(work_dir_str)
                        if work_dir and work_dir.exists():
                            progress_info['work_dir'] = work_dir
                            break

            # 查找进度
            for line in reversed(lines):
                # 匹配 [1/10] 格式
                match = re.search(r'\[(\d+)/(\d+)\]', line)
                if match:
                    current, total = int(match.group(1)), int(match.group(2))
                    progress_info['progress'] = int(current / total * 100)
                    break

                # 匹配 Progress: 50% 格式
                match = re.search(r'Progress:\s*(\d+)%', line)
                if match:
                    progress_info['progress'] = int(match.group(1))
                    break

            return progress_info if progress_info else None

        except Exception as e:
            logger.warning(f"Failed to parse progress: {e}")
            return None

    def _resolve_work_dir(self, work_dir_str: str) -> Optional[Path]:
        """解析工作目录路径"""
        # 清理路径字符串
        work_dir_str = work_dir_str.strip()

        # 尝试多种路径解析方式
        candidates = []

        # 1. 绝对路径
        if os.path.isabs(work_dir_str):
            candidates.append(Path(work_dir_str))

        # 2. 相对于base_dir的路径
        if work_dir_str.startswith('./'):
            candidates.append(self.base_dir / work_dir_str[2:])
        elif work_dir_str.startswith('../'):
            candidates.append(self.base_dir / work_dir_str)
        else:
            candidates.append(self.base_dir / work_dir_str)

        # 3. 相对于evaluation目录的路径
        candidates.append(self.evaluation_dir / work_dir_str)

        # 4. 如果路径包含outputs，尝试从outputs开始构建
        if 'outputs' in work_dir_str:
            parts = Path(work_dir_str).parts
            if 'outputs' in parts:
                idx = parts.index('outputs')
                relative_path = Path(*parts[idx:])
                candidates.append(self.evaluation_dir / relative_path)

        # 5. 尝试在outputs目录下查找
        path_parts = Path(work_dir_str).parts
        if len(path_parts) >= 2:
            # 如deepseek_advanced_safety_eval/20250726_190224
            candidates.append(self.outputs_dir / Path(*path_parts[-2:]))
        if len(path_parts) >= 1:
            # 如20250726_190224
            candidates.append(self.outputs_dir / path_parts[-1])

        # 检查所有候选路径
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_dir():
                    return candidate.resolve()
            except:
                continue

        return None

    def _find_latest_work_dir(self) -> Optional[Path]:
        """查找最新的工作目录"""
        if not self.outputs_dir.exists():
            return None

        # 获取所有子目录（包括嵌套的）
        all_dirs = []

        # 首先检查outputs目录下的直接子目录
        for item in self.outputs_dir.iterdir():
            if item.is_dir():
                # 检查是否是配置目录（如 deepseek_advanced_safety_eval）
                subdirs = [d for d in item.iterdir() if d.is_dir() and d.name.startswith('202')]
                if subdirs:
                    all_dirs.extend(subdirs)
                # 也检查直接的时间戳目录
                elif item.name.startswith('202'):
                    all_dirs.append(item)

        if not all_dirs:
            return None

        # 返回最新的目录
        return max(all_dirs, key=lambda x: x.stat().st_mtime)

    def _parse_results_from_work_dir(self, work_dir: Optional[Path]) -> Optional[Dict]:
        """从工作目录解析结果"""
        if not work_dir or not work_dir.exists():
            return None

        # 查找结果文件 - 扩展搜索模式
        result_patterns = [
            '**/summary*.json',
            '**/*result*.json',
            '**/predictions/**/*.json',  # 添加predictions目录
            '**/*/predictions/*.json',
            '**/*.json'  # 最后尝试所有json文件
        ]

        result_files = []

        for pattern in result_patterns:
            found_files = list(work_dir.glob(pattern))
            # 过滤掉配置文件和日志相关的json
            result_files.extend([
                f for f in found_files
                if 'config' not in f.name.lower()
                   and 'log' not in f.name.lower()
                   and f.stat().st_size > 0  # 确保文件非空
            ])

        if not result_files:
            logger.warning(f"No result files found in {work_dir}")
            return None

        # 使用ResultParser解析
        try:
            results = self.result_parser.merge_results(result_files)
            logger.info(f"Parsed {len(result_files)} result files from {work_dir}")
            return results
        except Exception as e:
            logger.error(f"Failed to parse results: {e}")
            return None

    def _update_task_info(self, task_id: int, work_dir: Optional[Path], log_file: Path):
        """更新任务信息"""
        from evaluation.models import EvaluationTask

        task = EvaluationTask.objects.get(id=task_id)
        task.work_dir = str(work_dir) if work_dir else None
        task.log_file = str(log_file)
        task.save(update_fields=['work_dir', 'log_file'])

    def _handle_process_error(self, returncode: int, log_file: Path):
        """处理进程错误"""
        with open(log_file, 'r', encoding='utf-8') as f:
            error_log = f.read()

        # 提取关键错误信息
        error_keywords = ['error', 'exception', 'traceback', 'failed', 'import']
        error_lines = []

        for i, line in enumerate(error_log.split('\n')):
            if any(keyword in line.lower() for keyword in error_keywords):
                error_lines.append(line)

        error_summary = '\n'.join(error_lines[-50:]) if error_lines else error_log[-1000:]

        raise Exception(f"Evaluation failed with code {returncode}\n{error_summary}")

    def get_task_files(self, work_dir: str) -> Dict[str, List[Dict]]:
        """获取任务文件列表"""
        work_path = self.validate_path(Path(work_dir), must_exist=True)
        if not work_path:
            return {}

        files = {'logs': [], 'results': [], 'configs': [], 'others': []}

        for file_path in work_path.rglob('*'):
            if file_path.is_file():
                file_info = {
                    'name': file_path.name,
                    'path': str(file_path.relative_to(work_path)),
                    'size': file_path.stat().st_size,
                    'modified': file_path.stat().st_mtime
                }

                if file_path.suffix == '.log':
                    files['logs'].append(file_info)
                elif file_path.suffix in ['.json', '.csv'] and any(
                        keyword in file_path.name.lower()
                        for keyword in ['result', 'summary', 'score']
                ):
                    files['results'].append(file_info)
                elif file_path.suffix == '.py':
                    files['configs'].append(file_info)
                else:
                    files['others'].append(file_info)

        return files

    def save_results(self, task, results):
        """保存评测结果"""
        from evaluation.models import EvaluationResult

        if not results:
            return

        # 获取实际的结果数据
        parsed_results = results.get('results', results)
        if not isinstance(parsed_results, dict):
            return

        # 保存到数据库
        for model_name, model_data in parsed_results.items():
            if not isinstance(model_data, dict):
                continue

            for dataset_name, metrics in model_data.items():
                if not isinstance(metrics, dict):
                    continue

                for metric_name, value in metrics.items():
                    if isinstance(value, (int, float)):
                        EvaluationResult.objects.update_or_create(
                            task=task,
                            model_name=model_name,
                            dataset_name=dataset_name,
                            metric_name=metric_name,
                            defaults={
                                'metric_value': value,
                                'metric_unit': 'score',
                                'details': {'raw_value': value}
                            }
                        )