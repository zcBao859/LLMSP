# evaluation/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class EvaluationDataset(models.Model):
    """评测数据集"""
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=[
        ('safety', '安全性'),
        ('bias', '偏见'),
        ('toxicity', '毒性'),
        ('privacy', '隐私'),
        ('robustness', '鲁棒性'),
        ('ethics', '伦理'),
        ('factuality', '事实性'),
        ('custom', '自定义'),
    ], default='custom')
    description = models.TextField(blank=True)
    file_path = models.CharField(max_length=500)  # 数据集文件路径
    file_type = models.CharField(max_length=20)  # json, jsonl, csv
    sample_count = models.IntegerField(default=0)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '评测数据集'
        verbose_name_plural = '评测数据集'

    def __str__(self):
        return f"{self.display_name} ({self.category})"


class EvaluationConfig(models.Model):
    """评测配置文件"""
    name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file_path = models.CharField(max_length=500)  # 配置文件路径

    # 从配置文件解析的信息
    model_names = models.JSONField(default=list)  # 配置中的模型列表
    dataset_names = models.JSONField(default=list)  # 配置中的数据集列表
    config_type = models.CharField(max_length=50, default='opencompass')  # 配置类型

    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '评测配置'
        verbose_name_plural = '评测配置'

    def __str__(self):
        return self.display_name


class EvaluationTask(models.Model):
    """评测任务"""
    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('running', '运行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    # 基本信息
    name = models.CharField(max_length=200)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    # 使用配置文件
    config = models.ForeignKey(EvaluationConfig, on_delete=models.CASCADE)

    # 状态和时间
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # 执行信息
    work_dir = models.CharField(max_length=500, blank=True)  # OpenCompass工作目录
    log_file = models.CharField(max_length=500, blank=True)  # 日志文件路径
    progress = models.IntegerField(default=0)  # 进度百分比
    error_message = models.TextField(blank=True)

    # 资源使用
    cpu_seconds = models.FloatField(default=0)
    memory_peak_mb = models.FloatField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '评测任务'
        verbose_name_plural = '评测任务'

    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"

    @property
    def duration(self):
        """计算任务运行时长"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def start(self):
        """开始任务"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save()

    def complete(self):
        """完成任务"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.progress = 100
        self.save()

    def fail(self, error_message):
        """任务失败"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save()


class EvaluationResult(models.Model):
    """评测结果"""
    task = models.ForeignKey(EvaluationTask, on_delete=models.CASCADE, related_name='results')

    # 模型和数据集信息
    model_name = models.CharField(max_length=100)
    dataset_name = models.CharField(max_length=100)

    # 评测指标
    metric_name = models.CharField(max_length=100)
    metric_value = models.FloatField()
    metric_unit = models.CharField(max_length=20, blank=True)  # 如 "%", "score" 等

    # 详细数据
    details = models.JSONField(default=dict)  # 存储详细的评测数据
    raw_results = models.JSONField(default=dict)  # 原始结果数据

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['task', 'model_name', 'dataset_name', 'metric_name']
        verbose_name = '评测结果'
        verbose_name_plural = '评测结果'

    def __str__(self):
        return f"{self.model_name} - {self.dataset_name} - {self.metric_name}: {self.metric_value}"


class ModelBenchmark(models.Model):
    """模型基准测试汇总"""
    model_name = models.CharField(max_length=100, unique=True)

    # 综合评分
    overall_score = models.FloatField(default=0)

    # 各类别评分
    category_scores = models.JSONField(default=dict)  # {"safety": 85.5, "bias": 90.2, ...}

    # 详细指标
    metrics = models.JSONField(default=dict)

    # 统计信息
    total_evaluations = models.IntegerField(default=0)
    datasets_evaluated = models.JSONField(default=list)  # 已评测的数据集列表
    last_evaluated = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-overall_score']
        verbose_name = '模型基准'
        verbose_name_plural = '模型基准'

    def __str__(self):
        return f"{self.model_name} (Score: {self.overall_score:.2f})"

    def update_from_results(self, results):
        """从评测结果更新基准分数"""
        # 更新各项指标
        for result in results:
            if result.metric_name in ['accuracy', 'pass_rate', 'score']:
                if result.dataset_name not in self.metrics:
                    self.metrics[result.dataset_name] = {}
                self.metrics[result.dataset_name][result.metric_name] = result.metric_value

        # 更新统计信息
        self.total_evaluations += 1
        self.last_evaluated = timezone.now()

        # 计算综合评分
        all_scores = []
        for dataset_metrics in self.metrics.values():
            for metric_value in dataset_metrics.values():
                all_scores.append(metric_value)

        if all_scores:
            self.overall_score = sum(all_scores) / len(all_scores)

        self.save()


# 新增的基础模型类
class BaseTimestampModel(models.Model):
    """基础时间戳模型"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


# 新增的模型
class BadCaseAnalysis(BaseTimestampModel):
    """错误案例分析结果"""
    task = models.ForeignKey(EvaluationTask, on_delete=models.CASCADE, related_name='bad_cases')
    model_name = models.CharField(max_length=100)
    dataset_name = models.CharField(max_length=100)
    total_cases = models.IntegerField(default=0)
    bad_cases_count = models.IntegerField(default=0)
    cases = models.JSONField(default=list)
    bad_cases_file = models.CharField(max_length=500, blank=True)
    all_cases_file = models.CharField(max_length=500, blank=True)

    class Meta(BaseTimestampModel.Meta):
        verbose_name = '错误案例分析'
        verbose_name_plural = '错误案例分析'
        unique_together = ['task', 'model_name', 'dataset_name']

    def __str__(self):
        return f"{self.task.name} - {self.model_name} - {self.dataset_name}"

    @property
    def accuracy(self):
        return ((self.total_cases - self.bad_cases_count) / self.total_cases * 100) if self.total_cases > 0 else 0


class PromptAnalysis(BaseTimestampModel):
    """Prompt分析记录"""
    config = models.ForeignKey(EvaluationConfig, on_delete=models.CASCADE, related_name='prompt_analyses')
    dataset_pattern = models.CharField(max_length=200, blank=True)
    prompt_count = models.IntegerField(default=1)
    prompts = models.JSONField(default=list)
    tokens_info = models.JSONField(default=dict)

    class Meta(BaseTimestampModel.Meta):
        verbose_name = 'Prompt分析'
        verbose_name_plural = 'Prompt分析'

    def __str__(self):
        return f"{self.config.display_name} - {self.dataset_pattern or 'all'}"


class ModelComparison(BaseTimestampModel):
    """模型对比结果"""
    name = models.CharField(max_length=200)
    tasks = models.ManyToManyField(EvaluationTask, related_name='comparisons')
    comparison_data = models.JSONField(default=dict)
    summary = models.TextField(blank=True)
    charts_data = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta(BaseTimestampModel.Meta):
        verbose_name = '模型对比'
        verbose_name_plural = '模型对比'

    def __str__(self):
        return f"{self.name} ({self.tasks.count()} models)"