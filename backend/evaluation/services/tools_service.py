# evaluation/services/tools_service.py
"""OpenCompass工具服务 - 封装各种实用工具的调用"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from django.conf import settings

logger = logging.getLogger(__name__)


class OpenCompassToolsService:
    """OpenCompass工具服务"""

    def __init__(self):
        self.base_dir = Path(settings.BASE_DIR)
        self.evaluation_dir = self.base_dir / 'evaluation'
        self.opencompass_path = self.evaluation_dir / 'opencompass'
        self.tools_path = self.opencompass_path / 'tools'

    def _run_tool(self, tool_name: str, args: List[str], cwd: Optional[Path] = None) -> Dict[str, Any]:
        """通用工具运行方法"""
        tool_script = self.tools_path / tool_name
        if not tool_script.exists():
            raise FileNotFoundError(f"Tool not found: {tool_script}")

        cmd = [sys.executable, str(tool_script)] + args
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join([
            str(self.evaluation_dir),
            str(self.opencompass_path),
            env.get('PYTHONPATH', '')
        ])
        env['OPENCOMPASS_ROOT'] = str(self.opencompass_path)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                env=env, cwd=str(cwd or self.base_dir)
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {'success': False, 'error': str(e)}

    def _task_tool_wrapper(self, task_id: int, tool_name: str,
                           args_builder: Callable, result_parser: Optional[Callable] = None) -> Dict[str, Any]:
        """任务相关工具的通用包装器"""
        from evaluation.models import EvaluationTask

        try:
            task = EvaluationTask.objects.get(id=task_id)
            if not task.config or not task.work_dir:
                return {'success': False, 'error': '任务配置或工作目录不存在'}

            args = args_builder(task)
            result = self._run_tool(tool_name, args)

            if result['success'] and result_parser:
                return result_parser(task, result)
            return result

        except Exception as e:
            logger.error(f"{tool_name} failed for task {task_id}: {e}")
            return {'success': False, 'error': str(e)}

    def analyze_bad_cases(self, task_id: int, force: bool = False) -> Dict[str, Any]:
        """分析错误案例"""

        def build_args(task):
            args = [task.config.file_path, '-w', task.work_dir]
            if force:
                args.append('-f')
            return args

        def parse_result(task, result):
            case_dir = Path(task.work_dir) / 'case_analysis'
            bad_files = list(case_dir.glob('bad/*.json'))

            bad_cases = []
            for f in bad_files[:1]:  # 只读第一个文件
                with open(f, 'r', encoding='utf-8') as file:
                    bad_cases = json.load(file)

            return {
                'success': True,
                'bad_cases_count': len(bad_cases),
                'bad_cases': bad_cases[:100],
                'files': {
                    'bad': [str(f) for f in bad_files],
                    'all': [str(f) for f in case_dir.glob('all/*.json')]
                }
            }

        return self._task_tool_wrapper(task_id, 'case_analyzer.py', build_args, parse_result)

    def list_available_configs(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """列出可用配置"""
        args = [pattern] if pattern else []
        result = self._run_tool('list_configs.py', args)

        if not result['success']:
            return result

        # 简单解析表格输出
        items = {'models': [], 'opencompass_datasets': []}
        section = None

        for line in result['stdout'].split('\n'):
            if 'Model' in line and 'Config Path' in line:
                section = 'models'
            elif 'Dataset' in line and 'Config Path' in line:
                section = 'opencompass_datasets'
            elif line.startswith('|') and section:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2 and not parts[0].startswith('-'):
                    items[section].append({'name': parts[0], 'config_path': parts[1]})

        return {'success': True, **items}

    def merge_predictions(self, task_id: int, clean: bool = False) -> Dict[str, Any]:
        """合并预测结果"""

        def build_args(task):
            work_path = Path(task.work_dir)
            args = [
                task.config.file_path,
                '-w', str(work_path.parent),
                '-r', work_path.name
            ]
            if clean:
                args.append('-c')
            return args

        return self._task_tool_wrapper(task_id, 'prediction_merger.py', build_args)

    def collect_code_predictions(self, task_id: int) -> Dict[str, Any]:
        """收集代码预测"""

        def build_args(task):
            return [task.config.file_path, '-r', Path(task.work_dir).name]

        def parse_result(task, result):
            humanevalx_dir = Path(task.work_dir) / 'humanevalx'
            result_files = []

            if humanevalx_dir.exists():
                result_files = [str(f) for f in humanevalx_dir.rglob('*.json')]

            return {
                'success': True,
                'result_files': result_files,
                'message': '代码预测结果收集完成'
            }

        return self._task_tool_wrapper(task_id, 'collect_code_preds.py', build_args, parse_result)

    def compare_models(self, task_ids: List[int]) -> Dict[str, Any]:
        """对比模型结果"""
        from evaluation.models import EvaluationTask

        tasks = EvaluationTask.objects.filter(id__in=task_ids, config__isnull=False, work_dir__isnull=False)
        if tasks.count() < 2:
            return {'success': False, 'error': '有效任务数量不足'}

        args = []
        for task in tasks:
            args.extend(['--cfg-paths', task.config.file_path])
            args.extend(['--work-dirs', task.work_dir])

        return self._run_tool('viz_multi_model.py', args)

    def view_prompts(self, config_path: str, dataset_pattern: Optional[str] = None,
                     count: int = 1) -> Dict[str, Any]:
        """查看prompt示例"""
        args = [config_path, '-n', '-c', str(count)]
        if dataset_pattern:
            args.extend(['-p', dataset_pattern])

        result = self._run_tool('prompt_viewer.py', args)
        return {'success': result['success'], 'prompts': result.get('stdout', '')} if result['success'] else result

    def test_api_model(self, config_path: str) -> Dict[str, Any]:
        """测试API模型"""
        result = self._run_tool('test_api_model.py', [config_path, '-n'])
        return {
            'success': result['success'],
            'test_output': result.get('stdout', ''),
            'message': 'API模型测试完成' if result['success'] else '测试失败'
        }