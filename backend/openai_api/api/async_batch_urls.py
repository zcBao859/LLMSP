# backend/openai_api/api/async_batch_urls.py
"""
异步批量测试相关的URL配置
"""
from django.urls import path
from .async_batch_test import AsyncBatchTestView, AsyncTaskDetailView, AsyncTaskResultsView

app_name = 'async_batch_test'

urlpatterns = [
    # 创建任务和列出所有任务
    path('tasks/', AsyncBatchTestView.as_view(), name='async-batch-tasks'),

    # 任务详情和进度
    path('tasks/<str:task_id>/', AsyncTaskDetailView.as_view(), name='async-task-detail'),

    # 任务结果
    path('tasks/<str:task_id>/results/', AsyncTaskResultsView.as_view(), name='async-task-results'),
]