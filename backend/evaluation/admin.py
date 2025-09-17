# evaluation/admin.py
from django.contrib import admin
from .models import (
    EvaluationDataset, EvaluationConfig,
    EvaluationTask, EvaluationResult, ModelBenchmark,
    BadCaseAnalysis, PromptAnalysis, ModelComparison  # 新增模型导入
)


@admin.register(EvaluationDataset)
class EvaluationDatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'category', 'sample_count', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['file_path', 'file_type', 'sample_count', 'created_at', 'updated_at']


@admin.register(EvaluationConfig)
class EvaluationConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'model_count', 'dataset_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'config_type', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['file_path', 'model_names', 'dataset_names', 'created_at', 'updated_at']

    def model_count(self, obj):
        return len(obj.model_names)

    model_count.short_description = '模型数量'

    def dataset_count(self, obj):
        return len(obj.dataset_names)

    dataset_count.short_description = '数据集数量'


@admin.register(EvaluationTask)
class EvaluationTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'config_name', 'status', 'progress', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'config__name']
    readonly_fields = ['work_dir', 'log_file', 'created_at', 'started_at', 'completed_at', 'duration']

    def config_name(self, obj):
        return obj.config.display_name

    config_name.short_description = '配置文件'


@admin.register(EvaluationResult)
class EvaluationResultAdmin(admin.ModelAdmin):
    list_display = ['task', 'model_name', 'dataset_name', 'metric_name', 'metric_value', 'metric_unit']
    list_filter = ['model_name', 'dataset_name', 'metric_name']
    search_fields = ['task__name', 'model_name', 'dataset_name', 'metric_name']
    readonly_fields = ['created_at']


@admin.register(ModelBenchmark)
class ModelBenchmarkAdmin(admin.ModelAdmin):
    list_display = ['model_name', 'overall_score', 'total_evaluations', 'last_evaluated']
    list_filter = ['last_evaluated']
    search_fields = ['model_name']
    readonly_fields = ['created_at', 'updated_at']


# 新增的管理类基类
class BaseTimestampAdmin(admin.ModelAdmin):
    """基础时间戳管理类"""
    readonly_fields = ['created_at', 'updated_at']
    list_filter = ['created_at']

    class Meta:
        abstract = True


# 新增的管理类
@admin.register(BadCaseAnalysis)
class BadCaseAnalysisAdmin(BaseTimestampAdmin):
    list_display = ['task', 'model_name', 'dataset_name', 'bad_cases_count', 'total_cases', 'accuracy_display',
                    'created_at']
    list_filter = ['model_name', 'dataset_name'] + BaseTimestampAdmin.list_filter
    search_fields = ['task__name', 'model_name', 'dataset_name']

    @admin.display(description='准确率')
    def accuracy_display(self, obj):
        return f"{obj.accuracy:.2f}%"


@admin.register(PromptAnalysis)
class PromptAnalysisAdmin(BaseTimestampAdmin):
    list_display = ['config', 'dataset_pattern', 'prompt_count', 'created_at']
    search_fields = ['config__name', 'dataset_pattern']


@admin.register(ModelComparison)
class ModelComparisonAdmin(BaseTimestampAdmin):
    list_display = ['name', 'task_count', 'created_by', 'created_at']
    search_fields = ['name']
    filter_horizontal = ['tasks']

    @admin.display(description='任务数量')
    def task_count(self, obj):
        return obj.tasks.count()