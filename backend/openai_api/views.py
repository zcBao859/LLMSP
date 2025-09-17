# backend/openai_api/views.py
"""Django views for OpenAI-compatible API endpoints - 修复版"""
import logging
import json
import asyncio
import threading
from django.conf import settings
from django.http import StreamingHttpResponse, HttpResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .serializers import (
    ChatCompletionRequestSerializer,
    ChatCompletionResponseSerializer,
    HealthStatusSerializer,
)
from .api.model_router import model_router
from .exceptions import JiutianAPIException
from .utils import get_current_timestamp

logger = logging.getLogger(__name__)


class ChatCompletionsView(APIView):
    """创建聊天补全 - 使用统一的模型路由器"""
    authentication_classes = []  # 移除认证
    permission_classes = [AllowAny]  # 允许所有访问

    def post(self, request):
        """创建聊天补全"""
        try:
            # 验证请求
            serializer = ChatCompletionRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            validated_data = serializer.validated_data

            # 提取必要参数
            model = validated_data.pop('model')
            messages = validated_data.pop('messages')
            stream = validated_data.pop('stream', False)

            logger.info(f"创建聊天补全 - 模型: {model}, 流式: {stream}")

            if stream:
                # 流式响应 - 修复版
                def generate():
                    """生成流式响应 - 使用线程隔离避免事件循环冲突"""

                    def run_in_new_loop(coro):
                        """在新的事件循环中运行协程"""
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(coro)
                        finally:
                            new_loop.close()

                    def thread_runner(coro):
                        """在新线程中运行协程，完全隔离事件循环"""
                        result = [None, None]  # [result, exception]

                        def target():
                            try:
                                result[0] = run_in_new_loop(coro)
                            except Exception as e:
                                result[1] = e

                        thread = threading.Thread(target=target)
                        thread.start()
                        thread.join()

                        if result[1]:
                            raise result[1]
                        return result[0]

                    try:
                        # 在隔离的线程中创建聊天补全
                        async_gen = thread_runner(
                            model_router.create_chat_completion(
                                messages=messages,
                                model=model,
                                stream=True,
                                **validated_data
                            )
                        )

                        # 迭代异步生成器
                        while True:
                            try:
                                # 在隔离的线程中获取下一个chunk
                                chunk = thread_runner(async_gen.__anext__())

                                # 将chunk转换为字典
                                if hasattr(chunk, 'to_dict'):
                                    chunk_dict = chunk.to_dict()
                                else:
                                    chunk_dict = chunk

                                yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"

                            except StopAsyncIteration:
                                break

                    except Exception as e:
                        logger.error(f"流式响应错误: {str(e)}", exc_info=True)
                        error_data = {
                            "error": {
                                "message": str(e),
                                "type": "stream_error"
                            }
                        }
                        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                    finally:
                        yield "data: [DONE]\n\n"

                response = StreamingHttpResponse(
                    generate(),
                    content_type="text/event-stream"
                )
                response['Cache-Control'] = 'no-cache'
                response['X-Accel-Buffering'] = 'no'
                return response

            else:
                # 非流式响应 - 也使用线程隔离
                def run_async_completion():
                    """在新线程和事件循环中运行异步代码"""
                    result = [None, None]  # [result, exception]

                    def target():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            coro = model_router.create_chat_completion(
                                messages=messages,
                                model=model,
                                stream=False,
                                **validated_data
                            )
                            result[0] = loop.run_until_complete(coro)
                        except Exception as e:
                            result[1] = e
                        finally:
                            loop.close()

                    thread = threading.Thread(target=target)
                    thread.start()
                    thread.join()

                    if result[1]:
                        raise result[1]
                    return result[0]

                try:
                    openai_response = run_async_completion()

                    # 处理响应
                    if hasattr(openai_response, 'to_dict'):
                        response_data = openai_response.to_dict()
                    else:
                        response_data = openai_response

                    response_serializer = ChatCompletionResponseSerializer(data=response_data)
                    response_serializer.is_valid(raise_exception=True)

                    logger.info(f"聊天补全成功 - ID: {response_data.get('id', 'unknown')}")
                    return Response(response_serializer.validated_data)

                except Exception as e:
                    logger.error(f"非流式响应错误: {str(e)}", exc_info=True)
                    raise

        except ValueError as e:
            logger.error(f"ValueError: {str(e)}")
            raise JiutianAPIException(str(e), status_code=404, error_type="model_not_found")
        except Exception as e:
            logger.error(f"聊天补全失败: {str(e)}", exc_info=True)
            raise JiutianAPIException(f"Internal server error: {str(e)}", status_code=500)


# 其他视图类保持不变...
class ModelsListView(APIView):
    """列出可用模型 - 无需认证"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """列出所有可用模型"""
        logger.info("列出所有可用模型")
        return Response({"object": "list", "data": model_router.list_models()})


class ModelDetailView(APIView):
    """获取模型详情 - 无需认证"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, model_id):
        """获取模型信息"""
        logger.info(f"获取模型信息: {model_id}")

        if model_info := model_router.get_model_info(model_id):
            return Response(model_info)

        raise JiutianAPIException(f"Model '{model_id}' not found",
                                  status_code=404, error_type="model_not_found")


class HealthCheckView(APIView):
    """健康检查"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """健康检查"""
        health_data = {
            "status": "healthy",
            "timestamp": get_current_timestamp(),
            "version": settings.JIUTIAN_CONFIG['APP_VERSION'],
            "details": {
                "service": settings.JIUTIAN_CONFIG['APP_NAME'],
                "environment": "development" if settings.DEBUG else "production",
                "models_available": len(model_router.list_models())
            }
        }

        serializer = HealthStatusSerializer(data=health_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class ReadinessCheckView(APIView):
    """就绪检查"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ready"})


class LivenessCheckView(APIView):
    """存活检查"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "alive"})


class RootView(APIView):
    """根路径API信息"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        api_prefix = settings.JIUTIAN_CONFIG['API_PREFIX']
        return Response({
            "service": settings.JIUTIAN_CONFIG['APP_NAME'],
            "version": settings.JIUTIAN_CONFIG['APP_VERSION'],
            "timestamp": get_current_timestamp(),
            "endpoints": {
                "chat_completions": f"{api_prefix}/chat/completions",
                "models": f"{api_prefix}/models",
                "health": "/api/health",
            },
            "note": "No authentication required"
        })


def robots_txt(request):
    """Robots.txt - 防止搜索引擎索引API"""
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")