# backend/openai_api/api/adapters/ollama_adapter.py
"""
Ollama API适配器 - 支持本地 Ollama 模型
"""
import aiohttp
import json
import asyncio
from typing import Dict, List, Any, Optional, AsyncIterator
import logging
import re
import time
from contextlib import asynccontextmanager

from .base_adapter import BaseAdapter, OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIStreamChunk

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseAdapter):
    """Ollama API适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器
        config 包含：
        - base_url: Ollama API地址，例如 http://localhost:11434
        - models: 支持的模型配置
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.chat_endpoint = f"{self.base_url}/api/chat"
        self.models_config = config.get("models", {})
        self.timeout = config.get("timeout", 120)
        self.max_tokens = config.get("max_tokens", 100000)
        self._is_available = None  # 缓存服务可用性状态
        self._last_check_time = 0  # 上次检查时间
        self._check_interval = 60  # 检查间隔（秒）

        logger.info(f"初始化 Ollama 适配器，API地址: {self.base_url}")

    async def check_availability(self) -> bool:
        """检查 Ollama 服务是否可用"""
        current_time = time.time()

        # 如果距离上次检查不到60秒，使用缓存结果
        if self._is_available is not None and (current_time - self._last_check_time) < self._check_interval:
            return self._is_available

        # 为可用性检查创建独立的会话
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.base_url}/api/tags",
                        timeout=aiohttp.ClientTimeout(total=2)  # 短超时
                ) as response:
                    self._is_available = response.status == 200
                    self._last_check_time = current_time
                    if self._is_available:
                        logger.debug("Ollama 服务可用")
                    return self._is_available
        except Exception as e:
            logger.debug(f"Ollama 服务不可用: {type(e).__name__}")
            self._is_available = False
            self._last_check_time = current_time
            return False

    def get_model_config(self, model: str) -> Dict[str, Any]:
        """获取特定模型的配置"""
        # 从模型名称中提取实际的 Ollama 模型名
        if model.startswith("ollama-"):
            actual_model = model[7:]  # 移除 "ollama-" 前缀
        else:
            actual_model = model

        # 返回模型配置，如果没有特定配置则返回默认配置
        return self.models_config.get(actual_model, {
            "model_name": actual_model,
            "max_tokens": self.max_tokens
        })

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """将OpenAI格式的消息转换为Ollama格式"""
        # Ollama 使用相同的消息格式
        return messages

    def _parse_response_content(self, response_text: str) -> tuple[Optional[str], Optional[str]]:
        """
        解析响应内容，分离思考过程和答案

        Returns:
            (think_content, answer_content)
        """
        if not response_text:
            return None, response_text

        # 使用正则表达式提取 <think> 标签内容
        think_pattern = r'<think>(.*?)</think>'
        think_match = re.search(think_pattern, response_text, re.DOTALL)

        think_content = None
        answer_content = response_text

        if think_match:
            think_content = think_match.group(1).strip()
            # 移除 think 部分，获取纯答案内容
            answer_content = re.sub(think_pattern, '', response_text, flags=re.DOTALL).strip()

            logger.debug(f"提取到思考内容，长度: {len(think_content)} 字符")
            logger.debug(f"提取到答案内容，长度: {len(answer_content)} 字符")

        return think_content, answer_content

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

        # 先检查服务是否可用
        if not await self.check_availability():
            return self.create_error_response("Ollama 服务不可用，请确保 Ollama 正在运行", model)

        # 获取实际的模型名称
        model_config = self.get_model_config(model)
        actual_model_name = model_config.get("model_name", model)

        if actual_model_name.startswith("ollama-"):
            actual_model_name = actual_model_name[7:]

        logger.info(f"创建聊天补全: model={model}, actual_model={actual_model_name}, stream={stream}")

        # 构建请求
        payload = {
            "model": actual_model_name,
            "messages": self._convert_messages(messages),
            "stream": False,  # 始终使用非流式，流式在专门的方法中处理
            "options": {}
        }

        # 添加可选参数
        if temperature is not None:
            payload["options"]["temperature"] = temperature

        # Ollama 使用 num_predict 而不是 max_tokens
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        else:
            payload["options"]["num_predict"] = model_config.get("max_tokens", self.max_tokens)

        # 添加其他 Ollama 支持的参数
        for key in ["top_k", "top_p", "repeat_penalty", "seed"]:
            if key in kwargs and kwargs[key] is not None:
                payload["options"][key] = kwargs[key]

        logger.debug(f"Ollama API 请求: {json.dumps(payload, ensure_ascii=False)}")

        # 为每个请求创建独立的会话
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                        self.chat_endpoint,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:

                    response_text = await response.text()

                    if response.status != 200:
                        logger.error(f"Ollama API 错误: {response.status}")
                        logger.error(f"错误详情: {response_text}")

                        try:
                            error_data = json.loads(response_text)
                            error_msg = error_data.get('error', response_text)
                        except:
                            error_msg = response_text

                        return self.create_error_response(f"API错误: {response.status} - {error_msg}", model)

                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"JSON解析失败: {response_text[:500]}")
                        return self.create_error_response("API响应格式错误", model)

                    # 提取响应
                    if "message" in data and "content" in data["message"]:
                        content = data["message"]["content"]

                        # 解析思考内容和答案
                        think_content, answer_content = self._parse_response_content(content)

                        # 使用答案内容作为最终响应
                        final_content = answer_content if answer_content else content

                        # 估算token使用
                        prompt_text = self.format_messages(messages)
                        usage = OpenAIUsage(
                            prompt_tokens=self.estimate_tokens(prompt_text),
                            completion_tokens=self.estimate_tokens(final_content),
                            total_tokens=self.estimate_tokens(prompt_text) + self.estimate_tokens(final_content)
                        )

                        # 如果需要，可以在响应中包含思考内容的信息
                        if think_content and logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"思考内容长度: {len(think_content)} 字符")
                            logger.debug(f"答案内容长度: {len(answer_content)} 字符")

                        return OpenAIResponse(
                            id=f"chatcmpl-ollama-{actual_model_name}",
                            model=model,
                            choices=[
                                OpenAIChoice(
                                    index=0,
                                    message=OpenAIMessage(
                                        role="assistant",
                                        content=final_content
                                    ),
                                    finish_reason="stop"
                                )
                            ],
                            usage=usage
                        )
                    else:
                        logger.error(f"无效的API响应格式: {data}")
                        return self.create_error_response("无效的API响应", model)

            except aiohttp.ClientTimeout:
                logger.error("Ollama API 请求超时")
                return self.create_error_response("请求超时", model)
            except aiohttp.ClientConnectorError:
                logger.error("无法连接到 Ollama 服务")
                # 标记服务不可用
                self._is_available = False
                self._last_check_time = time.time()
                return self.create_error_response("无法连接到 Ollama 服务", model)
            except Exception as e:
                logger.error(f"Ollama API 请求失败: {str(e)}", exc_info=True)
                return self.create_error_response(str(e), model)

    async def _stream_helper(self, messages: List[Dict[str, str]], model: str, **kwargs):
        """流式响应的辅助方法 - 在单独的协程中处理流"""
        # 先检查服务是否可用
        if not await self.check_availability():
            return [{
                "type": "error",
                "content": "Ollama 服务不可用"
            }]

        # 获取实际的模型名称
        model_config = self.get_model_config(model)
        actual_model_name = model_config.get("model_name", model)

        if actual_model_name.startswith("ollama-"):
            actual_model_name = actual_model_name[7:]

        # 构建请求
        payload = {
            "model": actual_model_name,
            "messages": self._convert_messages(messages),
            "stream": True,
            "options": {}
        }

        # 添加参数
        if kwargs.get("temperature") is not None:
            payload["options"]["temperature"] = kwargs["temperature"]

        if kwargs.get("max_tokens") is not None:
            payload["options"]["num_predict"] = kwargs["max_tokens"]
        else:
            payload["options"]["num_predict"] = model_config.get("max_tokens", self.max_tokens)

        chunks = []
        full_response = ""

        try:
            # 使用单独的会话处理流
            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.chat_endpoint, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        chunks.append({
                            "type": "error",
                            "content": f"API错误: {response.status} - {error_text}"
                        })
                        return chunks

                    # 读取流式响应
                    async for line in response.content:
                        if not line:
                            continue

                        try:
                            line_text = line.decode('utf-8').strip()
                            if not line_text:
                                continue

                            chunk_data = json.loads(line_text)

                            # Ollama 的流式响应格式
                            if "message" in chunk_data and "content" in chunk_data["message"]:
                                chunk_content = chunk_data["message"]["content"]
                                full_response += chunk_content
                                chunks.append({
                                    "type": "content",
                                    "content": chunk_content
                                })

                            # 检查是否完成
                            if chunk_data.get("done", False):
                                break

                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.debug(f"处理流式响应行时出错: {str(e)}")
                            continue

        except Exception as e:
            logger.error(f"流式请求失败: {str(e)}")
            chunks.append({
                "type": "error",
                "content": str(e)
            })

        # 如果响应包含思考标签，记录
        if "<think>" in full_response and "</think>" in full_response:
            think_content, answer_content = self._parse_response_content(full_response)
            logger.debug("流式响应包含思考内容")

        return chunks

    async def create_completion_stream(
            self,
            messages: List[Dict[str, str]],
            model: str,
            **kwargs
    ) -> AsyncIterator[OpenAIStreamChunk]:
        """创建流式聊天补全"""

        chunk_id = f"chatcmpl-ollama-stream"

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
            # 在当前事件循环中创建任务来处理流
            loop = asyncio.get_event_loop()

            # 使用 create_task 而不是直接 await
            task = loop.create_task(self._stream_helper(messages, model, **kwargs))

            # 等待任务完成
            chunks = await task

            # 处理收集到的块
            for chunk in chunks:
                if chunk["type"] == "error":
                    yield OpenAIStreamChunk(
                        id=chunk_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": f"错误: {chunk['content']}"},
                            "finish_reason": "error"
                        }]
                    )
                    return
                elif chunk["type"] == "content":
                    yield OpenAIStreamChunk(
                        id=chunk_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": chunk["content"]},
                            "finish_reason": None
                        }]
                    )
                    # 添加小延迟以避免过快发送
                    await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"流式生成失败: {str(e)}")
            yield OpenAIStreamChunk(
                id=chunk_id,
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {"content": f"错误: {str(e)}"},
                    "finish_reason": "error"
                }]
            )
            return

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

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用的模型"""
        # 先检查服务是否可用
        if not await self.check_availability():
            logger.debug("Ollama 服务不可用，跳过模型列表")
            return []

        try:
            # 为列出模型创建独立的会话
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.base_url}/api/tags",
                        timeout=aiohttp.ClientTimeout(total=3)  # 缩短超时时间
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        models = []

                        for model_info in data.get("models", []):
                            model_name = model_info.get("name", "")
                            if model_name:
                                models.append({
                                    "id": f"ollama-{model_name}",
                                    "object": "model",
                                    "owned_by": "ollama",
                                    "created": 1700000000,
                                    "description": f"Ollama {model_name} (本地模型)"
                                })

                        logger.info(f"成功获取 {len(models)} 个 Ollama 模型")
                        return models
                    else:
                        logger.debug(f"获取 Ollama 模型列表失败: HTTP {response.status}")
                        return []

        except asyncio.TimeoutError:
            logger.debug("获取 Ollama 模型列表超时")
            return []
        except aiohttp.ClientConnectorError as e:
            logger.debug(f"无法连接到 Ollama 服务: {str(e)}")
            return []
        except Exception as e:
            logger.debug(f"列出 Ollama 模型时出错: {type(e).__name__}: {str(e)}")
            return []