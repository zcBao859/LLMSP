# evaluation/serializers.py
from rest_framework import serializers
from .models import (
    EvaluationDataset, EvaluationConfig, EvaluationTask,
    EvaluationResult, ModelBenchmark,
    BadCaseAnalysis, PromptAnalysis, ModelComparison  # 新增模型导入
)


# 基础序列化器类
class BaseTimestampSerializer(serializers.ModelSerializer):
    """带时间戳的基础序列化器"""

    class Meta:
        abstract = True
        read_only_fields = ['created_at', 'updated_at']


class BaseUserSerializer(BaseTimestampSerializer):
    """带用户信息的基础序列化器"""
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        abstract = True


# 原有的序列化器
class EvaluationDatasetSerializer(serializers.ModelSerializer):
    """评测数据集序列化器"""
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = EvaluationDataset
        fields = [
            'id', 'name', 'display_name', 'category', 'description',
            'file_path', 'file_type', 'sample_count', 'uploaded_by',
            'uploaded_by_username', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['file_path', 'file_type', 'sample_count', 'created_at', 'updated_at']


class DatasetUploadSerializer(serializers.Serializer):
    """数据集上传序列化器"""
    file = serializers.FileField(required=True, help_text="数据集文件（.json, .jsonl, .csv）")
    name = serializers.CharField(max_length=100, help_text="数据集名称（唯一标识）")
    display_name = serializers.CharField(max_length=200, help_text="显示名称")
    category = serializers.ChoiceField(
        choices=['safety', 'bias', 'toxicity', 'privacy', 'robustness', 'ethics', 'factuality', 'custom'],
        default='custom',
        help_text="数据集类别"
    )
    description = serializers.CharField(required=False, allow_blank=True, help_text="数据集描述")


class EvaluationConfigSerializer(serializers.ModelSerializer):
    """评测配置序列化器"""
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = EvaluationConfig
        fields = [
            'id', 'name', 'display_name', 'description', 'file_path',
            'model_names', 'dataset_names', 'config_type',
            'uploaded_by', 'uploaded_by_username', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'file_path', 'model_names', 'dataset_names', 'config_type',
            'created_at', 'updated_at'
        ]


class ConfigUploadSerializer(serializers.Serializer):
    """配置文件上传序列化器"""
    file = serializers.FileField(required=True, help_text="OpenCompass配置文件（.py）")
    name = serializers.CharField(max_length=200, help_text="配置名称")
    display_name = serializers.CharField(max_length=200, help_text="显示名称")
    description = serializers.CharField(required=False, allow_blank=True, help_text="配置描述")


class EvaluationTaskSerializer(serializers.ModelSerializer):
    """评测任务序列化器"""
    config_name = serializers.CharField(source='config.display_name', read_only=True)
    model_names = serializers.JSONField(source='config.model_names', read_only=True)
    dataset_names = serializers.JSONField(source='config.dataset_names', read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = EvaluationTask
        fields = [
            'id', 'name', 'user', 'config', 'config_name',
            'model_names', 'dataset_names', 'status',
            'created_at', 'started_at', 'completed_at',
            'work_dir', 'log_file', 'progress', 'error_message',
            'duration', 'cpu_seconds', 'memory_peak_mb'
        ]
        read_only_fields = [
            'work_dir', 'log_file', 'created_at', 'started_at',
            'completed_at', 'cpu_seconds', 'memory_peak_mb'
        ]

    def get_duration(self, obj):
        return obj.duration


class CreateEvaluationTaskSerializer(serializers.Serializer):
    """创建评测任务序列化器"""
    name = serializers.CharField(
        required=False,
        max_length=200,
        help_text="任务名称"
    )
    config_id = serializers.IntegerField(
        required=True,
        help_text="配置文件ID"
    )
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high'],
        default='normal',
        required=False,
        help_text="任务优先级"
    )

    def validate_config_id(self, value):
        try:
            EvaluationConfig.objects.get(id=value, is_active=True)
        except EvaluationConfig.DoesNotExist:
            raise serializers.ValidationError("配置文件不存在或未激活")
        return value


class EvaluationResultSerializer(serializers.ModelSerializer):
    """评测结果序列化器"""

    class Meta:
        model = EvaluationResult
        fields = [
            'id', 'task', 'model_name', 'dataset_name',
            'metric_name', 'metric_value', 'metric_unit',
            'details', 'raw_results', 'created_at'
        ]


class ModelBenchmarkSerializer(serializers.ModelSerializer):
    """模型基准序列化器"""
    rank = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = ModelBenchmark
        fields = [
            'id', 'model_name', 'overall_score', 'category_scores',
            'metrics', 'total_evaluations', 'datasets_evaluated',
            'last_evaluated', 'created_at', 'updated_at', 'rank'
        ]


class TaskProgressSerializer(serializers.Serializer):
    """任务进度序列化器"""
    task_id = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    progress = serializers.IntegerField(read_only=True)
    error_message = serializers.CharField(read_only=True, allow_null=True)
    log_preview = serializers.CharField(read_only=True, allow_null=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration = serializers.FloatField(read_only=True, allow_null=True)


class ModelComparisonSerializer(serializers.Serializer):
    """模型对比序列化器"""
    model_names = serializers.ListField(
        child=serializers.CharField(),
        min_length=2,
        max_length=10,
        help_text="要对比的模型名称列表"
    )
    datasets = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="要对比的数据集"
    )


class ExportReportSerializer(serializers.Serializer):
    """导出报告序列化器"""
    task_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="要导出的任务ID列表"
    )
    format = serializers.ChoiceField(
        choices=['json', 'csv', 'markdown'],
        default='json',
        help_text="导出格式"
    )
    include_raw_results = serializers.BooleanField(
        default=False,
        help_text="是否包含原始结果"
    )


# 新增的序列化器
class BadCaseAnalysisSerializer(BaseTimestampSerializer):
    """错误案例分析序列化器"""
    accuracy = serializers.ReadOnlyField()

    class Meta:
        model = BadCaseAnalysis
        fields = '__all__'


class PromptAnalysisSerializer(BaseTimestampSerializer):
    """Prompt分析序列化器"""
    config_name = serializers.CharField(source='config.display_name', read_only=True)

    class Meta:
        model = PromptAnalysis
        fields = '__all__'
class BatchDeleteTasksSerializer(serializers.Serializer):
    """批量删除任务序列化器"""
    task_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="要删除的任务ID列表"
    )
    delete_files = serializers.BooleanField(
        default=False,
        help_text="是否同时删除相关文件（工作目录和日志）"
    )


class CleanupOldTasksSerializer(serializers.Serializer):
    """清理旧任务序列化器"""
    days = serializers.IntegerField(
        default=30,
        min_value=1,
        help_text="清理多少天前的任务"
    )
    status = serializers.ListField(
        child=serializers.ChoiceField(choices=['failed', 'cancelled', 'completed']),
        default=['failed', 'cancelled'],
        help_text="要清理的任务状态"
    )
    delete_files = serializers.BooleanField(
        default=True,
        help_text="是否删除相关文件"
    )
    dry_run = serializers.BooleanField(
        default=False,
        help_text="仅预览将要删除的任务，不执行实际删除"
    )

class ModelComparisonSerializer(BaseTimestampSerializer):
    """模型对比序列化器"""
    task_names = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ModelComparison
        fields = '__all__'

    def get_task_names(self, obj):
        return list(obj.tasks.values_list('name', flat=True))


# 通用操作序列化器
class BooleanActionSerializer(serializers.Serializer):
    """布尔操作序列化器"""
    force = serializers.BooleanField(default=False, help_text="是否强制执行")
    clean = serializers.BooleanField(default=False, help_text="是否清理临时文件")


class CompareModelsSerializer(serializers.Serializer):
    """模型对比序列化器"""
    task_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=2,
        help_text="任务ID列表（至少2个）"
    )
    name = serializers.CharField(max_length=200, required=False)
    save_result = serializers.BooleanField(default=True)