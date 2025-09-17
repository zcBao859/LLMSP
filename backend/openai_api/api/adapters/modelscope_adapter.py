"""
魔搭社区（ModelScope）API适配器 - 支持任意模型
"""
import json
import asyncio
from typing import Dict, List, Any, Optional, AsyncIterator
import logging
from openai import AsyncOpenAI

from .base_adapter import BaseAdapter, OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIStreamChunk

logger = logging.getLogger(__name__)


class ModelScopeAdapter(BaseAdapter):
    """魔搭社区API适配器 - 使用OpenAI SDK"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器
        config 包含API配置
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api-inference.modelscope.cn/v1/")
        self.api_key = config.get("api_key", "")
        self.verify_ssl = config.get("verify_ssl", True)
        self.timeout = config.get("timeout", 60)

        # 默认参数
        self.default_temperature = config.get("default_temperature", 0.7)
        self.default_top_p = config.get("default_top_p", 0.9)
        self.default_max_tokens = config.get("default_max_tokens", 2000)

        # 创建异步OpenAI客户端
        self.client = None
        if self.api_key:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            logger.info("初始化魔搭API客户端")
        else:
            logger.warning("魔搭API密钥未配置")

    def _extract_model_id(self, model: str) -> str:
        """从模型名称中提取实际的模型ID"""
        # 移除 "modelscope-" 前缀
        if model.startswith("modelscope-"):
            return model[11:]  # len("modelscope-") = 11
        return model

    def _is_error_response(self, response: Any) -> bool:
        """检查响应是否是错误响应"""
        # 检查是否有error字段
        if hasattr(response, 'error') and response.error:
            return True

        # 检查消息内容是否包含错误信息
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice.message, 'content'):
                content = choice.message.content
                if isinstance(content, str) and content.startswith("错误:"):
                    return True

        return False

    def _extract_content_from_message(self, message: Any) -> str:
        """从消息对象中安全地提取内容"""
        content = ""

        try:
            if hasattr(message, 'content'):
                if isinstance(message.content, str):
                    content = message.content or ""
                elif isinstance(message.content, list):
                    # 处理列表格式的content
                    for item in message.content:
                        if isinstance(item, dict):
                            if 'text' in item:
                                content += str(item['text'])
                            elif 'content' in item:
                                content += str(item['content'])
                        elif isinstance(item, str):
                            content += item
                elif isinstance(message.content, dict):
                    # 处理字典格式
                    if 'text' in message.content:
                        content = str(message.content['text'])
                    elif 'content' in message.content:
                        content = str(message.content['content'])
                    else:
                        # 如果没有特定字段，转换整个字典
                        content = json.dumps(message.content, ensure_ascii=False)

            # 如果content仍然为空，尝试其他属性
            if not content:
                if hasattr(message, 'text'):
                    content = str(message.text) if message.text else ""
                elif hasattr(message, 'answer'):
                    content = str(message.answer) if message.answer else ""
                elif hasattr(message, 'response'):
                    content = str(message.response) if message.response else ""

            # 最后的防护：确保不返回None
            if not content:
                logger.warning(f"无法提取内容，原始消息: {message}")
                content = ""  # 返回空字符串而不是默认错误信息

        except Exception as e:
            logger.error(f"提取内容时出错: {str(e)}", exc_info=True)
            content = ""

        return content

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

        if not self.client:
            logger.error("魔搭API客户端未初始化")
            return self.create_error_response("魔搭API密钥未配置", model)

        # 提取实际的模型ID
        model_id = self._extract_model_id(model)
        logger.info(f"创建聊天补全: model={model}, model_id={model_id}, stream={stream}")

        try:
            # 构建请求参数
            create_params = {
                "model": model_id,  # 使用实际的模型ID
                "messages": messages,
                "stream": False  # 先使用非流式，流式在专门的方法中处理
            }

            # 添加可选参数
            if temperature is not None:
                create_params["temperature"] = temperature
            else:
                create_params["temperature"] = self.default_temperature

            if max_tokens is not None:
                create_params["max_tokens"] = max_tokens
            else:
                create_params["max_tokens"] = self.default_max_tokens

            # 添加其他参数
            if "top_p" in kwargs:
                create_params["top_p"] = kwargs["top_p"]
            elif self.default_top_p is not None:
                create_params["top_p"] = self.default_top_p

            # 传递其他OpenAI支持的参数
            for key in ["n", "stop", "presence_penalty", "frequency_penalty", "logit_bias", "user", "seed"]:
                if key in kwargs and kwargs[key] is not None:
                    create_params[key] = kwargs[key]

            # 特殊处理：检查是否需要添加extra_body
            if kwargs.get("extra_body"):
                create_params["extra_body"] = kwargs["extra_body"]
            elif model_id.startswith("Qwen/"):
                # 对Qwen模型默认禁用thinking
                create_params["extra_body"] = {"enable_thinking": False}

            logger.info(f"魔搭API请求: 模型={model_id}")
            logger.debug(f"请求参数: {json.dumps(create_params, ensure_ascii=False)}")

            # 调用API
            response = await self.client.chat.completions.create(**create_params)

            # 先检查是否是API错误响应
            if self._is_error_response(response):
                error_msg = "API返回错误响应"
                if hasattr(response, 'error') and response.error:
                    error_msg = str(response.error)
                elif response.choices and response.choices[0].message.content:
                    error_msg = response.choices[0].message.content
                logger.error(f"API错误: {error_msg}")
                return self.create_error_response(error_msg, model)

            # 提取响应
            if response.choices:
                choice = response.choices[0]

                # 使用改进的内容提取方法
                content = self._extract_content_from_message(choice.message)

                # 记录提取的内容长度
                logger.debug(f"提取的内容长度: {len(content)} 字符")

                # 使用API返回的usage或估算
                usage = None
                if hasattr(response, 'usage') and response.usage:
                    usage = OpenAIUsage(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens
                    )
                else:
                    # 估算token使用
                    prompt_text = self.format_messages(messages)
                    usage = OpenAIUsage(
                        prompt_tokens=self.estimate_tokens(prompt_text),
                        completion_tokens=self.estimate_tokens(content),
                        total_tokens=self.estimate_tokens(prompt_text) + self.estimate_tokens(content)
                    )

                return OpenAIResponse(
                    id=getattr(response, 'id', f"chatcmpl-modelscope"),
                    model=model,  # 返回用户请求的模型名称
                    choices=[
                        OpenAIChoice(
                            index=0,
                            message=OpenAIMessage(
                                role="assistant",
                                content=content  # 确保这里的content是字符串
                            ),
                            finish_reason=getattr(choice, 'finish_reason', 'stop')
                        )
                    ],
                    usage=usage
                )
            else:
                logger.error("API响应中没有choices")
                return self.create_error_response("API响应格式错误", model)

        except Exception as e:
            logger.error(f"魔搭API请求失败: {str(e)}", exc_info=True)
            error_msg = str(e)

            # 解析常见错误
            if "errors" in error_msg and "has no provider supported" in error_msg:
                error_msg = f"模型 {model_id} 不被支持或未找到"
            elif "model not found" in error_msg.lower():
                error_msg = f"模型 {model_id} 未找到，请检查模型ID是否正确"
            elif "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                error_msg = "API密钥无效或无权限访问该模型"
            elif "rate limit" in error_msg.lower():
                error_msg = "请求频率超限，请稍后重试"

            return self.create_error_response(error_msg, model)

    async def create_completion_stream(
            self,
            messages: List[Dict[str, str]],
            model: str,
            **kwargs
    ) -> AsyncIterator[OpenAIStreamChunk]:
        """创建流式聊天补全"""

        if not self.client:
            yield OpenAIStreamChunk(
                id="error",
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {"content": "错误: 魔搭API密钥未配置"},
                    "finish_reason": "error"
                }]
            )
            return

        # 提取实际的模型ID
        model_id = self._extract_model_id(model)
        chunk_id = f"chatcmpl-modelscope-stream"

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
            # 构建请求参数
            create_params = {
                "model": model_id,
                "messages": messages,
                "stream": True,
                "temperature": kwargs.get("temperature", self.default_temperature),
                "max_tokens": kwargs.get("max_tokens", self.default_max_tokens)
            }

            if "top_p" in kwargs:
                create_params["top_p"] = kwargs["top_p"]
            elif self.default_top_p is not None:
                create_params["top_p"] = self.default_top_p

            # 传递其他参数
            for key in ["n", "stop", "presence_penalty", "frequency_penalty", "logit_bias", "user", "seed"]:
                if key in kwargs and kwargs[key] is not None:
                    create_params[key] = kwargs[key]

            # 特殊处理extra_body
            if kwargs.get("extra_body"):
                create_params["extra_body"] = kwargs["extra_body"]
            elif model_id.startswith("Qwen/"):
                create_params["extra_body"] = {"enable_thinking": False}

            try:
                # 创建流式响应
                stream = await self.client.chat.completions.create(**create_params)

                # 迭代流式响应
                async for chunk in stream:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                            if choice.delta.content:
                                yield OpenAIStreamChunk(
                                    id=chunk_id,
                                    model=model,
                                    choices=[{
                                        "index": 0,
                                        "delta": {"content": choice.delta.content},
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

            except Exception as stream_error:
                logger.warning(f"流式API失败，降级为非流式: {str(stream_error)}")

                # 降级为非流式响应模拟
                response = await self.create_completion(
                    messages=messages,
                    model=model,
                    stream=False,
                    **kwargs
                )

                if response.choices and response.choices[0].message.content:
                    content = response.choices[0].message.content

                    # 将内容分块发送
                    chunk_size = 50
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

                        # 添加小延迟以模拟流式效果
                        await asyncio.sleep(0.02)

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