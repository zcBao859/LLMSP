from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    #path("api/chat/", include("chat.urls")),
    path("api/evaluation/", include("evaluation.urls")),
    path("api/", include("openai_api.urls")),  # 添加 openai_api 的路由
    path("api/subjective/", include("subjective.urls")),
]