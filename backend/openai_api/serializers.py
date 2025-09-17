# backend/openai_api/serializers.py
"""
Django REST Framework serializers for OpenAI API compatibility
"""
from typing import List, Optional, Union, Dict, Any
from rest_framework import serializers
from .utils import get_current_timestamp, generate_completion_id


# === Request Serializers ===
class MessageSerializer(serializers.Serializer):
    """Chat message serializer"""
    role = serializers.ChoiceField(
        choices=['system', 'user', 'assistant'],
        help_text="Role: system/user/assistant"
    )
    content = serializers.CharField(help_text="Message content")
    name = serializers.CharField(required=False, help_text="Sender name")


class ChatCompletionRequestSerializer(serializers.Serializer):
    """Chat completion request serializer"""
    model = serializers.CharField(
        default="jiutian-model",
        help_text="Model name"
    )
    messages = MessageSerializer(many=True, help_text="Message list")
    
    # Optional parameters without defaults
    temperature = serializers.FloatField(
        required=False,
        min_value=0,
        max_value=2,
        help_text="Temperature parameter"
    )
    max_tokens = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Maximum tokens to generate"
    )
    stream = serializers.BooleanField(
        default=False,
        help_text="Use streaming response"
    )
    
    # OpenAI compatibility parameters
    top_p = serializers.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        help_text="Top-p sampling"
    )
    n = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Number of completions"
    )
    stop = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Stop sequences"
    )
    presence_penalty = serializers.FloatField(
        required=False,
        min_value=-2,
        max_value=2,
        help_text="Presence penalty"
    )
    frequency_penalty = serializers.FloatField(
        required=False,
        min_value=-2,
        max_value=2,
        help_text="Frequency penalty"
    )
    logit_bias = serializers.DictField(
        required=False,
        child=serializers.FloatField(),
        help_text="Token bias"
    )
    user = serializers.CharField(
        required=False,
        help_text="User identifier"
    )
    seed = serializers.IntegerField(
        required=False,
        help_text="Random seed"
    )
    
    def validate_stop(self, value):
        """Validate stop parameter can be string or list"""
        if value is not None and not isinstance(value, (str, list)):
            raise serializers.ValidationError("Stop must be a string or list of strings")
        return value


# === Response Serializers ===
class ChatCompletionMessageSerializer(serializers.Serializer):
    """Chat completion message serializer"""
    role = serializers.CharField()
    content = serializers.CharField()


class ChatCompletionChoiceSerializer(serializers.Serializer):
    """Chat completion choice serializer"""
    index = serializers.IntegerField()
    message = ChatCompletionMessageSerializer()
    finish_reason = serializers.CharField()


class UsageSerializer(serializers.Serializer):
    """Token usage statistics serializer"""
    prompt_tokens = serializers.IntegerField()
    completion_tokens = serializers.IntegerField()
    total_tokens = serializers.IntegerField()


class ChatCompletionResponseSerializer(serializers.Serializer):
    """Chat completion response serializer"""
    id = serializers.CharField(default=generate_completion_id)
    object = serializers.CharField(default="chat.completion")
    created = serializers.IntegerField(default=get_current_timestamp)
    model = serializers.CharField()
    choices = ChatCompletionChoiceSerializer(many=True)
    usage = UsageSerializer()
    system_fingerprint = serializers.CharField(required=False, allow_null=True)


# === Streaming Response Serializers ===
class DeltaMessageSerializer(serializers.Serializer):
    """Delta message serializer"""
    role = serializers.CharField(required=False)
    content = serializers.CharField(required=False)


class ChatCompletionStreamChoiceSerializer(serializers.Serializer):
    """Streaming response choice serializer"""
    index = serializers.IntegerField()
    delta = DeltaMessageSerializer()
    finish_reason = serializers.CharField(required=False, allow_null=True)


class ChatCompletionChunkSerializer(serializers.Serializer):
    """Chat completion chunk serializer"""
    id = serializers.CharField()
    object = serializers.CharField(default="chat.completion.chunk")
    created = serializers.IntegerField()
    model = serializers.CharField()
    choices = ChatCompletionStreamChoiceSerializer(many=True)
    system_fingerprint = serializers.CharField(required=False, allow_null=True)


# === Model Related Serializers ===
class ModelSerializer(serializers.Serializer):
    """Model information serializer"""
    id = serializers.CharField()
    object = serializers.CharField(default="model")
    created = serializers.IntegerField()
    owned_by = serializers.CharField()
    permission = serializers.ListField(
        child=serializers.DictField(),
        default=list
    )
    root = serializers.CharField()
    parent = serializers.CharField(required=False, allow_null=True)


class ModelListSerializer(serializers.Serializer):
    """Model list serializer"""
    object = serializers.CharField(default="list")
    data = ModelSerializer(many=True)


# === Error Serializers ===
class ErrorDetailSerializer(serializers.Serializer):
    """Error detail serializer"""
    message = serializers.CharField()
    type = serializers.CharField()
    code = serializers.CharField(required=False)


class ErrorResponseSerializer(serializers.Serializer):
    """Error response serializer"""
    error = ErrorDetailSerializer()


# === Health Check Serializers ===
class HealthStatusSerializer(serializers.Serializer):
    """Health status serializer"""
    status = serializers.ChoiceField(
        choices=['healthy', 'unhealthy'],
        help_text="Health status"
    )
    timestamp = serializers.IntegerField(default=get_current_timestamp)
    version = serializers.CharField(help_text="Service version")
    details = serializers.DictField(required=False, help_text="Detailed information")