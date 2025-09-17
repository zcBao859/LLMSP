# backend/openai_api/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json

from .models import (
    TestPlatform, TestSession, TestResult, 
    TestCheckpoint, BrowserState
)


@admin.register(TestPlatform)
class TestPlatformAdmin(admin.ModelAdmin):
    list_display = ['name', 'platform_type', 'base_url', 'is_active', 'created_at']
    list_filter = ['platform_type', 'is_active']
    search_fields = ['name', 'base_url']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'platform_type', 'base_url', 'is_active')
        }),
        ('配置信息', {
            'fields': ('config',),
            'classes': ('wide',)
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TestSession)
class TestSessionAdmin(admin.ModelAdmin):
    list_display = [
        'session_id', 'platform', 'test_type', 'status',
        'success_rate_display', 'duration_display', 'started_at'
    ]
    list_filter = ['platform', 'test_type', 'status', 'started_at']
    search_fields = ['session_id', 'prompt_file']
    readonly_fields = [
        'session_id', 'success_rate', 'duration',
        'started_at', 'completed_at'
    ]
    date_hierarchy = 'started_at'
    
    def success_rate_display(self, obj):
        if obj.total_tests > 0:
            rate = obj.success_rate
            color = 'green' if rate >= 80 else 'orange' if rate >= 50 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, rate
            )
        return '-'
    success_rate_display.short_description = '成功率'
    
    def duration_display(self, obj):
        if obj.duration:
            minutes = int(obj.duration // 60)
            seconds = int(obj.duration % 60)
            return f"{minutes}分{seconds}秒"
        return '-'
    duration_display.short_description = '耗时'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('platform')


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = [
        'test_index', 'session_link', 'success_icon',
        'prompt_preview', 'response_preview', 'duration', 'created_at'
    ]
    list_filter = ['success', 'session__platform', 'created_at']
    search_fields = ['prompt', 'response', 'error_message']
    readonly_fields = ['created_at', 'metadata_formatted']
    raw_id_fields = ['session']
    
    def session_link(self, obj):
        url = reverse('admin:openai_api_testsession_change', args=[obj.session.id])
        return format_html('<a href="{}">{}</a>', url, obj.session.session_id[:8])
    session_link.short_description = '会话'
    
    def success_icon(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✅</span>')
        else:
            return format_html('<span style="color: red;">❌</span>')
    success_icon.short_description = '状态'
    
    def prompt_preview(self, obj):
        return obj.prompt[:50] + '...' if len(obj.prompt) > 50 else obj.prompt
    prompt_preview.short_description = '提示词'
    
    def response_preview(self, obj):
        if obj.response:
            preview = obj.response[:100] + '...' if len(obj.response) > 100 else obj.response
            return format_html(
                '<span title="{}">{}</span>',
                obj.response[:500], preview
            )
        return '-'
    response_preview.short_description = '响应'
    
    def metadata_formatted(self, obj):
        if obj.metadata:
            formatted = json.dumps(obj.metadata, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted)
        return '-'
    metadata_formatted.short_description = '元数据'
    
    fieldsets = (
        ('基本信息', {
            'fields': ('session', 'test_index', 'success')
        }),
        ('测试内容', {
            'fields': ('prompt', 'response', 'error_message'),
            'classes': ('wide',)
        }),
        ('增强测试', {
            'fields': ('simple_question', 'simple_question_success'),
            'classes': ('collapse',)
        }),
        ('性能和元数据', {
            'fields': ('duration', 'metadata_formatted', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TestCheckpoint)
class TestCheckpointAdmin(admin.ModelAdmin):
    list_display = ['session', 'last_test_index', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['session']
    
    def has_add_permission(self, request):
        return False  # 检查点应该由系统自动创建


@admin.register(BrowserState)
class BrowserStateAdmin(admin.ModelAdmin):
    list_display = ['platform', 'is_valid', 'is_expired_display', 'created_at', 'expires_at']
    list_filter = ['platform', 'is_valid', 'created_at']
    readonly_fields = ['created_at', 'cookies_count', 'local_storage_preview']
    
    def is_expired_display(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: red;">已过期</span>')
        return format_html('<span style="color: green;">有效</span>')
    is_expired_display.short_description = '状态'
    
    def cookies_count(self, obj):
        if obj.cookies:
            return f"{len(obj.cookies)} 个Cookie"
        return '0 个Cookie'
    cookies_count.short_description = 'Cookies数量'
    
    def local_storage_preview(self, obj):
        if obj.local_storage:
            preview = json.dumps(obj.local_storage, indent=2, ensure_ascii=False)[:500]
            return format_html('<pre>{}</pre>', preview)
        return '-'
    local_storage_preview.short_description = 'LocalStorage预览'
    
    fieldsets = (
        ('基本信息', {
            'fields': ('platform', 'is_valid', 'expires_at')
        }),
        ('状态数据', {
            'fields': ('cookies_count', 'local_storage_preview'),
            'classes': ('wide',)
        }),
        ('时间信息', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return False  # 浏览器状态应该由系统自动创建