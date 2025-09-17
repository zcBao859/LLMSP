# backend/openai_api/api/adapters/huanxin_adapter.py
"""
环信API适配器 - 支持多个DeepSeek模型，每个模型独立配置
"""
import aiohttp
import json
import asyncio
from typing import Dict, List, Any, Optional, AsyncIterator
import logging

from .base_adapter import BaseAdapter, OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIStreamChunk
from ...utils import generate_completion_id, get_current_timestamp

logger = logging.getLogger(__name__)


class HuanxinAdapter(BaseAdapter):
    """环信API适配器 - 原JIUTIAN适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器
        config 包含所有模型的配置信息
        """
        super().__init__(config)
        self.models_config = config.get("models", {})
        self.verify_ssl = config.get("verify_ssl", False)
        self.timeout = config.get("timeout", 60)

    def get_model_config(self, model: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的配置"""
        return self.models_config.get(model)

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """将OpenAI格式的消息转换为环信格式"""
        parts = []
        role_map = {"system": "系统", "user": "用户", "assistant": "助手"}

        # 检查是否有系统消息
        has_system = any(msg["role"] == "system" for msg in messages)

        # 如果没有系统消息，添加默认的
        if not has_system:
            parts.append("系统: 你是一个有帮助的助手")

        # 转换消息
        for msg in messages:
            role = role_map.get(msg["role"], msg["role"])
            content = msg["content"].strip()
            if content:
                parts.append(f"{role}: {content}")

        formatted_prompt = "\n".join(parts)

        logger.info("========== 格式化的提示词 ==========")
        logger.info(formatted_prompt)
        logger.info("===================================")

        return formatted_prompt

    def _extract_text(self, response: Dict) -> str:
        """从环信响应中提取文本"""
        # 主要提取逻辑
        if "text" in response and isinstance(response["text"], list):
            text = response["text"][0] if response["text"] else ""

            # 处理特殊标签
            if "</think>" in text:
                text = text.split("</think>", 1)[1].strip()

            # 提取实际回复（移除角色标记）
            lines = text.split('\n')
            cleaned_lines = []

            for line in lines:
                # 跳过角色标记行
                if line.startswith(("系统:", "用户:", "助手:")):
                    continue
                cleaned_lines.append(line)

            result = '\n'.join(cleaned_lines).strip()
            if result:
                return result

            # 如果清理后的结果为空，返回原始文本
            return text.strip()

        # 备选提取策略
        for field in ["response", "result", "output", "content", "completion"]:
            if field in response:
                value = response[field]
                if isinstance(value, str):
                    return value
                elif isinstance(value, list) and value:
                    return str(value[0])

        # 如果无法提取，返回JSON字符串
        logger.warning("无法从响应中提取文本，返回JSON")
        return json.dumps(response, ensure_ascii=False, indent=2)

    async def _call_api(self, api_url: str, api_key: str, prompt: str, **params) -> Dict[str, Any]:
        """调用环信API"""
        # 构建请求数据
        data = {
            "prompt": prompt
        }

        # 只添加明确提供的参数
        for key, value in params.items():
            if value is not None:
                data[key] = value

        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
            "User-Agent": "Huanxin-Adapter/1.0"
        }

        logger.info(f"========== 环信API请求 ==========")
        logger.info(f"URL: {api_url}")
        logger.info(f"Headers: {dict(headers)}")
        logger.info("请求体:")
        logger.info(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("=================================")

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
                        api_url,
                        headers=headers,
                        json=data,
                        ssl=ssl_context,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_text = await response.text()

                    if response.status != 200:
                        logger.error(f"环信API错误: {response.status}")
                        logger.error(f"错误详情: {response_text}")

                        try:
                            error_data = json.loads(response_text)
                            error_msg = error_data.get('error', {}).get('message', response_text)
                        except json.JSONDecodeError:
                            error_msg = response_text

                        raise Exception(f"API错误: {response.status} - {error_msg}")

                    result = json.loads(response_text)

                    logger.info("========== 环信API原始响应 ==========")
                    logger.info(json.dumps(result, ensure_ascii=False, indent=2))
                    logger.info("====================================")

                    return result

        except aiohttp.ClientTimeout:
            logger.error("环信API请求超时")
            raise Exception("环信API请求超时")
        except Exception as e:
            logger.error(f"环信API请求失败: {str(e)}")
            raise

    async def create_completion(
            self,
            messages: List[Dict[str, str]],
            model: str,
            stream: bool = False,
            **kwargs
    ) -> OpenAIResponse:
        """创建聊天补全"""
        logger.info(f"创建聊天补全: model={model}, stream={stream}")

        # 获取模型配置
        model_config = self.get_model_config(model)
        if not model_config:
            logger.error(f"未找到模型配置: {model}")
            return self.create_error_response(f"未找到模型配置: {model}", model)

        api_url = model_config.get("api_url")
        api_key = model_config.get("api_key")

        if not api_url or not api_key:
            logger.error(f"模型 {model} 的URL或API密钥未配置")
            return self.create_error_response(f"模型 {model} 配置不完整", model)

        # 格式化消息
        prompt = self._format_messages(messages)

        try:
            # 调用API
            api_response = await self._call_api(api_url, api_key, prompt, **kwargs)

            # 提取内容
            content = self._extract_text(api_response)

            # 计算token使用量
            prompt_tokens = self.estimate_tokens(prompt)
            completion_tokens = self.estimate_tokens(content)

            return OpenAIResponse(
                id=generate_completion_id(),
                model=model,
                created=get_current_timestamp(),
                choices=[
                    OpenAIChoice(
                        index=0,
                        message=OpenAIMessage(
                            role="assistant",
                            content=content
                        ),
                        finish_reason="stop"
                    )
                ],
                usage=OpenAIUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            )

        except Exception as e:
            logger.error(f"创建聊天补全失败: {str(e)}", exc_info=True)
            return self.create_error_response(str(e), model)

    async def create_completion_stream(
            self,
            messages: List[Dict[str, str]],
            model: str,
            **kwargs
    ) -> AsyncIterator[OpenAIStreamChunk]:
        """创建流式聊天补全"""
        completion_id = generate_completion_id()
        created = get_current_timestamp()

        # 初始块
        yield OpenAIStreamChunk(
            id=completion_id,
            model=model,
            created=created,
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
                        id=completion_id,
                        model=model,
                        created=created,
                        choices=[{
                            "index": 0,
                            "delta": {"content": chunk_text},
                            "finish_reason": None
                        }]
                    )

                    # 添加小延迟以模拟流式效果
                    await asyncio.sleep(0.05)

            # 结束块
            yield OpenAIStreamChunk(
                id=completion_id,
                model=model,
                created=created,
                choices=[{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            )

        except Exception as e:
            logger.error(f"流式响应错误: {str(e)}")
            yield OpenAIStreamChunk(
                id=completion_id,
                model=model,
                created=created,
                choices=[{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "error"
                }],
                error=str(e)
            )

    # 保留向后兼容的同步方法
    def create(self, messages: List[Dict[str, str]], model: str = "huanxin-model",
               stream: bool = False, **kwargs):
        """同步版本的create方法（向后兼容）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if stream:
                async def collect_stream():
                    return [chunk async for chunk in
                            self.create_completion_stream(messages, model, **kwargs)]

                chunks = loop.run_until_complete(collect_stream())
                return (chunk.to_dict() for chunk in chunks)
            else:
                response = loop.run_until_complete(
                    self.create_completion(messages, model, stream, **kwargs))

                # 转换为原有格式的对象
                class ChatCompletion:
                    def __init__(self, r):
                        self.id = r.id
                        self.object = r.object
                        self.created = r.created
                        self.model = r.model
                        self.choices = r.choices
                        self.usage = r.usage

                return ChatCompletion(response)
        finally:
            loop.close()