 # backend/openai_api/api/adapters/doubao_adapter.py
"""
豆包API适配器 - 将豆包API转换为OpenAI格式
"""
import aiohttp
import json
from typing import Dict, List, Any, Optional, AsyncIterator
import logging

from .base_adapter import BaseAdapter, OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIStreamChunk

logger = logging.getLogger(__name__)


class DoubaoAdapter(BaseAdapter):
    """豆包API适配器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = config.get("api_url", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        self.api_key = config.get("api_key", "")
        self.verify_ssl = config.get("verify_ssl", False)

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """将OpenAI格式的消息转换为豆包格式"""
        doubao_messages = []

        for msg in messages:
            # 豆包格式：content是一个包含text和type的数组
            doubao_message = {
                "role": msg["role"],
                "content": [
                    {
                        "text": msg["content"],
                        "type": "text"
                    }
                ]
            }
            doubao_messages.append(doubao_message)

        return doubao_messages

    async def create_completion(
            self,
            messages: List[Dict[str, str]],
            model: str,
            stream: bool = False,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            **kwargs
    ) -> OpenAIResponse:
        """创建聊天补全"""

        # 构建请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 转换消息格式为豆包格式
        doubao_messages = self._convert_messages(messages)

        # 直接使用用户指定的模型名称
        payload = {
            "model": model,  # 使用用户传入的模型名
            "messages": doubao_messages
        }

        # 添加可选参数
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # 添加其他支持的参数
        for key in ["top_p", "frequency_penalty", "presence_penalty"]:
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        logger.info(f"豆包API请求: 模型={model}")
        logger.debug(f"请求URL: {self.api_url}")
        logger.debug(f"请求体: {json.dumps(payload, ensure_ascii=False)}")

        try:
            # 创建SSL上下文
            ssl_context = None
            if not self.verify_ssl:
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession() as session:
                async with session.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                        ssl=ssl_context,
                        timeout=aiohttp.ClientTimeout(total=60)
                ) as response:

                    response_text = await response.text()

                    if response.status != 200:
                        logger.error(f"豆包API错误: {response.status}")
                        logger.error(f"错误详情: {response_text}")

                        # 解析错误信息
                        try:
                            error_data = json.loads(response_text)
                            error_msg = error_data.get('error', {}).get('message', response_text)
                        except:
                            error_msg = response_text

                        return self.create_error_response(f"API错误: {response.status} - {error_msg}", model)

                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"JSON解析失败: {response_text[:500]}")
                        return self.create_error_response("API响应格式错误", model)

                    # 提取响应
                    if "choices" in data and data["choices"]:
                        choice = data["choices"][0]
                        content = choice["message"]["content"]

                        # 处理content
                        if isinstance(content, str):
                            final_content = content
                        else:
                            final_content = str(content)

                        # 使用API返回的usage或估算
                        usage = None
                        if "usage" in data:
                            usage = OpenAIUsage(
                                prompt_tokens=data["usage"].get("prompt_tokens", 0),
                                completion_tokens=data["usage"].get("completion_tokens", 0),
                                total_tokens=data["usage"].get("total_tokens", 0)
                            )
                        else:
                            prompt_text = self.format_messages(messages)
                            usage = OpenAIUsage(
                                prompt_tokens=self.estimate_tokens(prompt_text),
                                completion_tokens=self.estimate_tokens(final_content),
                                total_tokens=self.estimate_tokens(prompt_text) + self.estimate_tokens(final_content)
                            )

                        return OpenAIResponse(
                            id=data.get("id", f"chatcmpl-doubao"),
                            model=model,
                            choices=[
                                OpenAIChoice(
                                    index=0,
                                    message=OpenAIMessage(
                                        role="assistant",
                                        content=final_content
                                    )
                                )
                            ],
                            usage=usage
                        )
                    else:
                        logger.error(f"无效的API响应格式: {data}")
                        return self.create_error_response("无效的API响应", model)

        except Exception as e:
            logger.error(f"豆包API请求失败: {str(e)}", exc_info=True)
            return self.create_error_response(str(e), model)

    async def create_completion_stream(
            self,
            messages: List[Dict[str, str]],
            model: str,
            **kwargs
    ) -> AsyncIterator[OpenAIStreamChunk]:
        """创建流式聊天补全（模拟）"""

        chunk_id = f"chatcmpl-doubao-stream"

        # 初始块
        yield OpenAIStreamChunk(
            id=chunk_id,
            model=model,
            choices=[{
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }]
        )

        try:
            # 获取完整响应
            response = await self.create_completion(
                messages=messages,
                model=model,
                stream=False,
                **kwargs
            )

            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content

                # 将内容分块发送
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    chunk_text = content[i:i + chunk_size]

                    yield OpenAIStreamChunk(
                        id=chunk_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": chunk_text},
                            "finish_reason": None
                        }]
                    )

            # 结束块
            yield OpenAIStreamChunk(
                id=chunk_id,
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            )

        except Exception as e:
            logger.error(f"流式响应生成失败: {str(e)}")
            yield OpenAIStreamChunk(
                id=chunk_id,
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {"content": f"错误: {str(e)}"},
                    "finish_reason": "error"
                }]
            )