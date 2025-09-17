# backend/openai_api/api/adapters/base_adapter.py
"""统一的适配器基类 - 所有AI模型适配器的基础"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncIterator
from dataclasses import dataclass, field
import time
import uuid
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class OpenAIMessage:
    """OpenAI消息格式"""
    role: str
    content: str
    name: Optional[str] = None


@dataclass
class OpenAIChoice:
    """OpenAI响应选项"""
    index: int
    message: OpenAIMessage
    finish_reason: str = "stop"


@dataclass
class OpenAIUsage:
    """Token使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class OpenAIResponse:
    """OpenAI响应格式"""
    id: str = field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:8]}")
    object: str = "chat.completion"
    created: int = field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[OpenAIChoice] = field(default_factory=list)
    usage: Optional[OpenAIUsage] = None
    system_fingerprint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": [{
                "index": c.index,
                "message": {"role": c.message.role, "content": c.message.content},
                "finish_reason": c.finish_reason
            } for c in self.choices],
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens
            } if self.usage else None
        }


@dataclass
class OpenAIStreamChunk:
    """流式响应块"""
    id: str
    object: str = "chat.completion.chunk"
    created: int = field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "object": self.object, "created": self.created,
                "model": self.model, "choices": self.choices}


class BaseAdapter(ABC):
    """所有模型适配器的基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model_name = config.get("model_name", "unknown")

    @abstractmethod
    async def create_completion(self, messages: List[Dict[str, str]], model: str,
                                stream: bool = False, **kwargs) -> OpenAIResponse:
        """创建聊天补全"""
        pass

    async def create_completion_stream(self, messages: List[Dict[str, str]],
                                       model: str, **kwargs) -> AsyncIterator[OpenAIStreamChunk]:
        """创建流式聊天补全 - 默认实现：将非流式响应模拟为流式"""
        try:
            response = await self.create_completion(messages, model, False, **kwargs)
            chunk_id = f"chatcmpl-{self.model_name}-stream"

            # 检查事件循环状态
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    logger.warning("事件循环已关闭，无法生成流式响应")
                    return
            except RuntimeError:
                logger.warning("无法获取事件循环")
                return

            # 初始块
            yield OpenAIStreamChunk(id=chunk_id, model=model,
                                    choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}])

            # 内容块
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    yield OpenAIStreamChunk(id=chunk_id, model=model,
                                            choices=[{"index": 0, "delta": {"content": content[i:i + chunk_size]},
                                                      "finish_reason": None}])
                    try:
                        await asyncio.sleep(0.05)
                    except asyncio.CancelledError:
                        logger.debug("流式响应被取消")
                        break

            # 结束块
            yield OpenAIStreamChunk(id=chunk_id, model=model,
                                    choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])

        except asyncio.CancelledError:
            logger.debug("流式响应生成被取消")
        except Exception as e:
            logger.error(f"流式响应生成失败: {str(e)}")
            # 生成错误块
            try:
                yield OpenAIStreamChunk(
                    id=f"chatcmpl-{self.model_name}-error",
                    model=model,
                    choices=[{"index": 0, "delta": {"content": f"错误: {str(e)}"}, "finish_reason": "error"}]
                )
            except:
                pass  # 如果无法发送错误块，静默失败

    def estimate_tokens(self, text: str) -> int:
        """估算token数量"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        return max(1, int(chinese_chars / 2 + (len(text) - chinese_chars) / 4))

    def format_messages(self, messages: List[Dict[str, str]]) -> str:
        """将OpenAI格式的消息转换为文本"""
        role_map = {"system": "系统", "user": "用户", "assistant": "助手"}
        parts = []

        # 添加默认系统消息
        if not any(msg["role"] == "system" for msg in messages):
            parts.append("系统: 你是一个有帮助的助手")

        # 转换消息
        for msg in messages:
            role = role_map.get(msg["role"], msg["role"])
            if content := msg.get("content", "").strip():
                parts.append(f"{role}: {content}")

        return "\n".join(parts)

    def create_error_response(self, error_message: str, model: str) -> OpenAIResponse:
        """创建错误响应"""
        return OpenAIResponse(
            model=model,
            choices=[OpenAIChoice(0, OpenAIMessage("assistant", f"错误: {error_message}"), "error")],
            usage=OpenAIUsage(0, 0, 0)
        )

    async def close(self):
        """关闭适配器，清理资源 - 子类可以重写此方法"""
        pass