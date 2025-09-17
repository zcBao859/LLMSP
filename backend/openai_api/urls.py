# backend/openai_api/urls.py
"""URL configuration for OpenAI API app"""
from django.urls import path, include
from . import views
from .api import data_api
from .api import batch_urls  # 导入批量测试URLs
from .api import async_batch_urls  # 导入异步批量测试URLs
from .api import cookie_manager

app_name = 'openai_api'

# Cookie管理API
cookie_patterns = [
    path('', cookie_manager.CookieUploadView.as_view(), name='cookie-upload'),  # 改为空路径
    path('export/', cookie_manager.CookieExportView.as_view(), name='cookie-export'),
    path('<str:platform>/', cookie_manager.CookieDeleteView.as_view(), name='cookie-delete'),
]

# API v1 URLs (OpenAI兼容)
api_v1_patterns = [
    # Chat completions
    path('chat/completions', views.ChatCompletionsView.as_view(), name='chat-completions'),

    # Models
    path('models', views.ModelsListView.as_view(), name='models-list'),
    path('models/<str:model_id>', views.ModelDetailView.as_view(), name='model-detail'),

    # 批量测试API - 移到这里，使URL为 /api/v1/batch/
    path('batch/', include(batch_urls)),

    # 异步批量测试API - /api/v1/async-batch/
    path('async-batch/', include(async_batch_urls)),
]

# Health check URLs
health_patterns = [
    path('health', views.HealthCheckView.as_view(), name='health-check'),
    path('health/ready', views.ReadinessCheckView.as_view(), name='readiness-check'),
    path('health/live', views.LivenessCheckView.as_view(), name='liveness-check'),
]

# Test Data API URLs
test_api_patterns = [
    # 测试会话
    path('sessions/', data_api.TestSessionListAPI.as_view(), name='test-sessions'),
    path('sessions/<str:session_id>/', data_api.TestSessionDetailAPI.as_view(), name='test-session-detail'),
    path('sessions/<str:session_id>/results/', data_api.TestResultsAPI.as_view(), name='test-session-results'),

    # 测试结果
    path('results/', data_api.TestResultsAPI.as_view(), name='test-results'),

    # 测试平台
    path('platforms/', data_api.TestPlatformsAPI.as_view(), name='test-platforms'),

    # 统计信息
    path('statistics/', data_api.TestStatisticsAPI.as_view(), name='test-statistics'),
]

urlpatterns = [
    # OpenAI兼容API
    path('v1/', include(api_v1_patterns)),

    # 健康检查
    path('', include(health_patterns)),

    # 测试数据API - 去掉 api/ 前缀
    path('test/', include(test_api_patterns)),

    # Cookie管理API - 去掉 api/ 前缀
    path('cookies/', include(cookie_patterns)),
]