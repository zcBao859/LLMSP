# backend/openai_api/api/response_saver.py
"""
模型响应保存管理器 - 用于保存模型回复并支持断点续传
"""
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class ResponseSaver:
    """响应保存管理器"""

    def __init__(self, base_dir: str = None):
        """
        初始化保存管理器

        Args:
            base_dir: 基础保存目录，默认使用settings中的配置
        """
        if base_dir is None:
            base_dir = getattr(settings, 'MODEL_RESPONSES_DIR', 'model_responses')

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"初始化响应保存管理器，基础目录: {self.base_dir}")

    def _get_model_dir(self, model_name: str) -> Path:
        """获取模型专属目录"""
        # 清理模型名称，移除特殊字符
        safe_model_name = model_name.replace('/', '_').replace('\\', '_').replace(':', '_')
        model_dir = self.base_dir / safe_model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir

    def _generate_response_id(self, prompt: str, timestamp: str = None) -> str:
        """生成响应ID（基于prompt的hash）"""
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 使用prompt的前100个字符生成hash
        prompt_hash = hashlib.md5(prompt[:100].encode()).hexdigest()[:8]
        return f"{timestamp}_{prompt_hash}"

    def _get_responses_file(self, model_name: str) -> Path:
        """获取模型的响应文件路径"""
        model_dir = self._get_model_dir(model_name)
        return model_dir / "responses.json"

    def _get_checkpoint_file(self, model_name: str) -> Path:
        """获取检查点文件路径"""
        model_dir = self._get_model_dir(model_name)
        return model_dir / "checkpoint.json"

    def load_responses(self, model_name: str) -> Dict[str, Any]:
        """
        加载模型的所有响应记录

        Returns:
            包含所有响应的字典
        """
        responses_file = self._get_responses_file(model_name)

        if responses_file.exists():
            try:
                with open(responses_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"加载了 {model_name} 的 {len(data.get('responses', []))} 条响应记录")
                    return data
            except Exception as e:
                logger.error(f"加载响应文件失败: {e}")
                return self._create_empty_responses_data(model_name)
        else:
            return self._create_empty_responses_data(model_name)

    def _create_empty_responses_data(self, model_name: str) -> Dict[str, Any]:
        """创建空的响应数据结构"""
        return {
            "model_name": model_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "total_responses": 0,
            "responses": []
        }

    def save_response(self, model_name: str, prompt: str, response: str,
                      metadata: Dict[str, Any] = None) -> str:
        """
        保存单个响应

        Args:
            model_name: 模型名称
            prompt: 输入提示词
            response: 模型响应
            metadata: 额外的元数据（如token使用量、耗时等）

        Returns:
            响应ID
        """
        # 加载现有数据
        data = self.load_responses(model_name)

        # 生成响应记录
        timestamp = datetime.now()
        response_id = self._generate_response_id(prompt, timestamp.strftime("%Y%m%d_%H%M%S"))

        response_record = {
            "id": response_id,
            "timestamp": timestamp.isoformat(),
            "prompt": prompt,
            "response": response,
            "metadata": metadata or {}
        }

        # 添加到数据中
        data["responses"].append(response_record)
        data["total_responses"] = len(data["responses"])
        data["updated_at"] = timestamp.isoformat()

        # 保存文件
        responses_file = self._get_responses_file(model_name)
        try:
            with open(responses_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"保存响应成功: {model_name} - {response_id}")
            return response_id

        except Exception as e:
            logger.error(f"保存响应失败: {e}")
            raise

    def save_batch_responses(self, model_name: str, responses: List[Dict[str, Any]]) -> int:
        """
        批量保存响应

        Args:
            model_name: 模型名称
            responses: 响应列表，每个响应包含 prompt, response, metadata

        Returns:
            保存的响应数量
        """
        # 加载现有数据
        data = self.load_responses(model_name)
        timestamp = datetime.now()

        # 批量添加响应
        saved_count = 0
        for resp in responses:
            response_id = self._generate_response_id(
                resp.get("prompt", ""),
                timestamp.strftime("%Y%m%d_%H%M%S")
            )

            response_record = {
                "id": response_id,
                "timestamp": timestamp.isoformat(),
                "prompt": resp.get("prompt", ""),
                "response": resp.get("response", ""),
                "metadata": resp.get("metadata", {})
            }

            data["responses"].append(response_record)
            saved_count += 1
            timestamp = datetime.now()  # 更新时间戳

        # 更新统计信息
        data["total_responses"] = len(data["responses"])
        data["updated_at"] = timestamp.isoformat()

        # 保存文件
        responses_file = self._get_responses_file(model_name)
        try:
            with open(responses_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"批量保存 {saved_count} 条响应到 {model_name}")
            return saved_count

        except Exception as e:
            logger.error(f"批量保存响应失败: {e}")
            raise

    def save_checkpoint(self, model_name: str, checkpoint_data: Dict[str, Any]):
        """
        保存检查点（用于断点续传）

        Args:
            model_name: 模型名称
            checkpoint_data: 检查点数据，如当前进度、状态等
        """
        checkpoint_file = self._get_checkpoint_file(model_name)

        checkpoint = {
            "model_name": model_name,
            "timestamp": datetime.now().isoformat(),
            "data": checkpoint_data
        }

        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)

            logger.info(f"保存检查点成功: {model_name}")

        except Exception as e:
            logger.error(f"保存检查点失败: {e}")
            raise

    def load_checkpoint(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        加载检查点

        Returns:
            检查点数据，如果不存在则返回None
        """
        checkpoint_file = self._get_checkpoint_file(model_name)

        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint = json.load(f)
                    logger.info(f"加载检查点成功: {model_name}")
                    return checkpoint.get("data")
            except Exception as e:
                logger.error(f"加载检查点失败: {e}")
                return None

        return None

    def delete_checkpoint(self, model_name: str):
        """删除检查点（通常在任务完成后调用）"""
        checkpoint_file = self._get_checkpoint_file(model_name)

        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
                logger.info(f"删除检查点成功: {model_name}")
            except Exception as e:
                logger.error(f"删除检查点失败: {e}")

    def get_response_by_id(self, model_name: str, response_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取特定响应"""
        data = self.load_responses(model_name)

        for response in data.get("responses", []):
            if response.get("id") == response_id:
                return response

        return None

    def get_responses_by_prompt(self, model_name: str, prompt: str) -> List[Dict[str, Any]]:
        """根据prompt获取所有相关响应（用于查找重复）"""
        data = self.load_responses(model_name)

        matching_responses = []
        for response in data.get("responses", []):
            if response.get("prompt") == prompt:
                matching_responses.append(response)

        return matching_responses

    def get_statistics(self, model_name: str) -> Dict[str, Any]:
        """获取模型响应统计信息"""
        data = self.load_responses(model_name)
        responses = data.get("responses", [])

        if not responses:
            return {
                "model_name": model_name,
                "total_responses": 0,
                "unique_prompts": 0,
                "avg_response_length": 0,
                "first_response": None,
                "last_response": None
            }

        # 计算统计信息
        unique_prompts = len(set(r.get("prompt", "") for r in responses))
        total_length = sum(len(r.get("response", "")) for r in responses)
        avg_length = total_length / len(responses) if responses else 0

        # 排序响应
        sorted_responses = sorted(responses, key=lambda r: r.get("timestamp", ""))

        return {
            "model_name": model_name,
            "total_responses": len(responses),
            "unique_prompts": unique_prompts,
            "avg_response_length": round(avg_length, 2),
            "first_response": sorted_responses[0].get("timestamp") if sorted_responses else None,
            "last_response": sorted_responses[-1].get("timestamp") if sorted_responses else None,
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at")
        }

    def export_responses(self, model_name: str, format: str = "json") -> str:
        """
        导出响应数据

        Args:
            model_name: 模型名称
            format: 导出格式 (json, csv, txt)

        Returns:
            导出文件路径
        """
        data = self.load_responses(model_name)
        model_dir = self._get_model_dir(model_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            export_file = model_dir / f"export_{timestamp}.json"
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        elif format == "csv":
            import csv
            export_file = model_dir / f"export_{timestamp}.csv"

            with open(export_file, 'w', encoding='utf-8', newline='') as f:
                if data.get("responses"):
                    # 获取所有可能的字段
                    fieldnames = ['id', 'timestamp', 'prompt', 'response']

                    # 添加metadata中的字段
                    metadata_fields = set()
                    for resp in data["responses"]:
                        if resp.get("metadata"):
                            metadata_fields.update(resp["metadata"].keys())

                    fieldnames.extend(sorted(metadata_fields))

                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()

                    for resp in data["responses"]:
                        row = {
                            'id': resp.get('id', ''),
                            'timestamp': resp.get('timestamp', ''),
                            'prompt': resp.get('prompt', ''),
                            'response': resp.get('response', '')
                        }

                        # 添加metadata字段
                        if resp.get("metadata"):
                            row.update(resp["metadata"])

                        writer.writerow(row)

        elif format == "txt":
            export_file = model_dir / f"export_{timestamp}.txt"

            with open(export_file, 'w', encoding='utf-8') as f:
                f.write(f"模型: {model_name}\n")
                f.write(f"导出时间: {datetime.now().isoformat()}\n")
                f.write(f"总响应数: {data.get('total_responses', 0)}\n")
                f.write("=" * 80 + "\n\n")

                for resp in data.get("responses", []):
                    f.write(f"ID: {resp.get('id', '')}\n")
                    f.write(f"时间: {resp.get('timestamp', '')}\n")
                    f.write(f"提示词: {resp.get('prompt', '')}\n")
                    f.write(f"响应: {resp.get('response', '')}\n")

                    if resp.get("metadata"):
                        f.write(f"元数据: {json.dumps(resp['metadata'], ensure_ascii=False)}\n")

                    f.write("-" * 80 + "\n\n")

        else:
            raise ValueError(f"不支持的导出格式: {format}")

        logger.info(f"导出 {model_name} 的响应到 {export_file}")
        return str(export_file)


# 全局实例
response_saver = ResponseSaver()