# backend/openai_api/models.py
"""
Django models for OpenAI API app - 包含自动化测试相关模型
"""
from django.db import models
from django.utils import timezone
import json


# === API代理相关模型（保持原样）===
# No database models needed for API proxy functionality


# === 自动化测试相关模型 ===
class TestPlatform(models.Model):
    """测试平台"""
    PLATFORM_TYPES = (
        ('web', 'Web Platform'),
        ('api', 'API Platform'),
    )
    
    name = models.CharField(max_length=50, unique=True, verbose_name='平台名称')
    platform_type = models.CharField(max_length=10, choices=PLATFORM_TYPES, verbose_name='平台类型')
    base_url = models.URLField(blank=True, verbose_name='基础URL')
    config = models.JSONField(default=dict, verbose_name='配置信息')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '测试平台'
        verbose_name_plural = '测试平台'
        ordering = ['platform_type', 'name']
    
    def __str__(self):
        return f"{self.get_platform_type_display()} - {self.name}"


class TestSession(models.Model):
    """测试会话"""
    platform = models.ForeignKey(TestPlatform, on_delete=models.CASCADE, verbose_name='测试平台')
    session_id = models.CharField(max_length=100, unique=True, verbose_name='会话ID')
    test_type = models.CharField(max_length=20, default='standard', verbose_name='测试类型')
    prompt_file = models.CharField(max_length=200, blank=True, verbose_name='提示词文件')
    total_tests = models.IntegerField(default=0, verbose_name='总测试数')
    successful_tests = models.IntegerField(default=0, verbose_name='成功数')
    failed_tests = models.IntegerField(default=0, verbose_name='失败数')
    status = models.CharField(max_length=20, default='pending', verbose_name='状态')
    started_at = models.DateTimeField(default=timezone.now, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    
    class Meta:
        verbose_name = '测试会话'
        verbose_name_plural = '测试会话'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.platform.name} - {self.session_id}"
    
    @property
    def success_rate(self):
        """成功率"""
        if self.total_tests > 0:
            return round(self.successful_tests / self.total_tests * 100, 2)
        return 0
    
    @property
    def duration(self):
        """测试时长"""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class TestResult(models.Model):
    """单次测试结果"""
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name='results', verbose_name='测试会话')
    test_index = models.IntegerField(verbose_name='测试序号')
    prompt = models.TextField(verbose_name='提示词')
    response = models.TextField(blank=True, verbose_name='响应内容')
    success = models.BooleanField(default=False, verbose_name='是否成功')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    duration = models.FloatField(default=0, verbose_name='耗时(秒)')
    
    # 增强测试相关
    simple_question = models.CharField(max_length=500, blank=True, verbose_name='简单问题')
    simple_question_success = models.BooleanField(default=False, verbose_name='简单问题成功')
    
    # 元数据
    metadata = models.JSONField(default=dict, blank=True, verbose_name='元数据')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '测试结果'
        verbose_name_plural = '测试结果'
        ordering = ['session', 'test_index']
        unique_together = ['session', 'test_index']
    
    def __str__(self):
        return f"{self.session.session_id} - Test {self.test_index}"


class TestCheckpoint(models.Model):
    """测试检查点"""
    session = models.OneToOneField(TestSession, on_delete=models.CASCADE, verbose_name='测试会话')
    checkpoint_data = models.JSONField(verbose_name='检查点数据')
    last_test_index = models.IntegerField(default=0, verbose_name='最后测试序号')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '测试检查点'
        verbose_name_plural = '测试检查点'
    
    def __str__(self):
        return f"Checkpoint for {self.session.session_id}"


class BrowserState(models.Model):
    """浏览器状态保存"""
    platform = models.ForeignKey(TestPlatform, on_delete=models.CASCADE, verbose_name='测试平台')
    state_data = models.JSONField(verbose_name='状态数据')
    cookies = models.JSONField(default=list, verbose_name='Cookies')
    local_storage = models.JSONField(default=dict, verbose_name='LocalStorage')
    is_valid = models.BooleanField(default=True, verbose_name='是否有效')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    expires_at = models.DateTimeField(verbose_name='过期时间')
    
    class Meta:
        verbose_name = '浏览器状态'
        verbose_name_plural = '浏览器状态'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.platform.name} - {self.created_at}"
    
    @property
    def is_expired(self):
        """是否已过期"""
        return timezone.now() > self.expires_at