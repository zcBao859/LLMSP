from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    """消息序列化器"""

    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'created_at', 'model_name']
        read_only_fields = ['created_at']


class SystemConfigSerializer(serializers.Serializer):
    """系统配置序列化器"""
    # Ollama配置
    ollama_base_url = serializers.CharField(required=False, help_text="Ollama服务地址")
    ollama_default_model = serializers.CharField(required=False, help_text="Ollama默认模型")

    # DeepSeek配置
    deepseek_api_key = serializers.CharField(required=False, help_text="DeepSeek API密钥")
    deepseek_base_url = serializers.CharField(required=False, help_text="DeepSeek API地址")
    deepseek_default_model = serializers.CharField(required=False, help_text="DeepSeek默认模型")

    # 默认提供商
    default_provider = serializers.ChoiceField(
        choices=['ollama', 'deepseek'],
        required=False,
        help_text="默认AI服务提供商"
    )

    def validate_ollama_base_url(self, value):
        """验证URL格式"""
        if value and not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError("URL必须以http://或https://开头")
        return value.rstrip('/')  # 移除末尾的斜杠

    def validate_deepseek_base_url(self, value):
        """验证URL格式"""
        if value and not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError("URL必须以http://或https://开头")
        return value.rstrip('/')  # 移除末尾的斜杠


class ConversationSerializer(serializers.ModelSerializer):
    """会话序列化器"""
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at', 'messages', 'message_count', 'last_message']
        read_only_fields = ['created_at', 'updated_at']

    def get_message_count(self, obj):
        return obj.messages.count()

    def get_last_message(self, obj):
        last_msg = obj.messages.last()
        if last_msg:
            return {
                'content': last_msg.content[:100],
                'role': last_msg.role,
                'created_at': last_msg.created_at
            }
        return None


class ConversationListSerializer(serializers.ModelSerializer):
    """会话列表序列化器（不包含所有消息）"""
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at', 'message_count', 'last_message']
        read_only_fields = ['created_at', 'updated_at']

    def get_message_count(self, obj):
        return obj.messages.count()

    def get_last_message(self, obj):
        last_msg = obj.messages.last()
        if last_msg:
            return {
                'content': last_msg.content[:100],
                'role': last_msg.role,
                'created_at': last_msg.created_at
            }
        return None


class ChatRequestSerializer(serializers.Serializer):
    """聊天请求序列化器"""
    message = serializers.CharField(required=True, help_text="用户消息内容")
    conversation_id = serializers.IntegerField(required=False, allow_null=True, help_text="会话ID，不提供则创建新会话")
    model = serializers.CharField(required=False, allow_blank=True, help_text="使用的模型名称")
    stream = serializers.BooleanField(default=False, help_text="是否使用流式响应")
    provider = serializers.ChoiceField(
        choices=['ollama', 'deepseek'],
        default='ollama',
        help_text="AI服务提供商"
    )

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("消息内容不能为空")
        return value.strip()