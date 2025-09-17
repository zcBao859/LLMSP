# 在 evaluation/views.py 文件顶部，确保有以下导入：

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.http import HttpResponse
from django.db.models import Avg, Count, Q
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings  # 添加这行
import json
import re
from pathlib import Path
import logging

from .services import EvaluationService
from .services import OpenCompassToolsService  # 确保导入工具服务
from .models import (
    EvaluationDataset, EvaluationConfig, EvaluationTask,
    EvaluationResult, ModelBenchmark
)
from .serializers import (
    EvaluationDatasetSerializer, DatasetUploadSerializer,
    EvaluationConfigSerializer, ConfigUploadSerializer,
    EvaluationTaskSerializer, CreateEvaluationTaskSerializer,
    EvaluationResultSerializer, ModelBenchmarkSerializer,
    TaskProgressSerializer, ModelComparisonSerializer,
    ExportReportSerializer,
    BatchDeleteTasksSerializer, CleanupOldTasksSerializer  # 添加新的序列化器
)
from .tasks import run_evaluation_task
from .services import result_parser  # 如果需要的话

logger = logging.getLogger(__name__)

class EvaluationDatasetViewSet(viewsets.ModelViewSet):
    """评测数据集视图集"""
    queryset = EvaluationDataset.objects.filter(is_active=True)
    serializer_class = EvaluationDatasetSerializer
    permission_classes = [AllowAny]


    @action(detail=False, methods=['post'])
    def upload(self, request):
        """上传自定义数据集文件"""
        serializer = DatasetUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': '请提供数据集文件'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data

        # 验证文件类型
        allowed_extensions = ['.json', '.jsonl', '.csv']
        file_ext = Path(file.name).suffix.lower()

        if file_ext not in allowed_extensions:
            return Response(
                {'error': f'不支持的文件格式。支持的格式：{", ".join(allowed_extensions)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 验证数据集名称唯一性
        if EvaluationDataset.objects.filter(name=data['name']).exists():
            return Response(
                {'error': f'数据集名称 "{data["name"]}" 已存在'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 读取和验证文件内容
            content = file.read().decode('utf-8')
            parsed_data, sample_count = self._parse_and_validate_dataset(content, file_ext)

            # 保存文件到datasets目录
            from django.conf import settings
            datasets_dir = Path(settings.BASE_DIR) / 'evaluation' / 'opencompass_datasets'
            datasets_dir.mkdir(parents=True, exist_ok=True)

            # 使用数据集名称作为文件名
            filename = f"{data['name']}{file_ext}"
            file_path = datasets_dir / filename

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 创建数据库记录
            dataset = EvaluationDataset.objects.create(
                name=data['name'],
                display_name=data['display_name'],
                category=data['category'],
                description=data.get('description', ''),
                file_path=str(file_path),
                file_type=file_ext[1:],  # 去掉点号
                sample_count=sample_count,
                uploaded_by=request.user if request.user.is_authenticated else None
            )

            return Response({
                'id': dataset.id,
                'name': dataset.name,
                'display_name': dataset.display_name,
                'sample_count': dataset.sample_count,
                'message': f'数据集上传成功，包含 {sample_count} 个样本'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"上传数据集失败: {str(e)}")
            return Response(
                {'error': f'处理数据集时出错: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _parse_and_validate_dataset(self, content: str, file_ext: str):
        """解析并验证数据集内容"""
        data = []

        if file_ext == '.json':
            parsed = json.loads(content)
            if isinstance(parsed, list):
                data = parsed
            elif isinstance(parsed, dict) and 'data' in parsed:
                data = parsed['data']
            else:
                raise ValueError("JSON文件必须是数组或包含'data'字段的对象")

        elif file_ext == '.jsonl':
            for line_num, line in enumerate(content.strip().split('\n'), 1):
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        raise ValueError(f"第 {line_num} 行的JSON格式错误: {e}")

        elif file_ext == '.csv':
            import csv
            import io
            reader = csv.DictReader(io.StringIO(content))
            data = list(reader)

        # 基本验证
        if not data:
            raise ValueError("数据集为空")

        # 验证必需字段（根据需要调整）
        # 这里只做基本检查，具体验证可以根据数据集类型定制

        return data, len(data)

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """预览数据集内容"""
        dataset = self.get_object()
        preview_size = int(request.query_params.get('size', 10))

        try:
            with open(dataset.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析数据
            if dataset.file_type == 'json':
                data = json.loads(content)
                if isinstance(data, dict) and 'data' in data:
                    data = data['data']
            elif dataset.file_type == 'jsonl':
                data = [json.loads(line) for line in content.strip().split('\n') if line]
            else:
                # CSV处理
                import csv
                import io
                reader = csv.DictReader(io.StringIO(content))
                data = list(reader)

            return Response({
                'dataset': EvaluationDatasetSerializer(dataset).data,
                'total_samples': len(data),
                'preview_samples': data[:preview_size]
            })

        except Exception as e:
            return Response(
                {'error': f'读取数据集失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """下载数据集文件"""
        dataset = self.get_object()

        try:
            with open(dataset.file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{dataset.name}.{dataset.file_type}"'
                return response
        except Exception as e:
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EvaluationConfigViewSet(viewsets.ModelViewSet):
    """评测配置视图集"""
    queryset = EvaluationConfig.objects.filter(is_active=True)
    serializer_class = EvaluationConfigSerializer
    permission_classes = [AllowAny]
    @action(detail=True, methods=['get'])
    def preview_prompts(self, request, pk=None):
        """预览prompts"""
        config = self.get_object()
        return self.call_tool_service(
            'view_prompts',
            config.file_path,
            dataset_pattern=request.query_params.get('dataset'),
            count=int(request.query_params.get('count', 1))
        )

    @action(detail=True, methods=['post'])
    def test_model(self, request, pk=None):
        """测试API模型"""
        config = self.get_object()
        return self.call_tool_service('test_api_model', config.file_path)

    @action(detail=False, methods=['get'])
    def list_available(self, request):
        """列出可用配置"""
        return self.call_tool_service('list_available_configs', pattern=request.query_params.get('pattern'))

    @action(detail=True, methods=['get'])
    def preview_prompts(self, request, pk=None):
        """预览配置文件的prompt示例"""
        config = self.get_object()

        dataset_pattern = request.query_params.get('dataset', None)
        count = int(request.query_params.get('count', 1))

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.view_prompts(
                config.file_path,
                dataset_pattern=dataset_pattern,
                count=count
            )

            if result['success']:
                return Response({
                    'config_id': config.id,
                    'config_name': config.display_name,
                    'prompts': result['prompts']
                })
            else:
                return Response({
                    'error': '预览失败',
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Prompt preview failed: {e}")
            return Response({
                'error': f'预览失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def test_model(self, request, pk=None):
        """测试配置中的API模型"""
        config = self.get_object()

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.test_api_model(config.file_path)

            if result['success']:
                return Response({
                    'config_id': config.id,
                    'config_name': config.display_name,
                    'test_output': result['test_output'],
                    'message': result['message']
                })
            else:
                return Response({
                    'error': '测试失败',
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Model test failed: {e}")
            return Response({
                'error': f'测试失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def list_available(self, request):
        """列出所有可用的模型和数据集配置"""
        pattern = request.query_params.get('pattern', None)

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.list_available_configs(pattern)

            if result['success']:
                return Response({
                    'models': result['models'],
                    'opencompass_datasets': result['opencompass_datasets'],
                    'total_models': len(result['models']),
                    'total_datasets': len(result['opencompass_datasets'])
                })
            else:
                return Response({
                    'error': '获取配置列表失败',
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"List configs failed: {e}")
            return Response({
                'error': f'获取失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(
        detail=False,
        methods=['post'],
        parser_classes=[MultiPartParser, FormParser]  # 只在这个action中指定
    )
    def upload(self, request):
        """上传评测配置文件"""
        # 调试信息
        logger.info(f"Request FILES: {request.FILES}")
        logger.info(f"Request DATA: {request.data}")
        logger.info(f"Content-Type: {request.content_type}")

        # 检查是否有文件
        if not request.FILES:
            return Response(
                {'error': '请上传文件。确保使用 multipart/form-data 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ConfigUploadSerializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': '请提供配置文件'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 验证文件类型
        if not file.name.endswith('.py'):
            return Response(
                {'error': '配置文件必须是Python文件（.py）'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data

        try:
            # 读取文件内容
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')

            # 解析配置文件，提取模型和数据集信息
            parsed_info = self._parse_config_file(content)

            # 保存文件到configs目录
            configs_dir = Path(settings.BASE_DIR) / 'evaluation' / 'configs'
            configs_dir.mkdir(parents=True, exist_ok=True)

            # 生成唯一的文件名
            timestamp = int(timezone.now().timestamp())
            filename = f"{data['name']}_{timestamp}.py"
            file_path = configs_dir / filename

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 创建数据库记录
            config = EvaluationConfig.objects.create(
                name=data['name'],
                display_name=data['display_name'],
                description=data.get('description', ''),
                file_path=str(file_path),
                model_names=parsed_info['models'],
                dataset_names=parsed_info['opencompass_datasets'],
                config_type='opencompass',
                uploaded_by=request.user if request.user.is_authenticated else None
            )

            return Response({
                'id': config.id,
                'name': config.name,
                'display_name': config.display_name,
                'models': config.model_names,
                'opencompass_datasets': config.dataset_names,
                'message': '配置文件上传成功'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"上传配置文件失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'处理配置文件时出错: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _parse_config_file(self, content: str) -> dict:
        """解析配置文件，提取关键信息"""
        info = {
            'models': [],
            'opencompass_datasets': []
        }

        try:
            # 提取模型信息
            # 查找 models = [...] 或类似的模型定义
            model_pattern = r'models\s*=\s*\[(.*?)\]'
            model_match = re.search(model_pattern, content, re.DOTALL)
            if model_match:
                models_text = model_match.group(1)
                # 提取模型名称
                model_names = re.findall(r"(?:path|abbr|model)\s*=\s*['\"]([^'\"]+)['\"]", models_text)
                info['models'] = list(set(model_names))

            # 提取数据集信息
            # 查找数据集导入和使用
            dataset_imports = re.findall(r'from\s+.*?opencompass_datasets\.(\w+)', content)
            dataset_extends = re.findall(r'opencompass_datasets\.extend\((\w+)_datasets', content)
            dataset_names = re.findall(r"dataset['\"]?\s*:\s*['\"]([^'\"]+)['\"]", content)

            all_datasets = dataset_imports + dataset_extends + dataset_names
            info['opencompass_datasets'] = list(set(all_datasets))

            # 如果没有找到信息，尝试其他模式
            if not info['models']:
                # 尝试查找 dict(type=..., path=...) 格式
                dict_patterns = re.findall(r'dict\([^)]*path\s*=\s*[\'"]([^\'"]+)[\'"][^)]*\)', content)
                info['models'] = list(set(dict_patterns))

        except Exception as e:
            logger.warning(f"解析配置文件时出现警告: {e}")

        return info

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """预览配置文件内容"""
        config = self.get_object()

        try:
            with open(config.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            return Response({
                'config': EvaluationConfigSerializer(config).data,
                'content': content,
                'lines': len(content.split('\n'))
            })

        except Exception as e:
            return Response(
                {'error': f'读取配置文件失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """下载配置文件"""
        config = self.get_object()

        try:
            with open(config.file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='text/plain')
                response['Content-Disposition'] = f'attachment; filename="{Path(config.file_path).name}"'
                return response
        except Exception as e:
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """验证配置文件"""
        config = self.get_object()

        try:
            # 这里可以添加配置文件验证逻辑
            # 例如：检查语法、验证必需字段等
            validation_result = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'info': {
                    'models': config.model_names,
                    'opencompass_datasets': config.dataset_names
                }
            }

            # 基本验证
            if not config.model_names:
                validation_result['valid'] = False
                validation_result['errors'].append('配置文件中未找到模型定义')

            if not config.dataset_names:
                validation_result['warnings'].append('配置文件中未找到数据集定义')

            return Response(validation_result)

        except Exception as e:
            return Response(
                {'error': f'验证失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EvaluationTaskViewSet(viewsets.ModelViewSet):
    """评测任务视图集"""
    queryset = EvaluationTask.objects.all()
    serializer_class = EvaluationTaskSerializer
    permission_classes = [AllowAny]

    def destroy(self, request, *args, **kwargs):
        """重写默认的删除方法，支持删除文件选项"""
        task = self.get_object()

        # 检查任务状态
        if task.status == 'running':
            return Response({
                'error': '无法删除正在运行的任务',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        # 是否删除相关文件（从查询参数获取）
        delete_files = request.query_params.get('delete_files', 'false').lower() == 'true'

        try:
            task_info = {
                'id': task.id,
                'name': task.name,
                'status': task.status,
                'created_at': task.created_at
            }

            if delete_files:
                # 删除工作目录
                if task.work_dir:
                    service = EvaluationService()
                    work_dir = service.get_task_work_dir(task)

                    if work_dir and work_dir.exists():
                        import shutil
                        try:
                            shutil.rmtree(work_dir)
                            task_info['work_dir_deleted'] = True
                        except Exception as e:
                            logger.warning(f"Failed to delete work directory: {e}")
                            task_info['work_dir_deleted'] = False

                # 删除日志文件
                if task.log_file:
                    log_path = Path(task.log_file)
                    if not log_path.is_absolute():
                        log_path = Path(settings.BASE_DIR) / log_path

                    if log_path.exists():
                        try:
                            log_path.unlink()
                            task_info['log_file_deleted'] = True
                        except Exception as e:
                            logger.warning(f"Failed to delete log file: {e}")
                            task_info['log_file_deleted'] = False

            # 清理缓存
            cache.delete(f'evaluation_task_{task.id}')
            cache.delete(f'celery_task_{task.id}')

            # 执行删除
            self.perform_destroy(task)

            return Response({
                'message': '任务删除成功',
                'task': task_info
            }, status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Failed to delete task: {e}")
            return Response({
                'error': f'删除任务失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @action(detail=True, methods=['delete'])
    def delete_task(self, request, pk=None):
        """删除评测任务及相关数据"""
        task = self.get_object()

        # 检查任务状态
        if task.status == 'running':
            return Response({
                'error': '无法删除正在运行的任务',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        # 是否删除相关文件
        delete_files = request.query_params.get('delete_files', 'false').lower() == 'true'

        try:
            # 记录要删除的信息
            task_info = {
                'id': task.id,
                'name': task.name,
                'work_dir': task.work_dir,
                'log_file': task.log_file,
                'results_count': task.results.count()
            }

            # 如果需要删除文件
            if delete_files and task.work_dir:
                service = EvaluationService()
                work_dir = service.get_task_work_dir(task)

                if work_dir and work_dir.exists():
                    import shutil
                    try:
                        shutil.rmtree(work_dir)
                        logger.info(f"Deleted work directory: {work_dir}")
                        task_info['work_dir_deleted'] = True
                    except Exception as e:
                        logger.error(f"Failed to delete work directory: {e}")
                        task_info['work_dir_deleted'] = False
                        task_info['work_dir_error'] = str(e)

            # 删除日志文件
            if delete_files and task.log_file:
                log_path = Path(task.log_file)
                if not log_path.is_absolute():
                    log_path = Path(settings.BASE_DIR) / log_path

                if log_path.exists():
                    try:
                        log_path.unlink()
                        logger.info(f"Deleted log file: {log_path}")
                        task_info['log_file_deleted'] = True
                    except Exception as e:
                        logger.error(f"Failed to delete log file: {e}")
                        task_info['log_file_deleted'] = False
                        task_info['log_file_error'] = str(e)

            # 清理缓存
            cache.delete(f'evaluation_task_{task.id}')
            cache.delete(f'celery_task_{task.id}')

            # 删除任务（会级联删除相关的结果）
            task.delete()

            return Response({
                'message': '任务删除成功',
                'deleted_task': task_info
            })

        except Exception as e:
            logger.error(f"Failed to delete task {task.id}: {e}")
            return Response({
                'error': f'删除任务失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        """批量删除任务"""
        task_ids = request.data.get('task_ids', [])
        delete_files = request.data.get('delete_files', False)

        if not task_ids:
            return Response({
                'error': '请提供要删除的任务ID列表'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 获取任务
        tasks = EvaluationTask.objects.filter(id__in=task_ids)

        # 检查是否有运行中的任务
        running_tasks = tasks.filter(status='running')
        if running_tasks.exists():
            return Response({
                'error': '存在正在运行的任务，无法删除',
                'running_task_ids': list(running_tasks.values_list('id', flat=True))
            }, status=status.HTTP_400_BAD_REQUEST)

        deleted_tasks = []
        failed_tasks = []

        for task in tasks:
            try:
                task_info = {
                    'id': task.id,
                    'name': task.name
                }

                # 如果需要删除文件
                if delete_files:
                    if task.work_dir:
                        service = EvaluationService()
                        work_dir = service.get_task_work_dir(task)

                        if work_dir and work_dir.exists():
                            import shutil
                            try:
                                shutil.rmtree(work_dir)
                                task_info['work_dir_deleted'] = True
                            except Exception as e:
                                logger.error(f"Failed to delete work dir for task {task.id}: {e}")
                                task_info['work_dir_error'] = str(e)

                    if task.log_file:
                        log_path = Path(task.log_file)
                        if not log_path.is_absolute():
                            log_path = Path(settings.BASE_DIR) / log_path

                        if log_path.exists():
                            try:
                                log_path.unlink()
                                task_info['log_file_deleted'] = True
                            except Exception as e:
                                logger.error(f"Failed to delete log file for task {task.id}: {e}")
                                task_info['log_file_error'] = str(e)

                # 清理缓存
                cache.delete(f'evaluation_task_{task.id}')
                cache.delete(f'celery_task_{task.id}')

                # 删除任务
                task.delete()
                deleted_tasks.append(task_info)

            except Exception as e:
                logger.error(f"Failed to delete task {task.id}: {e}")
                failed_tasks.append({
                    'id': task.id,
                    'name': task.name,
                    'error': str(e)
                })

        return Response({
            'message': f'成功删除 {len(deleted_tasks)} 个任务',
            'deleted_tasks': deleted_tasks,
            'failed_tasks': failed_tasks,
            'total_requested': len(task_ids)
        })

    @action(detail=False, methods=['post'])
    def cleanup_old_tasks(self, request):
        """清理旧任务"""
        days = int(request.data.get('days', 30))
        status_filter = request.data.get('status', ['failed', 'cancelled'])
        delete_files = request.data.get('delete_files', True)
        dry_run = request.data.get('dry_run', False)

        from django.utils import timezone
        cutoff_date = timezone.now() - timezone.timedelta(days=days)

        # 查找要清理的任务
        old_tasks = EvaluationTask.objects.filter(
            created_at__lt=cutoff_date,
            status__in=status_filter
        )

        if dry_run:
            # 只返回将要删除的任务信息
            tasks_info = []
            for task in old_tasks[:100]:  # 限制预览数量
                tasks_info.append({
                    'id': task.id,
                    'name': task.name,
                    'status': task.status,
                    'created_at': task.created_at,
                    'work_dir': task.work_dir,
                    'has_results': task.results.exists()
                })

            return Response({
                'dry_run': True,
                'total_tasks': old_tasks.count(),
                'preview_tasks': tasks_info,
                'message': f'找到 {old_tasks.count()} 个超过 {days} 天的任务'
            })

        # 执行实际删除
        deleted_count = 0
        deleted_dirs = 0

        for task in old_tasks:
            try:
                # 删除文件
                if delete_files and task.work_dir:
                    service = EvaluationService()
                    work_dir = service.get_task_work_dir(task)

                    if work_dir and work_dir.exists():
                        import shutil
                        try:
                            shutil.rmtree(work_dir)
                            deleted_dirs += 1
                        except Exception as e:
                            logger.error(f"Failed to delete work dir: {e}")

                # 删除任务
                task.delete()
                deleted_count += 1

            except Exception as e:
                logger.error(f"Failed to cleanup task {task.id}: {e}")

        return Response({
            'message': '清理完成',
            'deleted_tasks': deleted_count,
            'deleted_directories': deleted_dirs,
            'cutoff_date': cutoff_date
        })
    @action(detail=True, methods=['get'])
    def files(self, request, pk=None):
        """获取任务相关的所有文件列表"""
        task = self.get_object()

        # 使用服务获取实际的工作目录
        service = EvaluationService()
        work_dir = service.get_task_work_dir(task)

        if not work_dir:
            # 如果工作目录还不存在，返回空列表而不是错误
            return Response({
                'task_id': task.id,
                'work_dir': None,
                'files': {
                    'logs': [],
                    'results': [],
                    'configs': [],
                    'others': []
                },
                'total_files': 0,
                'message': '工作目录尚未创建'
            })

        try:
            # 获取文件列表
            files = service.get_task_files(str(work_dir))

            return Response({
                'task_id': task.id,
                'work_dir': str(work_dir),
                'files': files,
                'total_files': sum(len(file_list) for file_list in files.values())
            })
        except Exception as e:
            logger.error(f"获取文件列表失败: {e}")
            return Response({
                'task_id': task.id,
                'work_dir': str(work_dir) if work_dir else None,
                'files': {
                    'logs': [],
                    'results': [],
                    'configs': [],
                    'others': []
                },
                'total_files': 0,
                'error': f'获取文件列表时出错: {str(e)}'
            })
    @action(detail=True, methods=['get'])
    def download_file(self, request, pk=None):
        """下载任务相关的文件"""
        task = self.get_object()

        # 获取文件路径参数
        file_path = request.query_params.get('path')
        if not file_path:
            return Response(
                {'error': '请提供文件路径参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not task.work_dir:
            return Response(
                {'error': '任务工作目录不存在'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 构建完整路径
        full_path = Path(task.work_dir) / file_path

        # 安全检查：确保文件在工作目录内
        try:
            full_path = full_path.resolve()
            work_dir_path = Path(task.work_dir).resolve()
            if not str(full_path).startswith(str(work_dir_path)):
                raise ValueError("Invalid file path")
        except:
            return Response(
                {'error': '无效的文件路径'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not full_path.exists():
            return Response(
                {'error': '文件不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 读取并返回文件
        try:
            # 判断文件类型
            content_type = 'application/octet-stream'
            if full_path.suffix == '.log':
                content_type = 'text/plain'
            elif full_path.suffix == '.json':
                content_type = 'application/json'
            elif full_path.suffix == '.py':
                content_type = 'text/x-python'
            elif full_path.suffix == '.out':
                content_type = 'text/plain'

            with open(full_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type=content_type)
                response['Content-Disposition'] = f'inline; filename="{full_path.name}"'
                return response

        except Exception as e:
            return Response(
                {'error': f'读取文件失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def output_structure(self, request, pk=None):
        """获取输出目录结构（树形）"""
        task = self.get_object()

        if not task.work_dir or not Path(task.work_dir).exists():
            return Response({
                'error': '工作目录不存在',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        def build_tree(path: Path, base_path: Path) -> dict:
            """递归构建目录树"""
            tree = {
                'name': path.name,
                'path': str(path.relative_to(base_path)),
                'type': 'directory' if path.is_dir() else 'file',
                'children': []
            }

            if path.is_file():
                tree['size'] = path.stat().st_size
                tree['modified'] = path.stat().st_mtime
            else:
                # 目录：递归处理子项
                for child in sorted(path.iterdir()):
                    tree['children'].append(build_tree(child, base_path))

            return tree

        work_path = Path(task.work_dir)
        tree = build_tree(work_path, work_path.parent)

        return Response({
            'task_id': task.id,
            'work_dir': task.work_dir,
            'tree': tree
        })

    @action(detail=True, methods=['get'])
    def latest_log(self, request, pk=None):
        """获取最新的日志内容（尾部N行）"""
        task = self.get_object()

        # 行数参数
        lines = int(request.query_params.get('lines', 100))

        # 查找日志文件
        log_files = []

        # 主日志文件
        if task.log_file:
            log_path = Path(task.log_file)
            # 如果是相对路径，转换为绝对路径
            if not log_path.is_absolute():
                log_path = Path(settings.BASE_DIR) / log_path
            if log_path.exists():
                log_files.append(log_path)

        # 工作目录中的日志
        if task.work_dir:
            # 使用服务获取实际的工作目录
            service = EvaluationService()
            work_path = service.get_task_work_dir(task)
            if work_path and work_path.exists():
                log_files.extend(work_path.rglob('*.log'))

        if not log_files:
            # 返回空内容而不是404，这样前端可以继续轮询
            return Response({
                'task_id': task.id,
                'log_file': None,
                'content': '',
                'total_lines': 0,
                'returned_lines': 0,
                'message': '日志文件尚未生成'
            })

        # 找到最新的日志文件
        latest_log = max(log_files, key=lambda f: f.stat().st_mtime)

        try:
            with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                # 读取最后N行
                all_lines = f.readlines()
                tail_lines = all_lines[-lines:]
                content = ''.join(tail_lines)

            return Response({
                'task_id': task.id,
                'log_file': str(latest_log),
                'content': content,
                'total_lines': len(all_lines),
                'returned_lines': len(tail_lines)
            })

        except Exception as e:
            logger.error(f"读取日志失败: {e}")
            return Response({
                'task_id': task.id,
                'log_file': str(latest_log),
                'content': '',
                'total_lines': 0,
                'returned_lines': 0,
                'error': f'读取日志时出错: {str(e)}'
            })

    @action(detail=True, methods=['get'])
    def parse_results(self, request, pk=None):
        """重新解析任务结果"""
        task = self.get_object()

        if task.status != 'completed':
            return Response({
                'error': '只能解析已完成的任务',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        if not task.work_dir:
            return Response({
                'error': '工作目录不存在'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 使用服务重新解析结果
            service = EvaluationService()
            work_path = Path(task.work_dir)
            results = service._parse_results_from_work_dir(work_path)

            # 可选：重新保存到数据库
            if request.query_params.get('save', 'false').lower() == 'true':
                # 清除旧结果
                task.results.all().delete()
                # 保存新结果
                service.save_results(task, {'results': results})

            return Response({
                'task_id': task.id,
                'work_dir': task.work_dir,
                'results': results,
                'message': '结果解析成功'
            })

        except Exception as e:
            return Response(
                {'error': f'解析失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    def get_queryset(self):
        queryset = super().get_queryset()

        # 支持状态筛选
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # 支持配置筛选
        config_id = self.request.query_params.get('config')
        if config_id:
            queryset = queryset.filter(config_id=config_id)

        # 用户过滤
        if self.request.user.is_authenticated:
            queryset = queryset.filter(user=self.request.user)

        return queryset.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def analyze_bad_cases(self, request, pk=None):
        """分析错误案例"""
        task = self.get_object()
        if task.status != 'completed':
            return Response({'error': '只能分析已完成的任务'}, status=status.HTTP_400_BAD_REQUEST)

        return self.call_tool_service('analyze_bad_cases', task.id, force=request.data.get('force', False))

    @action(detail=True, methods=['post'])
    def merge_predictions(self, request, pk=None):
        """合并预测结果"""
        task = self.get_object()
        return self.call_tool_service('merge_predictions', task.id, clean=request.data.get('clean', False))

    @action(detail=True, methods=['post'])
    def collect_code_predictions(self, request, pk=None):
        """收集代码预测"""
        task = self.get_object()
        if task.status != 'completed':
            return Response({'error': '只能收集已完成任务的预测'}, status=status.HTTP_400_BAD_REQUEST)

        return self.call_tool_service('collect_code_predictions', task.id)

    @action(detail=False, methods=['post'])
    def compare_models(self, request):
        """对比模型"""
        task_ids = request.data.get('task_ids', [])
        if len(task_ids) < 2:
            return Response({'error': '至少需要2个任务进行对比'}, status=status.HTTP_400_BAD_REQUEST)

        return self.call_tool_service('compare_models', task_ids)
    @action(detail=True, methods=['post'])
    def analyze_bad_cases(self, request, pk=None):
        """分析任务的错误案例"""
        task = self.get_object()

        if task.status != 'completed':
            return Response({
                'error': '只能分析已完成的任务',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        force = request.data.get('force', False)

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.analyze_bad_cases(task.id, force=force)

            if result['success']:
                return Response({
                    'task_id': task.id,
                    'bad_cases_count': result['bad_cases_count'],
                    'bad_cases': result['bad_cases'],
                    'files': result['files'],
                    'message': '错误案例分析完成'
                })
            else:
                return Response({
                    'error': result.get('error', '分析失败'),
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Bad case analysis failed: {e}")
            return Response({
                'error': f'分析失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def merge_predictions(self, request, pk=None):
        """合并分片的预测结果"""
        task = self.get_object()

        clean = request.data.get('clean', False)

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.merge_predictions(task.id, clean=clean)

            if result['success']:
                return Response({
                    'task_id': task.id,
                    'message': '预测结果合并完成',
                    'output': result.get('stdout', '')
                })
            else:
                return Response({
                    'error': '合并失败',
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Prediction merge failed: {e}")
            return Response({
                'error': f'合并失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def collect_code_predictions(self, request, pk=None):
        """收集代码评测预测结果"""
        task = self.get_object()

        if task.status != 'completed':
            return Response({
                'error': '只能收集已完成任务的预测结果',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.collect_code_predictions(task.id)

            if result['success']:
                return Response({
                    'task_id': task.id,
                    'result_files': result['result_files'],
                    'message': result['message']
                })
            else:
                return Response({
                    'error': '收集失败',
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Code prediction collection failed: {e}")
            return Response({
                'error': f'收集失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def compare_models(self, request):
        """对比多个模型的结果"""
        task_ids = request.data.get('task_ids', [])

        if len(task_ids) < 2:
            return Response({
                'error': '至少需要选择2个任务进行对比'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            result = tools_service.compare_model_results(task_ids)

            if result['success']:
                # 解析比较结果
                output = result.get('stdout', '')

                return Response({
                    'task_ids': task_ids,
                    'comparison_output': output,
                    'message': '模型对比完成'
                })
            else:
                return Response({
                    'error': '对比失败',
                    'details': result
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Model comparison failed: {e}")
            return Response({
                'error': f'对比失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @action(detail=False, methods=['post'])
    def create_task(self, request):
        """创建评测任务"""
        serializer = CreateEvaluationTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        config = EvaluationConfig.objects.get(id=data['config_id'])

        # 生成任务名称
        if not data.get('name'):
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            data['name'] = f"{config.display_name} - {timestamp}"

        # 创建任务
        task = EvaluationTask.objects.create(
            name=data['name'],
            user=request.user if request.user.is_authenticated else None,
            config=config
        )

        try:
            # 异步运行评测
            from .tasks import run_evaluation_task
            celery_task = run_evaluation_task.delay(task.id)
            cache.set(f'celery_task_{task.id}', celery_task.id, 86400)  # 保存24小时

            logger.info(f"Created task {task.id} with Celery task {celery_task.id}")

            return Response({
                'id': task.id,
                'name': task.name,
                'status': task.status,
                'celery_task_id': celery_task.id,
                'message': '评测任务已创建并开始运行'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Failed to start Celery task: {e}")
            # 如果Celery失败，返回任务ID但提示需要手动运行
            return Response({
                'id': task.id,
                'name': task.name,
                'status': task.status,
                'message': '任务已创建，但自动运行失败，请使用同步运行',
                'error': str(e)
            }, status=status.HTTP_201_CREATED)

    # 在 evaluation/views.py 的 EvaluationTaskViewSet 类中添加

    @action(detail=True, methods=['get'])
    def debug_info(self, request, pk=None):
        """获取任务的调试信息"""
        task = self.get_object()

        # 检查Celery任务状态
        celery_task_id = cache.get(f'celery_task_{task.id}')

        celery_status = None
        if celery_task_id:
            try:
                from celery.result import AsyncResult
                result = AsyncResult(celery_task_id)
                celery_status = {
                    'id': celery_task_id,
                    'state': result.state,
                    'info': str(result.info) if result.info else None
                }
            except Exception as e:
                celery_status = {'error': str(e)}

        return Response({
            'task_id': task.id,
            'status': task.status,
            'work_dir': task.work_dir,
            'log_file': task.log_file,
            'config_path': task.config.file_path if task.config else None,
            'config_id': task.config.id if task.config else None,
            'celery_status': celery_status,
            'created_at': task.created_at,
            'started_at': task.started_at,
            'progress': task.progress,
        })

    @action(detail=True, methods=['post'])
    def run_sync(self, request, pk=None):
        """同步运行任务（用于调试）"""
        task = self.get_object()

        if task.status == 'running':
            return Response(
                {'error': '任务正在运行中'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 重置任务状态
            task.status = 'pending'
            task.progress = 0
            task.error_message = ''
            task.save()

            # 直接运行评测服务
            service = EvaluationService()
            task.start()

            def progress_callback(data):
                logger.info(f"Progress: {data}")
                task.progress = data.get('progress', 0)
                task.save(update_fields=['progress'])

            results = service.run_evaluation(
                task_id=task.id,
                config_path=task.config.file_path,
                progress_callback=progress_callback
            )

            # 保存结果
            service.save_results(task, results)
            task.complete()

            return Response({
                'message': '任务执行完成',
                'work_dir': results.get('work_dir'),
                'log_file': results.get('log_file'),
                'duration': results.get('duration')
            })

        except Exception as e:
            logger.error(f"Sync run failed: {e}", exc_info=True)
            task.fail(str(e))
            return Response(
                {'error': f'任务执行失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """获取任务进度"""
        task = self.get_object()

        # 获取日志预览
        log_preview = None
        if task.log_file:
            try:
                log_path = Path(task.log_file)
                # 如果是相对路径，转换为绝对路径
                if not log_path.is_absolute():
                    log_path = Path(settings.BASE_DIR) / log_path

                if log_path.exists():
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        # 读取最后50行
                        lines = f.readlines()
                        log_preview = ''.join(lines[-50:])
            except Exception as e:
                logger.warning(f"读取日志预览失败: {e}")

        # 获取任务运行时长
        duration = None
        if task.started_at:
            if task.completed_at:
                duration = (task.completed_at - task.started_at).total_seconds()
            else:
                # 任务仍在运行
                from django.utils import timezone
                duration = (timezone.now() - task.started_at).total_seconds()

        return Response({
            'task_id': task.id,
            'status': task.status,
            'progress': task.progress,
            'error_message': task.error_message,
            'log_preview': log_preview,
            'started_at': task.started_at,
            'completed_at': task.completed_at,
            'duration': duration
        })

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        """获取任务结果"""
        task = self.get_object()

        if task.status != 'completed':
            return Response({
                'error': '任务尚未完成',
                'status': task.status
            }, status=status.HTTP_400_BAD_REQUEST)

        results = task.results.all()

        # 按模型和数据集分组
        grouped_results = {}
        for result in results:
            model = result.model_name
            dataset = result.dataset_name

            if model not in grouped_results:
                grouped_results[model] = {}

            if dataset not in grouped_results[model]:
                grouped_results[model][dataset] = {}

            grouped_results[model][dataset][result.metric_name] = {
                'value': result.metric_value,
                'unit': result.metric_unit,
                'details': result.details
            }

        return Response({
            'task': EvaluationTaskSerializer(task).data,
            'results': grouped_results,
            'total_results': results.count()
        })

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """获取任务日志"""
        task = self.get_object()

        if not task.log_file or not Path(task.log_file).exists():
            return Response(
                {'error': '日志文件不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            with open(task.log_file, 'rb') as f:
                response = HttpResponse(f.read(), content_type='text/plain')
                response['Content-Disposition'] = f'inline; filename="task_{task.id}.log"'
                return response
        except Exception as e:
            return Response(
                {'error': f'读取日志失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """取消任务"""
        task = self.get_object()

        if task.status in ['completed', 'failed', 'cancelled']:
            return Response(
                {'error': '任务已结束，无法取消'},
                status=status.HTTP_400_BAD_REQUEST
            )

        task.status = 'cancelled'
        task.save()

        # 清理缓存
        cache.delete(f'evaluation_task_{task.id}')

        return Response({'message': '任务已取消'})

    @action(detail=True, methods=['post'])
    def rerun(self, request, pk=None):
        """重新运行任务"""
        task = self.get_object()

        # 创建新任务
        new_task = EvaluationTask.objects.create(
            name=f"{task.name} (重新运行)",
            user=task.user,
            config=task.config
        )

        # 异步运行
        run_evaluation_task.delay(new_task.id)

        return Response({
            'id': new_task.id,
            'name': new_task.name,
            'status': new_task.status,
            'original_task_id': task.id,
            'message': '新任务已创建并开始运行'
        })




class ToolsMixin:
    """工具调用的通用Mixin"""

    def call_tool_service(self, method_name: str, *args, **kwargs):
        """通用的工具服务调用包装器"""
        try:
            from .services import OpenCompassToolsService
            tools_service = OpenCompassToolsService()
            method = getattr(tools_service, method_name)
            result = method(*args, **kwargs)

            if result.get('success'):
                return Response(result)
            else:
                return Response(
                    {'error': result.get('error', '操作失败'), 'details': result},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        except Exception as e:
            logger.error(f"{method_name} failed: {e}")
            return Response(
                {'error': f'操作失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# 简化的工具ViewSet
class OpenCompassToolsViewSet(ToolsMixin, viewsets.ViewSet):
    """OpenCompass工具集视图"""
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def convert_alignment_bench(self, request):
        """转换AlignmentBench格式"""
        mode = request.data.get('mode', 'json')
        if mode not in ['json', 'csv']:
            return Response({'error': '无效的模式'}, status=status.HTTP_400_BAD_REQUEST)

        # 直接调用工具脚本
        args = ['--mode', mode]
        if mode == 'json':
            args.extend(['--jsonl', request.data.get('jsonl_path', '')])
            args.extend(['--json', request.data.get('json_path', '')])
        else:
            args.extend(['--exp-folder', request.data.get('exp_folder', '')])

        from .services import OpenCompassToolsService
        service = OpenCompassToolsService()
        result = service._run_tool('convert_alignmentbench.py', args)

        if result['success']:
            return Response({'mode': mode, 'message': '转换完成', 'output': result.get('stdout', '')})
        else:
            return Response({'error': '转换失败', 'details': result}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class ModelBenchmarkViewSet(viewsets.ReadOnlyModelViewSet):
    """模型基准视图集"""
    queryset = ModelBenchmark.objects.all()
    serializer_class = ModelBenchmarkSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """获取模型排行榜"""
        # 获取排序字段
        sort_by = request.query_params.get('sort_by', 'overall_score')
        order = request.query_params.get('order', 'desc')

        # 构建排序
        order_by = f"-{sort_by}" if order == 'desc' else sort_by

        benchmarks = self.queryset.order_by(order_by)[:50]

        # 构建排行榜数据
        leaderboard = []
        for rank, benchmark in enumerate(benchmarks, 1):
            data = ModelBenchmarkSerializer(benchmark).data
            data['rank'] = rank
            leaderboard.append(data)

        return Response({
            'leaderboard': leaderboard,
            'sort_by': sort_by,
            'order': order,
            'total_models': self.queryset.count()
        })

    @action(detail=False, methods=['post'])
    def compare(self, request):
        """对比多个模型"""
        serializer = ModelComparisonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        model_names = serializer.validated_data['model_names']
        datasets = serializer.validated_data.get('opencompass_datasets', [])

        # 获取模型数据
        models_data = []
        for model_name in model_names:
            try:
                benchmark = ModelBenchmark.objects.get(model_name=model_name)
                model_data = ModelBenchmarkSerializer(benchmark).data

                # 如果指定了数据集，只返回相关的指标
                if datasets:
                    filtered_metrics = {}
                    for dataset in datasets:
                        if dataset in model_data['metrics']:
                            filtered_metrics[dataset] = model_data['metrics'][dataset]
                    model_data['metrics'] = filtered_metrics

                models_data.append(model_data)
            except ModelBenchmark.DoesNotExist:
                models_data.append({
                    'model_name': model_name,
                    'error': '该模型尚未进行评测'
                })

        return Response({
            'models': models_data,
            'comparison_datasets': datasets
        })

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """获取模型的评测历史"""
        benchmark = self.get_object()

        # 获取该模型的所有评测任务
        tasks = EvaluationTask.objects.filter(
            config__model_names__contains=benchmark.model_name,
            status='completed'
        ).order_by('-completed_at')[:50]

        history = []
        for task in tasks:
            # 获取该任务中该模型的结果
            results = task.results.filter(model_name=benchmark.model_name)

            task_data = {
                'task_id': task.id,
                'config_name': task.config.display_name,
                'completed_at': task.completed_at,
                'opencompass_datasets': list(results.values_list('dataset_name', flat=True).distinct()),
                'metrics': {}
            }

            # 汇总指标
            for result in results:
                if result.dataset_name not in task_data['metrics']:
                    task_data['metrics'][result.dataset_name] = {}
                task_data['metrics'][result.dataset_name][result.metric_name] = result.metric_value

            history.append(task_data)

        return Response({
            'model_name': benchmark.model_name,
            'history': history,
            'total_evaluations': benchmark.total_evaluations
        })

    @action(detail=False, methods=['get'])
    def export_report(self, request):
        """导出评测报告"""
        serializer = ExportReportSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        task_ids = serializer.validated_data['task_ids']
        format_type = serializer.validated_data['format']
        include_raw = serializer.validated_data['include_raw_results']

        # 获取任务和结果
        tasks = EvaluationTask.objects.filter(id__in=task_ids, status='completed')

        if format_type == 'json':
            # JSON格式导出
            report_data = []
            for task in tasks:
                task_data = {
                    'task': EvaluationTaskSerializer(task).data,
                    'results': []
                }

                for result in task.results.all():
                    result_data = EvaluationResultSerializer(result).data
                    if not include_raw:
                        result_data.pop('raw_results', None)
                    task_data['results'].append(result_data)

                report_data.append(task_data)

            response = HttpResponse(
                json.dumps(report_data, ensure_ascii=False, indent=2),
                content_type='application/json'
            )
            response[
                'Content-Disposition'] = f'attachment; filename="evaluation_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'

        elif format_type == 'csv':
            # CSV格式导出
            import csv
            from io import StringIO

            output = StringIO()
            writer = csv.writer(output)

            # 写入表头
            headers = ['Task ID', 'Task Name', 'Config', 'Model', 'Dataset', 'Metric', 'Value', 'Unit', 'Completed At']
            writer.writerow(headers)

            # 写入数据
            for task in tasks:
                for result in task.results.all():
                    writer.writerow([
                        task.id,
                        task.name,
                        task.config.display_name,
                        result.model_name,
                        result.dataset_name,
                        result.metric_name,
                        result.metric_value,
                        result.metric_unit,
                        task.completed_at.strftime('%Y-%m-%d %H:%M:%S') if task.completed_at else ''
                    ])

            response = HttpResponse(output.getvalue(), content_type='text/csv')
            response[
                'Content-Disposition'] = f'attachment; filename="evaluation_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        else:  # markdown
            # Markdown格式导出
            lines = ['# 评测报告\n']
            lines.append(f'生成时间：{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}\n')

            for task in tasks:
                lines.append(f'\n## {task.name}\n')
                lines.append(f'- 配置：{task.config.display_name}\n')
                lines.append(f'- 状态：{task.get_status_display()}\n')
                lines.append(
                    f'- 完成时间：{task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else "N/A"}\n')

                # 按模型分组结果
                results_by_model = {}
                for result in task.results.all():
                    if result.model_name not in results_by_model:
                        results_by_model[result.model_name] = []
                    results_by_model[result.model_name].append(result)

                for model_name, results in results_by_model.items():
                    lines.append(f'\n### 模型：{model_name}\n')

                    # 创建表格
                    lines.append('| 数据集 | 指标 | 值 | 单位 |\n')
                    lines.append('|--------|------|-----|------|\n')

                    for result in results:
                        lines.append(
                            f'| {result.dataset_name} | {result.metric_name} | {result.metric_value:.2f} | {result.metric_unit} |\n')

            response = HttpResponse(''.join(lines), content_type='text/markdown')
            response[
                'Content-Disposition'] = f'attachment; filename="evaluation_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.md"'

        return response

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """获取统计信息"""
        stats = {
            'total_models': ModelBenchmark.objects.count(),
            'total_evaluations': EvaluationTask.objects.filter(status='completed').count(),
            'total_datasets': EvaluationDataset.objects.filter(is_active=True).count(),
            'total_configs': EvaluationConfig.objects.filter(is_active=True).count(),

            'recent_evaluations': EvaluationTask.objects.filter(
                status='completed',
                completed_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),

            'top_models': list(
                ModelBenchmark.objects.order_by('-overall_score')[:5].values(
                    'model_name', 'overall_score'
                )
            ),

            'evaluation_by_status': dict(
                EvaluationTask.objects.values('status').annotate(count=Count('id')).values_list('status', 'count')
            )
        }

        return Response(stats)