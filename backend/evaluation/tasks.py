# evaluation/tasks.py
"""评测异步任务"""
from celery import shared_task
import logging
from django.core.cache import cache
from django.utils import timezone

from .models import EvaluationTask, ModelBenchmark
from .services import EvaluationService, ResultParser

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_evaluation_task(self, task_id):
    """运行评测任务"""
    logger.info(f"Starting evaluation task {task_id}")

    try:
        task = EvaluationTask.objects.get(id=task_id)
        task.start()

        # 获取配置文件路径
        config_path = task.config.file_path

        # 创建评测服务
        service = EvaluationService()

        # 进度回调
        def progress_callback(data):
            # 更新进度
            progress = data.get('progress', 0)
            task.progress = progress
            task.save(update_fields=['progress'])

            # 更新Celery任务状态
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'Progress: {progress}%'
                }
            )

            # 缓存进度信息
            cache.set(f'evaluation_task_{task_id}', {
                'progress': progress,
                'log_file': data.get('log_file')
            }, 300)

        # 运行评测
        results = service.run_evaluation(
            task_id=task_id,
            config_path=config_path,
            progress_callback=progress_callback
        )

        # 保存结果
        service.save_results(task, results)

        # 完成任务
        task.complete()

        # 清理缓存
        cache.delete(f'evaluation_task_{task_id}')

        logger.info(f"Task {task_id} completed successfully")

        return {
            'status': 'success',
            'task_id': task_id,
            'results_count': task.results.count()
        }

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)

        if 'task' in locals():
            task.fail(str(e))

        # 清理缓存
        cache.delete(f'evaluation_task_{task_id}')

        # 重新抛出异常以便Celery记录
        raise


@shared_task
def update_model_benchmarks():
    """定期更新所有模型的基准分数"""
    logger.info("Updating model benchmarks")

    try:
        # 获取所有已完成的任务
        completed_tasks = EvaluationTask.objects.filter(
            status='completed',
            results__isnull=False
        ).distinct()

        # 收集所有模型
        models = set()
        for task in completed_tasks:
            for model_name in task.config.model_names:
                models.add(model_name)

        # 更新每个模型的基准
        for model_name in models:
            update_single_model_benchmark.delay(model_name)

        logger.info(f"Scheduled benchmark updates for {len(models)} models")

    except Exception as e:
        logger.error(f"Failed to update benchmarks: {e}")


@shared_task
def update_single_model_benchmark(model_name: str):
    """更新单个模型的基准分数"""
    logger.info(f"Updating benchmark for {model_name}")

    try:
        from django.db.models import Avg, Count
        from .models import EvaluationResult

        # 获取或创建基准记录
        benchmark, created = ModelBenchmark.objects.get_or_create(
            model_name=model_name
        )

        # 获取该模型的所有结果
        results = EvaluationResult.objects.filter(
            model_name=model_name,
            task__status='completed'
        )

        if not results.exists():
            logger.warning(f"No results found for model {model_name}")
            return

        # 计算综合评分
        metrics = {}
        category_scores = {}

        # 按数据集分组计算平均分
        dataset_scores = results.values('dataset_name').annotate(
            avg_score=Avg('metric_value'),
            count=Count('id')
        )

        for item in dataset_scores:
            dataset_name = item['dataset_name']
            avg_score = item['avg_score']

            if dataset_name not in metrics:
                metrics[dataset_name] = {}

            metrics[dataset_name]['average_score'] = avg_score

            # 获取数据集类别
            from .models import EvaluationDataset
            try:
                dataset = EvaluationDataset.objects.get(name=dataset_name)
                category = dataset.category

                if category not in category_scores:
                    category_scores[category] = []
                category_scores[category].append(avg_score)
            except EvaluationDataset.DoesNotExist:
                pass

        # 计算各类别平均分
        for category, scores in category_scores.items():
            category_scores[category] = sum(scores) / len(scores) if scores else 0

        # 计算总体平均分
        all_scores = []
        for dataset_metrics in metrics.values():
            if 'average_score' in dataset_metrics:
                all_scores.append(dataset_metrics['average_score'])

        overall_score = sum(all_scores) / len(all_scores) if all_scores else 0

        # 更新基准
        benchmark.overall_score = overall_score
        benchmark.category_scores = category_scores
        benchmark.metrics = metrics
        benchmark.total_evaluations = results.values('task').distinct().count()
        benchmark.datasets_evaluated = list(results.values_list('dataset_name', flat=True).distinct())
        benchmark.last_evaluated = timezone.now()
        benchmark.save()

        logger.info(f"Updated benchmark for {model_name}: overall_score={overall_score:.2f}")

    except Exception as e:
        logger.error(f"Failed to update benchmark for {model_name}: {e}")


@shared_task
def cleanup_old_results(days=30):
    """清理旧的评测结果"""
    logger.info(f"Cleaning up results older than {days} days")

    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days)

        # 删除旧任务
        old_tasks = EvaluationTask.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['failed', 'cancelled']
        )

        count = old_tasks.count()
        old_tasks.delete()

        logger.info(f"Deleted {count} old tasks")

        # 清理工作目录
        from pathlib import Path
        from django.conf import settings

        outputs_dir = Path(settings.BASE_DIR) / 'evaluation' / 'outputs'
        if outputs_dir.exists():
            for task_dir in outputs_dir.iterdir():
                if task_dir.is_dir():
                    # 检查目录年龄
                    mtime = task_dir.stat().st_mtime
                    age_days = (timezone.now().timestamp() - mtime) / 86400

                    if age_days > days:
                        import shutil
                        shutil.rmtree(task_dir)
                        logger.info(f"Removed old directory: {task_dir}")

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")


@shared_task
def parse_evaluation_logs(task_id: int):
    """解析评测日志提取额外信息"""
    logger.info(f"Parsing logs for task {task_id}")

    try:
        task = EvaluationTask.objects.get(id=task_id)

        if not task.log_file:
            logger.warning(f"No log file for task {task_id}")
            return

        from pathlib import Path
        log_path = Path(task.log_file)

        if not log_path.exists():
            logger.warning(f"Log file not found: {log_path}")
            return

        # 使用结果解析器
        parser = ResultParser()
        additional_results = parser.parse_log_file(log_path)

        if additional_results:
            # 保存额外的结果
            from .models import EvaluationResult

            for model_name, model_data in additional_results.items():
                if isinstance(model_data, dict):
                    for dataset_name, metrics in model_data.items():
                        if isinstance(metrics, dict):
                            for metric_name, value in metrics.items():
                                # 检查是否已存在
                                exists = EvaluationResult.objects.filter(
                                    task=task,
                                    model_name=model_name,
                                    dataset_name=dataset_name,
                                    metric_name=metric_name
                                ).exists()

                                if not exists and isinstance(value, (int, float)):
                                    EvaluationResult.objects.create(
                                        task=task,
                                        model_name=model_name,
                                        dataset_name=dataset_name,
                                        metric_name=metric_name,
                                        metric_value=value,
                                        metric_unit='score',
                                        details={'source': 'log_parser'}
                                    )

            logger.info(f"Extracted additional results from logs for task {task_id}")

    except Exception as e:
        logger.error(f"Failed to parse logs for task {task_id}: {e}")