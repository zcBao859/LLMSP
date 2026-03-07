from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.http import StreamingHttpResponse
import json
import logging
from .serializers import SystemConfigSerializer
from .models import Conversation, Message, SystemConfig
from .serializers import (
    ConversationSerializer,
    ConversationListSerializer,
    MessageSerializer,
    ChatRequestSerializer
)
from .ollama_service import OllamaService
from .deepseek_service import DeepSeekService

logger = logging.getLogger(__name__)


class ConversationViewSet(viewsets.ModelViewSet):
    """会话视图集"""
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [AllowAny]  # 暂时允许所有访问，生产环境应该加上认证

    def get_serializer_class(self):
        if self.action == 'list':
            return ConversationListSerializer
        return ConversationSerializer

    def get_queryset(self):
        # 如果有用户认证，过滤用户的会话
        if self.request.user.is_authenticated:
            return self.queryset.filter(user=self.request.user)
        # 暂时返回所有会话，生产环境应该限制
        return self.queryset.all()

    def _get_ai_service(self, provider: str):
        """根据提供商获取AI服务实例"""
        if provider == 'deepseek':
            return DeepSeekService()
        else:
            return OllamaService()

    @action(detail=False, methods=['post'])
    def chat(self, request):
        """处理聊天请求"""
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        message_content = data['message']
        conversation_id = data.get('conversation_id')
        model = data.get('model')
        stream = data.get('stream', False)
        provider = data.get('provider', 'ollama')

        # 获取或创建会话
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id)
            except Conversation.DoesNotExist:
                return Response(
                    {'error': '会话不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # 创建新会话，使用第一条消息的前30个字符作为标题
            conversation = Conversation.objects.create(
                user=request.user if request.user.is_authenticated else None,
                title=message_content[:30] + "..." if len(message_content) > 30 else message_content
            )

        # 保存用户消息
        user_message = Message.objects.create(
            conversation=conversation,
            role='user',
            content=message_content
        )

        # 准备消息历史（包含系统提示词）
        messages = []

        # 添加系统提示词（可选）
        # messages.append({
        #     "role": "system",
        #     "content": "你是一个有帮助的AI助手。"
        # })

        # 添加历史消息
        for msg in conversation.messages.all():
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # 获取对应的AI服务
        ai_service = self._get_ai_service(provider)

        try:
            if stream:
                return self._stream_response(conversation, messages, model, ai_service, provider)
            else:
                # 非流式响应
                response = ai_service.chat(messages, model=model)
                assistant_content = response.get('message', {}).get('content', '')

                # 保存助手回复
                assistant_message = Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=assistant_content,
                    model_name=model or ai_service.default_model
                )

                # 更新会话的更新时间
                conversation.save()

                return Response({
                    'conversation_id': conversation.id,
                    'message': MessageSerializer(assistant_message).data,
                    'user_message': MessageSerializer(user_message).data,
                    'provider': provider
                })

        except Exception as e:
            logger.error(f"Chat error: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _stream_response(self, conversation, messages, model, ai_service, provider):
        """处理流式响应"""

        def generate():
            full_content = ""
            try:
                # 发送开始标记
                yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation.id, 'provider': provider})}\n\n"

                # 流式获取响应
                for chunk in ai_service.chat(messages, model=model, stream=True):
                    if 'message' in chunk:
                        content = chunk['message'].get('content', '')
                        full_content += content

                        # 发送内容块
                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

                    # 检查是否完成
                    if chunk.get('done', False):
                        # 保存完整的助手回复
                        assistant_message = Message.objects.create(
                            conversation=conversation,
                            role='assistant',
                            content=full_content,
                            model_name=model or ai_service.default_model
                        )

                        # 更新会话
                        conversation.save()

                        # 发送完成标记
                        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_message.id})}\n\n"

            except Exception as e:
                logger.error(f"Stream error: {str(e)}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        response = StreamingHttpResponse(
            generate(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # 禁用nginx缓冲
        return response

    @action(detail=True, methods=['delete'])
    def clear_messages(self, request, pk=None):
        """清空会话的所有消息"""
        conversation = self.get_object()
        conversation.messages.all().delete()
        return Response({'status': 'messages cleared'})


class ModelViewSet(viewsets.ViewSet):
    """模型管理视图集"""
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def config(self, request):
        """获取系统配置"""
        ollama_service = OllamaService()
        deepseek_service = DeepSeekService()

        return Response({
            'ollama': {
                'base_url': ollama_service.base_url,
                'default_model': ollama_service.default_model
            },
            'deepseek': {
                'api_key': deepseek_service.api_key[:8] + '...' if deepseek_service.api_key else None,
                'base_url': deepseek_service.base_url,
                'default_model': deepseek_service.default_model
            },
            'default_provider': SystemConfig.get_config('default_provider', 'ollama')
        })

    @action(detail=False, methods=['post'])
    def update_config(self, request):
        """更新系统配置"""
        serializer = SystemConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # 更新Ollama配置
        if any(key.startswith('ollama_') for key in data):
            ollama_service = OllamaService()
            ollama_service.update_config(
                base_url=data.get('ollama_base_url'),
                default_model=data.get('ollama_default_model')
            )

            # 测试Ollama配置
            if data.get('ollama_base_url'):
                test_service = OllamaService()
                if not test_service.check_health():
                    return Response(
                        {'error': f'无法连接到Ollama服务: {test_service.base_url}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # 更新DeepSeek配置
        if any(key.startswith('deepseek_') for key in data):
            deepseek_service = DeepSeekService()
            deepseek_service.update_config(
                api_key=data.get('deepseek_api_key'),
                base_url=data.get('deepseek_base_url'),
                default_model=data.get('deepseek_default_model')
            )

            # 测试DeepSeek配置
            if data.get('deepseek_api_key'):
                test_service = DeepSeekService()
                if not test_service.check_health():
                    return Response(
                        {'error': 'DeepSeek API配置无效，请检查API密钥'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # 更新默认提供商
        if 'default_provider' in data:
            SystemConfig.set_config('default_provider', data['default_provider'], '默认AI服务提供商')

        return Response({
            'status': 'success',
            'message': '配置更新成功'
        })

    @action(detail=False, methods=['get'])
    def list_available(self, request):
        """获取可用模型列表"""
        provider = request.query_params.get('provider', 'ollama')

        if provider == 'deepseek':
            service = DeepSeekService()
        else:
            service = OllamaService()

        try:
            models = service.list_models()
            return Response({
                'provider': provider,
                'models': models,
                'default_model': service.default_model
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def health_check(self, request):
        """健康检查"""
        provider = request.query_params.get('provider')

        results = {}

        # 检查指定的提供商或所有提供商
        if not provider or provider == 'ollama':
            ollama_service = OllamaService()
            results['ollama'] = {
                'status': 'healthy' if ollama_service.check_health() else 'unhealthy',
                'base_url': ollama_service.base_url,
                'default_model': ollama_service.default_model
            }

        if not provider or provider == 'deepseek':
            deepseek_service = DeepSeekService()
            results['deepseek'] = {
                'status': 'healthy' if deepseek_service.check_health() else 'unhealthy',
                'base_url': deepseek_service.base_url,
                'default_model': deepseek_service.default_model,
                'api_key_configured': bool(deepseek_service.api_key)
            }

        return Response(results)

    @action(detail=False, methods=['post'])
    def pull(self, request):
        """拉取（下载）模型 - 仅Ollama支持"""
        model_name = request.data.get('model_name')
        if not model_name:
            return Response(
                {'error': '请提供模型名称'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ollama_service = OllamaService()

        def generate():
            try:
                for progress in ollama_service.pull_model(model_name):
                    yield f"data: {json.dumps(progress)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        response = StreamingHttpResponse(
            generate(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        return response