from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet, ModelViewSet

# 创建路由器
router = DefaultRouter()
router.register(r'conversations', ConversationViewSet)
router.register(r'models', ModelViewSet, basename='model')

# URL配置
urlpatterns = [
    path('', include(router.urls)),
]

# API端点说明：
# GET    /api/chat/conversations/              - 获取会话列表
# POST   /api/chat/conversations/              - 创建新会话
# GET    /api/chat/conversations/{id}/         - 获取特定会话详情
# PUT    /api/chat/conversations/{id}/         - 更新会话
# DELETE /api/chat/conversations/{id}/         - 删除会话
# POST   /api/chat/conversations/chat/         - 发送聊天消息
# DELETE /api/chat/conversations/{id}/clear_messages/ - 清空会话消息

# GET    /api/chat/models/list_available/      - 获取可用模型列表
# GET    /api/chat/models/health_check/        - 健康检查
# POST   /api/chat/models/pull/                - 拉取模型