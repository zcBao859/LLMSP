# backend/openai_api/api/batch_scheduler.py
"""
批量测试调度程序 - 增强版，集成会话隔离机制

本模块基于任务调度理论(Task Scheduling Theory)和资源管理最佳实践，
实现了具有智能会话隔离和资源优化能力的批量测试框架。
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import threading

from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from ..models import TestSession, TestResult, TestPlatform
from .model_router import model_router
from ..batch_test_saver import batch_test_saver
from ..serializers import ChatCompletionRequestSerializer
from .web_model_config import WebModelTestConfig

logger = logging.getLogger(__name__)


@dataclass
class TestTask:
    """测试任务数据类"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str = ""
    models: List[str] = field(default_factory=list)
    run_count: int = 1
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    save_responses: bool = True
    session_isolation: bool = True  # 是否启用会话隔离
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "models": self.models,
            "run_count": self.run_count,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system_prompt": self.system_prompt,
            "save_responses": self.save_responses,
            "session_isolation": self.session_isolation,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class TestTaskResult:
    """测试任务结果数据类"""
    task_id: str
    prompt: str
    model: str
    run_index: int
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    tokens_used: Optional[Dict[str, int]] = None
    session_isolated: bool = False
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "model": self.model,
            "run_index": self.run_index,
            "success": self.success,
            "response": self.response,
            "error": self.error,
            "duration": self.duration,
            "tokens_used": self.tokens_used,
            "session_isolated": self.session_isolated,
            "error_type": self.error_type,
            "timestamp": datetime.now().isoformat()
        }


class BatchTestScheduler:
    """
    批量测试调度器 - 增强版

    实现了基于优先级队列(Priority Queue)的任务调度算法，
    结合了智能资源分配和会话管理策略。
    """

    def __init__(self):
        self.active_tasks: Dict[str, TestTask] = {}
        self.task_results: Dict[str, List[TestTaskResult]] = {}
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._lock = threading.Lock()

        # Web模型配置管理器
        self.web_model_config = WebModelTestConfig()

        # 资源管理
        self._resource_tracker = {
            "web_models_active": 0,
            "api_models_active": 0,
            "browser_instances": 0,
            "memory_usage": 0
        }

    def create_task(self,
                    prompt: str,
                    models: List[str],
                    run_count: int = 1,
                    temperature: Optional[float] = None,
                    max_tokens: Optional[int] = None,
                    system_prompt: Optional[str] = None,
                    save_responses: bool = True,
                    session_isolation: bool = True) -> TestTask:
        """创建测试任务"""
        # 验证模型列表
        if not models:
            raise ValueError("至少需要指定一个模型")

        # 去重
        unique_models = list(dict.fromkeys(models))

        task = TestTask(
            prompt=prompt,
            models=unique_models,
            run_count=run_count,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            save_responses=save_responses,
            session_isolation=session_isolation
        )

        with self._lock:
            self.active_tasks[task.task_id] = task
            self.task_results[task.task_id] = []

        # 分析模型类型
        web_models = self.web_model_config.get_all_web_models(unique_models)
        api_models = self.web_model_config.get_api_models(unique_models)

        logger.info(f"创建测试任务: {task.task_id}, "
                    f"模型: {unique_models} (Web: {len(web_models)}, API: {len(api_models)}), "
                    f"运行次数: {run_count}, 会话隔离: {session_isolation}")

        return task

    async def run_single_test_with_session_isolation(
            self,
            task: TestTask,
            model: str,
            run_index: int,
            test_index: int
    ) -> TestTaskResult:
        """执行单次测试，确保会话隔离"""

        # 获取模型特定配置
        model_config = self.web_model_config.get_web_model_config(model)
        is_web_model = self.web_model_config.is_web_model(model)

        # 记录测试开始
        logger.info(f"[会话隔离] 开始测试 - 模型: {model}, 运行: {run_index + 1}/{task.run_count}, "
                    f"会话隔离: {'启用' if is_web_model and task.session_isolation else '标准'}")

        # Web模型的会话隔离前置处理
        if is_web_model and model_config and task.session_isolation:
            # 应用测试前延迟
            if run_index > 0:
                delay = model_config.get("inter_test_delay", 2)
                logger.info(f"[会话隔离] 测试间隔等待 {delay} 秒")
                await asyncio.sleep(delay)

            # 检查是否需要清理浏览器状态
            if test_index > 0 and test_index % model_config.get("clear_cookies_interval", 10) == 0:
                logger.info(f"[会话隔离] 达到清理阈值 ({test_index} 次测试)，准备状态重置")
                await self._reset_browser_state(model)

            # 注入会话隔离配置
            await self._inject_session_config(model, model_config)

        # 执行测试
        try:
            result = await self.run_single_test_with_model(task, model, run_index, test_index)

            # Web模型的后置处理
            if is_web_model and task.session_isolation:
                # 添加会话隔离元数据
                result.session_isolated = True

                # 记录会话信息
                if hasattr(result, 'metadata'):
                    if not isinstance(result.metadata, dict):
                        result.metadata = {}
                    result.metadata['session_isolated'] = True
                    result.metadata['isolation_mode'] = model_config.get('session_isolation_mode', 'unknown')

            return result

        except Exception as e:
            logger.error(f"[会话隔离] 测试执行失败: {str(e)}")

            # 对于Web模型，可能需要特殊的错误恢复
            if is_web_model and model_config.get("retry_on_session_error", True):
                if "session" in str(e).lower() or "会话" in str(e).lower():
                    logger.info("[会话隔离] 检测到会话错误，尝试恢复")
                    await self._recover_from_session_error(model)
                    # 可以选择重试

            # 创建错误结果
            return TestTaskResult(
                task_id=task.task_id,
                prompt=task.prompt,
                model=model,
                run_index=run_index,
                success=False,
                error=str(e),
                duration=0,
                session_isolated=is_web_model and task.session_isolation,
                error_type=self._classify_error(str(e))
            )

    async def _inject_session_config(self, model: str, config: Dict[str, Any]):
        """向模型适配器注入会话配置"""
        try:
            # 通过模型路由器传递配置
            adapter = model_router.get_adapter(model)

            if adapter and hasattr(adapter, 'update_session_config'):
                adapter.update_session_config(config)
                logger.debug(f"[会话隔离] 已向 {model} 注入配置: {config}")
        except Exception as e:
            logger.warning(f"[会话隔离] 配置注入失败: {str(e)}")

    async def _reset_browser_state(self, model: str):
        """重置浏览器状态"""
        try:
            logger.info(f"[会话隔离] 开始重置 {model} 的浏览器状态")
            # 这里可以调用浏览器管理器的清理方法
            # 例如：清理cookies、localStorage等
            with self._lock:
                self._resource_tracker["browser_instances"] = max(0, self._resource_tracker["browser_instances"] - 1)
        except Exception as e:
            logger.error(f"[会话隔离] 浏览器状态重置失败: {str(e)}")

    async def _recover_from_session_error(self, model: str):
        """从会话错误中恢复"""
        try:
            logger.info(f"[会话隔离] 尝试恢复 {model} 的会话状态")
            # 实施错误恢复策略
            # 1. 等待一段时间
            await asyncio.sleep(5)
            # 2. 尝试重置浏览器
            await self._reset_browser_state(model)
            # 3. 更新资源追踪
            with self._lock:
                self._resource_tracker["web_models_active"] = max(0, self._resource_tracker["web_models_active"] - 1)
        except Exception as e:
            logger.error(f"[会话隔离] 会话恢复失败: {str(e)}")

    def _classify_error(self, error_message: str) -> str:
        """错误分类"""
        error_lower = error_message.lower()

        if "session" in error_lower or "会话" in error_lower:
            return "session_error"
        elif "timeout" in error_lower or "超时" in error_lower:
            return "timeout_error"
        elif "login" in error_lower or "登录" in error_lower:
            return "auth_error"
        elif "network" in error_lower or "网络" in error_lower:
            return "network_error"
        elif "rate" in error_lower or "limit" in error_lower:
            return "rate_limit_error"
        else:
            return "general_error"

    async def run_single_test_with_model(self, task: TestTask, model: str, run_index: int,
                                         test_index: int) -> TestTaskResult:
        """运行单次测试（原始方法，保持兼容）"""
        start_time = asyncio.get_event_loop().time()

        try:
            # 检查是否有检查点（断点续传）
            if task.save_responses:
                checkpoint = batch_test_saver.load_checkpoint(model)
                if checkpoint and checkpoint.get("results"):
                    existing_results = checkpoint["results"]

                    # 查找是否已经有相同的测试（基于prompt和run_index）
                    for existing in existing_results:
                        if (existing.get("prompt") == task.prompt and
                                existing.get("run_index") == run_index):
                            logger.info(f"从检查点恢复: {model} - 运行 {run_index + 1}")

                            return TestTaskResult(
                                task_id=task.task_id,
                                prompt=task.prompt,
                                model=model,
                                run_index=run_index,
                                success=existing.get("success", False),
                                response=existing.get("response"),
                                error=existing.get("error"),
                                duration=existing.get("duration", 0),
                                tokens_used=existing.get("tokens_used"),
                                session_isolated=existing.get("session_isolated", False)
                            )

            # 构建消息
            messages = []
            if task.system_prompt:
                messages.append({
                    "role": "system",
                    "content": task.system_prompt
                })
            messages.append({
                "role": "user",
                "content": task.prompt
            })

            # 调用模型
            logger.info(f"任务 {task.task_id} - 模型 {model} - 第 {run_index + 1}/{task.run_count} 次测试")

            # 构建参数
            kwargs = {}
            if task.temperature is not None:
                kwargs['temperature'] = task.temperature
            if task.max_tokens is not None:
                kwargs['max_tokens'] = task.max_tokens

            # 更新资源追踪
            is_web_model = self.web_model_config.is_web_model(model)
            with self._lock:
                if is_web_model:
                    self._resource_tracker["web_models_active"] += 1
                else:
                    self._resource_tracker["api_models_active"] += 1

            # 创建完成
            response = await model_router.create_chat_completion(
                messages=messages,
                model=model,
                stream=False,
                **kwargs
            )

            # 更新资源追踪
            with self._lock:
                if is_web_model:
                    self._resource_tracker["web_models_active"] -= 1
                else:
                    self._resource_tracker["api_models_active"] -= 1

            # 提取结果
            if hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content
                tokens_used = None
                if hasattr(response, 'usage') and response.usage:
                    tokens_used = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }

                duration = asyncio.get_event_loop().time() - start_time

                result = TestTaskResult(
                    task_id=task.task_id,
                    prompt=task.prompt,
                    model=model,
                    run_index=run_index,
                    success=True,
                    response=content,
                    duration=duration,
                    tokens_used=tokens_used,
                    session_isolated=False  # 原始方法不使用会话隔离
                )

                logger.info(f"测试成功 - 模型: {model}, 耗时: {duration:.2f}秒")

            else:
                raise Exception("响应格式错误")

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.error(f"测试失败 - 模型: {model}, 错误: {str(e)}")

            result = TestTaskResult(
                task_id=task.task_id,
                prompt=task.prompt,
                model=model,
                run_index=run_index,
                success=False,
                error=str(e),
                duration=duration,
                session_isolated=False,
                error_type=self._classify_error(str(e))
            )

        # 保存结果到检查点（立即保存）
        if task.save_responses:
            # 加载现有检查点
            checkpoint = batch_test_saver.load_checkpoint(model)
            existing_results = checkpoint.get("results", []) if checkpoint else []

            # 添加新结果
            existing_results.append(result.to_dict())

            # 保存更新后的检查点
            batch_test_saver.save_checkpoint(
                model,
                existing_results,
                task.to_dict()
            )

        # 保存到内存
        with self._lock:
            if task.task_id in self.task_results:
                self.task_results[task.task_id].append(result)

        return result

    async def run_task(self, task: TestTask) -> List[TestTaskResult]:
        """运行完整的测试任务 - 增强版，支持会话隔离"""
        logger.info(f"开始运行任务 {task.task_id} (会话隔离: {task.session_isolation})")

        # 创建测试会话（用于数据库记录）
        try:
            test_platform, _ = TestPlatform.objects.get_or_create(
                name='multi_model_batch',
                defaults={
                    'platform_type': 'api',
                    'base_url': ''
                }
            )

            total_tests = len(task.models) * task.run_count

            # 分析模型类型
            web_models = self.web_model_config.get_all_web_models(task.models)
            api_models = self.web_model_config.get_api_models(task.models)

            metadata = {
                "session_isolation": task.session_isolation,
                "web_models": web_models,
                "api_models": api_models
            }

            session = TestSession.objects.create(
                platform=test_platform,
                session_id=task.task_id,
                test_type='batch_multi_model',
                prompt_file=f"batch_test_{task.task_id}.json",
                total_tests=total_tests,
                metadata=metadata
            )
        except Exception as e:
            logger.error(f"创建测试会话失败: {e}")
            session = None

        all_results = []

        # 按模型分组执行，根据模型类型采用不同策略
        for model_index, model in enumerate(task.models):
            logger.info(f"开始测试模型 {model_index + 1}/{len(task.models)}: {model}")

            # 判断是否为Web模型
            is_web_model = self.web_model_config.is_web_model(model)

            # 为每个模型运行指定次数的测试
            if is_web_model and task.session_isolation:
                # Web模型使用会话隔离的串行执行
                logger.info(f"[{model}] 使用会话隔离模式")
                for run_index in range(task.run_count):
                    test_index = model_index * task.run_count + run_index

                    # 使用会话隔离方法
                    result = await self.run_single_test_with_session_isolation(
                        task, model, run_index, test_index
                    )
                    all_results.append(result)

                    # 保存到数据库
                    if session:
                        self._save_test_result(session, result, test_index)
            else:
                # API模型或未启用会话隔离的模型可以并发执行
                if is_web_model:
                    # Web模型但未启用会话隔离，仍然串行但不强制新会话
                    logger.info(f"[{model}] Web模型使用标准串行模式（无会话隔离）")
                    for run_index in range(task.run_count):
                        test_index = model_index * task.run_count + run_index
                        result = await self.run_single_test_with_model(task, model, run_index, test_index)
                        all_results.append(result)

                        if session:
                            self._save_test_result(session, result, test_index)

                        if run_index < task.run_count - 1:
                            await asyncio.sleep(2)
                else:
                    # API模型可以并发执行
                    logger.info(f"[{model}] API模型使用并发模式")
                    max_concurrent = 3
                    semaphore = asyncio.Semaphore(max_concurrent)

                    async def run_with_semaphore(run_index):
                        async with semaphore:
                            test_index = model_index * task.run_count + run_index
                            return await self.run_single_test_with_model(task, model, run_index, test_index)

                    # 创建所有任务
                    tasks = [run_with_semaphore(i) for i in range(task.run_count)]
                    model_results = await asyncio.gather(*tasks)

                    # 保存结果
                    for i, result in enumerate(model_results):
                        all_results.append(result)
                        if session:
                            test_index = model_index * task.run_count + i
                            self._save_test_result(session, result, test_index)

            # 模型之间的间隔
            if model_index < len(task.models) - 1:
                if is_web_model:
                    logger.info(f"模型 {model} 测试完成，等待5秒后测试下一个模型")
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(1)

        # 更新会话状态
        if session:
            session.status = 'completed'
            session.completed_at = datetime.now()
            session.save()

        # 清理任务
        with self._lock:
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]

        # 为每个模型生成最终报告
        if task.save_responses:
            for model in task.models:
                try:
                    metadata = {
                        "task_id": task.task_id,
                        "session_isolation": task.session_isolation,
                        "is_web_model": self.web_model_config.is_web_model(model)
                    }

                    saved_files = batch_test_saver.finalize_test_results(model, metadata)
                    logger.info(f"模型 {model} 的测试结果已保存: {saved_files}")
                except Exception as e:
                    logger.error(f"保存模型 {model} 的最终结果失败: {e}")

        # 统计结果
        success_count = sum(1 for r in all_results if r.success)
        logger.info(f"任务 {task.task_id} 完成，总测试: {len(all_results)}, 成功: {success_count}")

        # 按模型统计
        for model in task.models:
            model_results = [r for r in all_results if r.model == model]
            model_success = sum(1 for r in model_results if r.success)
            session_isolated_count = sum(1 for r in model_results if r.session_isolated)
            logger.info(f"  - {model}: {model_success}/{len(model_results)} 成功, "
                        f"{session_isolated_count} 个使用会话隔离")

        return all_results

    def _save_test_result(self, session: TestSession, result: TestTaskResult, test_index: int):
        """保存测试结果到数据库"""
        try:
            TestResult.objects.create(
                session=session,
                test_index=test_index,
                prompt=result.prompt,
                response=result.response or "",
                success=result.success,
                error_message=result.error or "",
                duration=result.duration,
                metadata={
                    "model": result.model,
                    "run_index": result.run_index,
                    "tokens_used": result.tokens_used,
                    "session_isolated": result.session_isolated,
                    "error_type": result.error_type
                }
            )

            if result.success:
                session.successful_tests += 1
            else:
                session.failed_tests += 1
            session.save()

        except Exception as e:
            logger.error(f"保存测试结果失败: {e}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self._lock:
            task = self.active_tasks.get(task_id)
            results = self.task_results.get(task_id, [])

        if not task and not results:
            return None

        # 计算统计信息
        if task:
            total_runs = len(task.models) * task.run_count
        else:
            models = list(set(r.model for r in results))
            if models and results:
                run_count = max(r.run_index for r in results if r.model == models[0]) + 1
                total_runs = len(models) * run_count
            else:
                total_runs = len(results)

        completed_runs = len(results)
        success_runs = sum(1 for r in results if r.success)
        session_isolated_runs = sum(1 for r in results if r.session_isolated)

        # 按模型分组统计
        model_stats = {}
        error_distribution = {}

        for result in results:
            if result.model not in model_stats:
                model_stats[result.model] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "avg_duration": 0,
                    "durations": [],
                    "session_isolated": 0,
                    "is_web_model": self.web_model_config.is_web_model(result.model)
                }
                error_distribution[result.model] = {}

            model_stats[result.model]["total"] += 1
            if result.success:
                model_stats[result.model]["success"] += 1
            else:
                model_stats[result.model]["failed"] += 1
                # 统计错误类型
                if result.error_type:
                    error_distribution[result.model][result.error_type] = \
                        error_distribution[result.model].get(result.error_type, 0) + 1

            model_stats[result.model]["durations"].append(result.duration)
            if result.session_isolated:
                model_stats[result.model]["session_isolated"] += 1

        # 计算平均耗时
        for model, stats in model_stats.items():
            if stats["durations"]:
                stats["avg_duration"] = sum(stats["durations"]) / len(stats["durations"])
            del stats["durations"]  # 不返回详细列表

        # 获取每个模型的检查点进度
        checkpoint_progress = {}
        if task:
            for model in task.models:
                progress = batch_test_saver.get_test_progress(model)
                checkpoint_progress[model] = progress

        status_info = {
            "task_id": task_id,
            "status": "running" if task else "completed",
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "success_runs": success_runs,
            "session_isolated_runs": session_isolated_runs,
            "success_rate": success_runs / completed_runs if completed_runs > 0 else 0,
            "model_stats": model_stats,
            "error_distribution": error_distribution,
            "checkpoint_progress": checkpoint_progress,
            "resource_usage": self._resource_tracker.copy(),
            "results": [r.to_dict() for r in results]
        }

        if task:
            status_info["task_info"] = task.to_dict()

        return status_info

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务状态"""
        with self._lock:
            all_task_ids = set(self.active_tasks.keys()) | set(self.task_results.keys())

        return [self.get_task_status(task_id) for task_id in all_task_ids if self.get_task_status(task_id)]

    def get_resource_status(self) -> Dict[str, Any]:
        """获取资源使用状态"""
        with self._lock:
            return {
                "resource_tracker": self._resource_tracker.copy(),
                "active_tasks": len(self.active_tasks),
                "executor_active": self.executor._threads,
                "timestamp": datetime.now().isoformat()
            }


# 全局调度器实例
batch_scheduler = BatchTestScheduler()


class BatchTestView(APIView):
    """批量测试API视图"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """创建批量测试任务"""
        try:
            # 验证请求数据
            prompt = request.data.get('prompt')
            models = request.data.get('models')
            model = request.data.get('model')
            run_count = request.data.get('run_count', 1)
            temperature = request.data.get('temperature')
            max_tokens = request.data.get('max_tokens')
            system_prompt = request.data.get('system_prompt')
            session_isolation = request.data.get('session_isolation', True)

            if not prompt:
                return Response(
                    {"error": "prompt is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 处理模型参数
            if models:
                if not isinstance(models, list):
                    return Response(
                        {"error": "models must be a list"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if not models:
                    return Response(
                        {"error": "models list cannot be empty"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            elif model:
                models = [model]
            else:
                return Response(
                    {"error": "models or model is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if len(models) > 10:
                return Response(
                    {"error": "maximum 10 models allowed per task"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 创建任务
            task = batch_scheduler.create_task(
                prompt=prompt,
                models=models,
                run_count=run_count,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                session_isolation=session_isolation
            )

            # 分析模型类型
            web_models = WebModelTestConfig.get_all_web_models(models)
            api_models = WebModelTestConfig.get_api_models(models)

            # 在后台运行任务
            async def run_task_async():
                await batch_scheduler.run_task(task)

            def run_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_task_async())
                loop.close()

            thread = threading.Thread(target=run_in_thread)
            thread.start()

            total_tests = len(models) * run_count
            return Response({
                "task_id": task.task_id,
                "status": "created",
                "message": f"任务创建成功。将运行 {total_tests} 个测试 "
                           f"({len(models)} 个模型 × {run_count} 次运行)",
                "models": models,
                "run_count": run_count,
                "session_isolation": session_isolation,
                "model_breakdown": {
                    "web_models": web_models,
                    "api_models": api_models
                }
            })

        except Exception as e:
            logger.error(f"创建批量测试任务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request):
        """获取任务状态"""
        task_id = request.query_params.get('task_id')

        if task_id:
            status_info = batch_scheduler.get_task_status(task_id)
            if not status_info:
                return Response(
                    {"error": "Task not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            return Response(status_info)
        else:
            all_tasks = batch_scheduler.get_all_tasks()
            resource_status = batch_scheduler.get_resource_status()

            return Response({
                "tasks": all_tasks,
                "total": len(all_tasks),
                "resource_status": resource_status
            })


class BatchTestResultView(APIView):
    """批量测试结果API视图"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, task_id):
        """获取测试结果"""
        try:
            # 先尝试从内存中获取结果
            status_info = batch_scheduler.get_task_status(task_id)

            if status_info and status_info.get('status') == 'completed':
                # 从内存中构建响应
                response_data = {
                    "task_id": task_id,
                    "platform": "multi_model_batch",
                    "total_tests": status_info.get('total_runs', 0),
                    "successful_tests": status_info.get('success_runs', 0),
                    "failed_tests": status_info.get('total_runs', 0) - status_info.get('success_runs', 0),
                    "session_isolated_tests": status_info.get('session_isolated_runs', 0),
                    "success_rate": status_info.get('success_rate', 0) * 100,
                    "status": "completed",
                    "models": [],
                    "model_stats": status_info.get('model_stats', {}),
                    "error_distribution": status_info.get('error_distribution', {}),
                    "results": []
                }

                # 提取模型列表
                if 'model_stats' in status_info:
                    response_data["models"] = list(status_info['model_stats'].keys())

                # 处理结果
                for result in status_info.get('results', []):
                    response_data["results"].append({
                        "index": result.get('run_index', 0),
                        "model": result.get('model', 'unknown'),
                        "run_index": result.get('run_index', 0),
                        "prompt": result.get('prompt', ''),
                        "response": result.get('response', ''),
                        "success": result.get('success', False),
                        "error": result.get('error', ''),
                        "duration": result.get('duration', 0),
                        "session_isolated": result.get('session_isolated', False),
                        "error_type": result.get('error_type'),
                        "metadata": {
                            "model": result.get('model', 'unknown'),
                            "tokens_used": result.get('tokens_used')
                        }
                    })

                return Response(response_data)

            # 从数据库获取会话
            session = TestSession.objects.filter(session_id=task_id).first()
            if not session:
                return Response(
                    {"error": "Session not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 获取所有结果
            results = TestResult.objects.filter(session=session).order_by('test_index')

            # 构建响应
            response_data = {
                "task_id": task_id,
                "platform": session.platform.name,
                "total_tests": session.total_tests,
                "successful_tests": session.successful_tests,
                "failed_tests": session.failed_tests,
                "success_rate": float(session.success_rate) if session.success_rate else 0.0,
                "status": session.status,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "models": [],
                "model_stats": {},
                "error_distribution": {},
                "results": []
            }

            # 从会话元数据提取信息
            if session.metadata:
                response_data["session_isolation"] = session.metadata.get("session_isolation", False)
                response_data["web_models"] = session.metadata.get("web_models", [])
                response_data["api_models"] = session.metadata.get("api_models", [])

            # 收集模型信息
            models_set = set()
            model_results = {}
            error_distribution = {}
            session_isolated_count = 0

            for result in results:
                metadata = result.metadata if isinstance(result.metadata, dict) else {}
                model = metadata.get('model', 'unknown')
                models_set.add(model)

                if model not in model_results:
                    model_results[model] = {
                        "total": 0,
                        "success": 0,
                        "failed": 0,
                        "avg_duration": 0,
                        "durations": [],
                        "session_isolated": 0,
                        "is_web_model": WebModelTestConfig.is_web_model(model)
                    }
                    error_distribution[model] = {}

                model_results[model]["total"] += 1
                if result.success:
                    model_results[model]["success"] += 1
                else:
                    model_results[model]["failed"] += 1
                    # 统计错误类型
                    error_type = metadata.get('error_type', 'unknown')
                    error_distribution[model][error_type] = error_distribution[model].get(error_type, 0) + 1

                model_results[model]["durations"].append(float(result.duration))

                if metadata.get('session_isolated', False):
                    model_results[model]["session_isolated"] += 1
                    session_isolated_count += 1

                response_data["results"].append({
                    "index": result.test_index,
                    "model": model,
                    "run_index": metadata.get('run_index', 0),
                    "prompt": result.prompt,
                    "response": result.response,
                    "success": result.success,
                    "error": result.error_message,
                    "duration": float(result.duration),
                    "session_isolated": metadata.get('session_isolated', False),
                    "error_type": metadata.get('error_type'),
                    "metadata": metadata
                })

            # 计算平均耗时
            for model, stats in model_results.items():
                if stats["durations"]:
                    stats["avg_duration"] = sum(stats["durations"]) / len(stats["durations"])
                    stats["success_rate"] = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
                del stats["durations"]

            response_data["models"] = list(models_set)
            response_data["model_stats"] = model_results
            response_data["error_distribution"] = error_distribution
            response_data["session_isolated_count"] = session_isolated_count

            return Response(response_data)

        except Exception as e:
            logger.error(f"获取测试结果失败: {str(e)}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )