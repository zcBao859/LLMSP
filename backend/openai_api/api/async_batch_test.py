# backend/openai_api/api/async_batch_test.py
"""
异步批量测试API - 支持真正的并发测试
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import threading
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from asgiref.sync import sync_to_async
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from ..models import TestSession, TestResult, TestPlatform
from .model_router import model_router
from ..batch_test_saver import batch_test_saver

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"  # 等待中
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class AsyncTestTask:
    """异步测试任务"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str = ""
    models: List[str] = field(default_factory=list)
    run_count: int = 1
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    progress: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    concurrent_mode: str = "full"  # "full": 完全并发, "model": 模型级并发, "sequential": 顺序执行

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
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "concurrent_mode": self.concurrent_mode
        }


class AsyncBatchTestManager:
    """异步批量测试管理器 - 支持真正的并发"""

    def __init__(self):
        self._executor = None
        self._running_tasks = {}
        self._lock = threading.Lock()
        self._initialize_executor()

    def _initialize_executor(self):
        """初始化或重新初始化线程池"""
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False)
            except:
                pass

        self._executor = ThreadPoolExecutor(max_workers=10)
        logger.info("初始化线程池执行器")

    @property
    def executor(self):
        """获取执行器，如果已关闭则重新创建"""
        if self._executor is None or self._executor._shutdown:
            logger.warning("检测到线程池已关闭，重新初始化")
            self._initialize_executor()
        return self._executor

    def create_task(self, concurrent_mode="full", **kwargs) -> AsyncTestTask:
        """创建异步任务"""
        task = AsyncTestTask(concurrent_mode=concurrent_mode, **kwargs)

        # 初始化进度信息
        task.progress = {
            "total_tests": len(task.models) * task.run_count,
            "completed_tests": 0,
            "model_progress": {model: {"total": task.run_count, "completed": 0}
                               for model in task.models},
            "active_models": [],  # 当前正在测试的模型列表
            "current_test": 0
        }

        # 保存任务到缓存（24小时过期）
        self._save_task_to_cache(task)

        try:
            # 使用 property 获取执行器，确保它是活跃的
            future = self.executor.submit(self._run_task_in_thread, task)

            with self._lock:
                self._running_tasks[task.task_id] = {
                    "task": task,
                    "future": future
                }

            logger.info(f"创建异步任务: {task.task_id}, 并发模式: {concurrent_mode}")
            return task

        except RuntimeError as e:
            if "cannot schedule new futures after shutdown" in str(e):
                logger.error("线程池已关闭，尝试重新初始化")
                self._initialize_executor()

                # 重试一次
                future = self.executor.submit(self._run_task_in_thread, task)

                with self._lock:
                    self._running_tasks[task.task_id] = {
                        "task": task,
                        "future": future
                    }

                return task
            else:
                raise

    def _save_task_to_cache(self, task: AsyncTestTask):
        """保存任务到缓存"""
        cache_key = f"async_task:{task.task_id}"
        cache.set(cache_key, task.to_dict(), 86400)  # 24小时

        # 同时保存到任务列表
        task_list = cache.get("async_task_list", [])
        if task.task_id not in task_list:
            task_list.append(task.task_id)
            cache.set("async_task_list", task_list, 86400)

    def _update_task_progress(self, task: AsyncTestTask):
        """更新任务进度"""
        self._save_task_to_cache(task)

    def _run_task_in_thread(self, task: AsyncTestTask):
        """在线程中运行任务"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            self._update_task_progress(task)

            # 根据并发模式选择执行策略
            if task.concurrent_mode == "full":
                loop.run_until_complete(self._run_full_concurrent(task))
            elif task.concurrent_mode == "model":
                loop.run_until_complete(self._run_model_concurrent(task))
            else:  # sequential
                loop.run_until_complete(self._run_sequential(task))

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()

        except Exception as e:
            logger.error(f"任务 {task.task_id} 执行失败: {str(e)}", exc_info=True)
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now()

        finally:
            self._update_task_progress(task)

            # 清理运行中的任务
            with self._lock:
                if task.task_id in self._running_tasks:
                    del self._running_tasks[task.task_id]

            loop.close()

    async def _run_full_concurrent(self, task: AsyncTestTask):
        """完全并发模式 - 所有模型的所有测试同时运行"""
        logger.info(f"任务 {task.task_id}: 开始完全并发测试")

        # 创建所有测试任务
        all_test_tasks = []
        test_configs = []

        for model_index, model in enumerate(task.models):
            # 更新活跃模型列表
            task.progress["active_models"].append(model)
            self._update_task_progress(task)

            for run_index in range(task.run_count):
                test_config = {
                    "model": model,
                    "model_index": model_index,
                    "run_index": run_index,
                    "test_index": model_index * task.run_count + run_index
                }
                test_configs.append(test_config)

        # 根据模型类型设置并发限制
        # Web模型使用较小的并发数，API模型可以使用较大的并发数
        web_semaphore = asyncio.Semaphore(3)  # Web模型最多3个并发
        api_semaphore = asyncio.Semaphore(20)  # API模型最多20个并发

        async def run_single_test_with_limit(config):
            """根据模型类型限制并发"""
            model = config["model"]
            is_web_model = 'web' in model.lower()

            semaphore = web_semaphore if is_web_model else api_semaphore
            async with semaphore:
                return await self._run_single_test_with_config(task, config)

        # 创建所有测试任务
        for config in test_configs:
            test_task = run_single_test_with_limit(config)
            all_test_tasks.append(test_task)

        logger.info(f"创建了 {len(all_test_tasks)} 个并发测试任务")

        # 执行所有测试
        all_results = await asyncio.gather(*all_test_tasks, return_exceptions=True)

        # 处理结果
        session = await self._create_test_session(task)

        for i, result in enumerate(all_results):
            if isinstance(result, Exception):
                logger.error(f"测试任务 {i} 失败: {str(result)}")
                # 创建失败结果
                config = test_configs[i]
                result = {
                    "model": config["model"],
                    "run_index": config["run_index"],
                    "prompt": task.prompt,
                    "response": "",
                    "success": False,
                    "error": str(result),
                    "duration": 0,
                    "timestamp": datetime.now().isoformat()
                }

            if session:
                await self._save_test_result_async(session, result, test_configs[i]["test_index"])

        # 生成报告
        await self._finalize_results(task, session)

        logger.info(f"任务 {task.task_id} 完成，共 {len(all_results)} 个测试")

    async def _run_model_concurrent(self, task: AsyncTestTask):
        """模型级并发 - 每个模型内部并发，模型之间顺序执行"""
        logger.info(f"任务 {task.task_id}: 开始模型级并发测试")

        session = await self._create_test_session(task)

        for model_index, model in enumerate(task.models):
            logger.info(f"开始测试模型 {model}")

            # 更新活跃模型
            task.progress["active_models"] = [model]
            self._update_task_progress(task)

            # 创建该模型的所有测试任务
            model_tasks = []
            is_web_model = 'web' in model.lower()

            # Web模型限制并发数
            semaphore = asyncio.Semaphore(2 if is_web_model else 10)

            async def run_with_semaphore(run_index):
                async with semaphore:
                    config = {
                        "model": model,
                        "model_index": model_index,
                        "run_index": run_index,
                        "test_index": model_index * task.run_count + run_index
                    }
                    return await self._run_single_test_with_config(task, config)

            # 创建该模型的所有测试
            for run_index in range(task.run_count):
                model_tasks.append(run_with_semaphore(run_index))

            # 并发执行该模型的所有测试
            model_results = await asyncio.gather(*model_tasks, return_exceptions=True)

            # 处理结果
            for i, result in enumerate(model_results):
                if isinstance(result, Exception):
                    logger.error(f"模型 {model} 测试 {i} 失败: {str(result)}")
                    result = {
                        "model": model,
                        "run_index": i,
                        "prompt": task.prompt,
                        "response": "",
                        "success": False,
                        "error": str(result),
                        "duration": 0,
                        "timestamp": datetime.now().isoformat()
                    }

                if session:
                    await self._save_test_result_async(session, result, model_index * task.run_count + i)

            # 完成该模型后的间隔
            if model_index < len(task.models) - 1:
                await asyncio.sleep(2)

        # 清空活跃模型列表
        task.progress["active_models"] = []
        self._update_task_progress(task)

        await self._finalize_results(task, session)

    async def _run_sequential(self, task: AsyncTestTask):
        """顺序执行模式 - 传统的顺序执行方式"""
        logger.info(f"任务 {task.task_id}: 开始顺序执行测试")

        session = await self._create_test_session(task)

        for model_index, model in enumerate(task.models):
            logger.info(f"开始测试模型 {model}")

            # 更新活跃模型
            task.progress["active_models"] = [model]
            self._update_task_progress(task)

            for run_index in range(task.run_count):
                config = {
                    "model": model,
                    "model_index": model_index,
                    "run_index": run_index,
                    "test_index": model_index * task.run_count + run_index
                }

                result = await self._run_single_test_with_config(task, config)

                if session:
                    await self._save_test_result_async(session, result, config["test_index"])

                # 每次测试间隔
                if run_index < task.run_count - 1:
                    await asyncio.sleep(1)

            # 模型间间隔
            if model_index < len(task.models) - 1:
                await asyncio.sleep(2)

        # 清空活跃模型列表
        task.progress["active_models"] = []
        self._update_task_progress(task)

        await self._finalize_results(task, session)

    async def _run_single_test_with_config(self, task: AsyncTestTask, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个测试（带配置）"""
        model = config["model"]
        run_index = config["run_index"]

        start_time = asyncio.get_event_loop().time()

        try:
            # 检查是否有检查点
            checkpoint = batch_test_saver.load_checkpoint(model)
            if checkpoint and checkpoint.get("results"):
                existing_results = checkpoint["results"]
                for existing in existing_results:
                    if (existing.get("prompt") == task.prompt and
                            existing.get("run_index") == run_index):
                        logger.info(f"从检查点恢复: {model} - 运行 {run_index + 1}")
                        return existing

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

            # 构建参数
            kwargs = {}
            if task.temperature is not None:
                kwargs['temperature'] = task.temperature
            if task.max_tokens is not None:
                kwargs['max_tokens'] = task.max_tokens

            # 调用模型
            response = await model_router.create_chat_completion(
                messages=messages,
                model=model,
                stream=False,
                **kwargs
            )

            # 提取结果
            if hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content
                duration = asyncio.get_event_loop().time() - start_time

                result = {
                    "model": model,
                    "run_index": run_index,
                    "prompt": task.prompt,
                    "response": content,
                    "success": True,
                    "duration": duration,
                    "timestamp": datetime.now().isoformat()
                }

                # 立即保存到检查点
                batch_test_saver.save_single_result(model, result)

                # 更新进度
                task.progress["model_progress"][model]["completed"] += 1
                task.progress["completed_tests"] += 1
                self._update_task_progress(task)

                return result
            else:
                raise Exception("响应格式错误")

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.error(f"测试失败 - 模型: {model}, 错误: {str(e)}")

            result = {
                "model": model,
                "run_index": run_index,
                "prompt": task.prompt,
                "response": "",
                "success": False,
                "error": str(e),
                "duration": duration,
                "timestamp": datetime.now().isoformat()
            }

            # 保存失败结果
            batch_test_saver.save_single_result(model, result)

            # 更新进度
            task.progress["model_progress"][model]["completed"] += 1
            task.progress["completed_tests"] += 1
            self._update_task_progress(task)

            return result

    async def _create_test_session(self, task: AsyncTestTask):
        """创建测试会话 - 使用 sync_to_async"""
        try:
            @sync_to_async
            @transaction.atomic
            def create_session():
                test_platform, _ = TestPlatform.objects.get_or_create(
                    name='async_batch_test',
                    defaults={
                        'platform_type': 'api',
                        'base_url': ''
                    }
                )

                session = TestSession.objects.create(
                    platform=test_platform,
                    session_id=task.task_id,
                    test_type='async_batch_concurrent',
                    total_tests=task.progress["total_tests"]
                )
                return session

            return await create_session()
        except Exception as e:
            logger.error(f"创建测试会话失败: {e}")
            return None

    async def _save_test_result_async(self, session: TestSession, result: Dict[str, Any], test_index: int):
        """异步保存测试结果到数据库"""
        if not session:
            logger.debug("跳过数据库结果保存 - 没有会话")
            return

        @sync_to_async
        @transaction.atomic
        def save_result():
            TestResult.objects.create(
                session=session,
                test_index=test_index,
                prompt=result.get("prompt", ""),
                response=result.get("response", ""),
                success=result.get("success", False),
                error_message=result.get("error", ""),
                duration=result.get("duration", 0),
                metadata={
                    "model": result.get("model"),
                    "run_index": result.get("run_index")
                }
            )

        try:
            await save_result()
        except Exception as e:
            logger.error(f"保存测试结果失败: {e}")

    async def _finalize_results(self, task: AsyncTestTask, session: Optional[TestSession]):
        """完成结果处理 - 使用 sync_to_async"""
        # 更新会话状态
        if session:
            @sync_to_async
            @transaction.atomic
            def update_session():
                # 重新获取会话以避免并发问题
                try:
                    current_session = TestSession.objects.get(id=session.id)
                    current_session.status = 'completed'
                    current_session.completed_at = datetime.now()

                    # 计算成功和失败数
                    results = TestResult.objects.filter(session=current_session)
                    current_session.successful_tests = results.filter(success=True).count()
                    current_session.failed_tests = results.filter(success=False).count()
                    current_session.save()
                except TestSession.DoesNotExist:
                    logger.error(f"会话 {session.id} 不存在")

            try:
                await update_session()
            except Exception as e:
                logger.error(f"更新会话状态失败: {e}")

        # 为每个模型生成报告
        for model in task.models:
            try:
                saved_files = batch_test_saver.finalize_test_results(
                    model,
                    {"task_id": task.task_id, "async": True, "concurrent_mode": task.concurrent_mode}
                )
                logger.info(f"模型 {model} 的测试结果已保存: {saved_files}")
            except Exception as e:
                logger.error(f"保存模型 {model} 结果失败: {e}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        # 先从缓存获取
        cache_key = f"async_task:{task_id}"
        task_data = cache.get(cache_key)

        if task_data:
            return task_data

        # 检查运行中的任务
        with self._lock:
            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]["task"]
                return task.to_dict()

        return None

    def list_tasks(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有任务"""
        task_list = cache.get("async_task_list", [])
        tasks = []

        for task_id in task_list:
            task_data = self.get_task_status(task_id)
            if task_data:
                if status_filter is None or task_data["status"] == status_filter:
                    tasks.append(task_data)

        # 按创建时间倒序排序
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        return tasks

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            if task_id in self._running_tasks:
                future = self._running_tasks[task_id]["future"]
                future.cancel()

                # 更新任务状态
                task = self._running_tasks[task_id]["task"]
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                self._update_task_progress(task)

                return True

        return False

    def __del__(self):
        """清理资源"""
        try:
            if self._executor:
                self._executor.shutdown(wait=True)
        except:
            pass


# 修改全局实例创建方式
_async_test_manager_instance = None
_async_test_manager_lock = threading.Lock()


def get_async_test_manager():
    """获取或创建异步测试管理器实例"""
    global _async_test_manager_instance

    with _async_test_manager_lock:
        if _async_test_manager_instance is None:
            _async_test_manager_instance = AsyncBatchTestManager()
        return _async_test_manager_instance


class AsyncBatchTestView(APIView):
    """异步批量测试API视图"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """创建异步批量测试任务"""
        try:
            # 使用函数获取管理器实例
            async_test_manager = get_async_test_manager()

            # 验证请求数据
            prompt = request.data.get('prompt')
            models = request.data.get('models', [])
            run_count = request.data.get('run_count', 1)
            temperature = request.data.get('temperature')
            max_tokens = request.data.get('max_tokens')
            system_prompt = request.data.get('system_prompt')
            concurrent_mode = request.data.get('concurrent_mode', 'full')  # 默认完全并发

            if not prompt:
                return Response(
                    {"error": "prompt is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not models:
                return Response(
                    {"error": "models is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not isinstance(models, list):
                return Response(
                    {"error": "models must be a list"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if run_count < 1:
                return Response(
                    {"error": "run_count must be at least 1"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if concurrent_mode not in ['full', 'model', 'sequential']:
                return Response(
                    {"error": "concurrent_mode must be one of: full, model, sequential"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 创建异步任务
            task = async_test_manager.create_task(
                prompt=prompt,
                models=models,
                run_count=run_count,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                concurrent_mode=concurrent_mode
            )

            return Response({
                "task_id": task.task_id,
                "status": task.status.value,
                "message": f"异步任务已创建（{concurrent_mode}模式），将测试 {len(models)} 个模型，每个运行 {run_count} 次",
                "progress_url": f"/api/v1/async-batch/tasks/{task.task_id}/",
                "models": models,
                "total_tests": len(models) * run_count,
                "concurrent_mode": concurrent_mode
            })

        except Exception as e:
            logger.error(f"创建异步任务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request):
        """列出所有异步任务"""
        async_test_manager = get_async_test_manager()
        status_filter = request.query_params.get('status')
        tasks = async_test_manager.list_tasks(status_filter)

        return Response({
            "tasks": tasks,
            "total": len(tasks)
        })


class AsyncTaskDetailView(APIView):
    """异步任务详情视图"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, task_id):
        """获取任务详情和进度"""
        async_test_manager = get_async_test_manager()
        task_data = async_test_manager.get_task_status(task_id)

        if not task_data:
            return Response(
                {"error": "Task not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 添加进度百分比
        if task_data["progress"]["total_tests"] > 0:
            task_data["progress"]["percentage"] = (
                    task_data["progress"]["completed_tests"] /
                    task_data["progress"]["total_tests"] * 100
            )
        else:
            task_data["progress"]["percentage"] = 0

        return Response(task_data)

    def delete(self, request, task_id):
        """取消任务"""
        async_test_manager = get_async_test_manager()
        success = async_test_manager.cancel_task(task_id)

        if success:
            return Response({"message": "Task cancelled successfully"})
        else:
            return Response(
                {"error": "Task not found or already completed"},
                status=status.HTTP_400_BAD_REQUEST
            )


class AsyncTaskResultsView(APIView):
    """异步任务结果视图"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, task_id):
        """获取任务的测试结果"""
        async_test_manager = get_async_test_manager()

        # 检查任务是否存在
        task_data = async_test_manager.get_task_status(task_id)

        if not task_data:
            return Response(
                {"error": "Task not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 尝试从数据库获取结果
        try:
            session = TestSession.objects.filter(session_id=task_id).first()

            if session:
                # 从数据库构建响应
                results = TestResult.objects.filter(session=session).order_by('test_index')

                response_data = {
                    "task_id": task_id,
                    "status": task_data["status"],
                    "models": task_data["models"],
                    "total_tests": session.total_tests,
                    "successful_tests": session.successful_tests,
                    "failed_tests": session.failed_tests,
                    "concurrent_mode": task_data.get("concurrent_mode", "unknown"),
                    "results": []
                }

                # 按模型分组结果
                model_results = {}
                for result in results:
                    metadata = result.metadata or {}
                    model = metadata.get('model', 'unknown')

                    if model not in model_results:
                        model_results[model] = []

                    model_results[model].append({
                        "run_index": metadata.get('run_index', 0),
                        "prompt": result.prompt,
                        "response": result.response,
                        "success": result.success,
                        "error": result.error_message,
                        "duration": float(result.duration)
                    })

                response_data["model_results"] = model_results
            else:
                # 数据库中没有会话，从缓存构建响应
                logger.info(f"数据库中未找到会话 {task_id}，使用缓存数据")

                response_data = {
                    "task_id": task_id,
                    "status": task_data["status"],
                    "models": task_data["models"],
                    "total_tests": task_data["progress"]["total_tests"],
                    "completed_tests": task_data["progress"]["completed_tests"],
                    "concurrent_mode": task_data.get("concurrent_mode", "unknown"),
                    "progress": task_data["progress"],
                    "from_cache": True
                }

                # 如果任务已完成，尝试从检查点文件读取结果
                if task_data["status"] == "completed":
                    model_results = {}
                    for model in task_data["models"]:
                        checkpoint = batch_test_saver.load_checkpoint(model)
                        if checkpoint and checkpoint.get("results"):
                            model_results[model] = checkpoint["results"]

                    if model_results:
                        response_data["model_results"] = model_results

        except Exception as e:
            logger.error(f"获取任务结果时出错: {str(e)}")

            # 降级到仅使用缓存数据
            response_data = {
                "task_id": task_id,
                "status": task_data["status"],
                "models": task_data["models"],
                "total_tests": task_data["progress"]["total_tests"],
                "completed_tests": task_data["progress"]["completed_tests"],
                "concurrent_mode": task_data.get("concurrent_mode", "unknown"),
                "progress": task_data["progress"],
                "error": "Database error, showing cached data",
                "from_cache": True
            }

        # 添加保存的文件路径
        saved_files = {}
        for model in task_data["models"]:
            # 清理模型名称
            safe_model_name = model.replace(':', '_').replace('/', '_').replace('\\', '_')
            files = batch_test_saver.list_all_results().get(safe_model_name, [])

            # 尝试不同的目录名称格式
            if not files:
                # 尝试原始模型名
                files = batch_test_saver.list_all_results().get(model, [])

            if not files:
                # 尝试处理特殊情况（如 jiutian-web -> jiutian）
                if '-web' in model:
                    base_name = model.replace('-web', '')
                    files = batch_test_saver.list_all_results().get(base_name, [])

            if files:
                saved_files[model] = files

        response_data["saved_files"] = saved_files

        return Response(response_data)

class WebModelTestConfig:
    """Web模型测试配置类"""

    # Web模型识别模式
    WEB_MODEL_PATTERNS = [
        'web',  # 包含 'web' 的模型名
        '-web',  # 以 '-web' 结尾
        '_web',  # 以 '_web' 结尾
    ]

    # Web模型特定配置
    WEB_MODEL_SETTINGS = {
        "force_new_chat": True,  # 强制每次新建对话
        "session_isolation_mode": "strict",  # 严格会话隔离
        "new_chat_cooldown": 3,  # 新建对话冷却时间（秒）
        "inter_test_delay": 2,  # 测试间隔时间（秒）
        "max_concurrent": 1,  # 最大并发数（建议为1）
        "retry_on_session_error": True,  # 会话错误时重试
        "clear_cookies_interval": 10,  # 每N次测试清理cookies
    }

    @classmethod
    def is_web_model(cls, model_name: str) -> bool:
        """判断是否为Web模型"""
        model_lower = model_name.lower()
        return any(pattern in model_lower for pattern in cls.WEB_MODEL_PATTERNS)

    @classmethod
    def get_web_model_config(cls, model_name: str) -> Dict[str, Any]:
        """获取Web模型的特定配置"""
        if cls.is_web_model(model_name):
            return cls.WEB_MODEL_SETTINGS.copy()
        return {}