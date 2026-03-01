from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubjectiveTaskViewSet, TaskItemViewSet

# 使用 Router 自动生成标准 RESTful 路由
router = DefaultRouter()
router.register(r'tasks', SubjectiveTaskViewSet, basename='subjective-task')
router.register(r'items', TaskItemViewSet, basename='subjective-item')

urlpatterns = [
    # 将 router 生成的全部路由包含进来
    path('', include(router.urls)),
]