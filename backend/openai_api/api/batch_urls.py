# backend/openai_api/api/batch_urls.py
"""
批量测试相关的URL配置
"""
from django.urls import path
from .batch_scheduler import BatchTestView, BatchTestResultView

app_name = 'batch_test'

urlpatterns = [
    # 批量测试任务管理
    path('tasks/', BatchTestView.as_view(), name='batch-tasks'),
    path('tasks/<str:task_id>/results/', BatchTestResultView.as_view(), name='batch-results'),
]