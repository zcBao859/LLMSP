# evaluation/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EvaluationDatasetViewSet,
    EvaluationConfigViewSet,
    EvaluationTaskViewSet,
    ModelBenchmarkViewSet,
    OpenCompassToolsViewSet  # 新增
)

router = DefaultRouter()
router.register(r'opencompass_datasets', EvaluationDatasetViewSet)
router.register(r'configs', EvaluationConfigViewSet)
router.register(r'tasks', EvaluationTaskViewSet)
router.register(r'benchmarks', ModelBenchmarkViewSet)
router.register(r'tools', OpenCompassToolsViewSet, basename='tools')  # 新增

urlpatterns = [
    path('', include(router.urls)),
]