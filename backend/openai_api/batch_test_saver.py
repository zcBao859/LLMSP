# backend/openai_api/batch_test_saver.py
"""
批量测试结果保存管理器 - 改进版，支持新的目录结构和简化的断点续传
"""
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BatchTestResultSaver:
    """批量测试结果保存器 - 改进版"""

    def __init__(self, base_dir: str = None):
        """
        初始化保存器

        Args:
            base_dir: 基础目录，默认为 openai_api/test/results
        """
        if base_dir is None:
            # 获取当前文件所在目录（openai_api）
            current_dir = Path(__file__).parent
            base_dir = current_dir / "test" / "results"

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"批量测试结果保存器初始化，目录: {self.base_dir}")

    def _get_model_dir(self, model_name: str) -> Path:
        """获取模型专属目录"""
        # 清理模型名称，移除特殊字符
        safe_model_name = model_name.replace('/', '_').replace('\\', '_').replace(':', '_')

        # 根据模型名称映射到正确的目录
        model_dir_mapping = {
            'claude': 'claude',
            'doubao-api': 'doubao_api',
            'doubao-seed': 'doubao_api',
            'jiutian': 'jiutian',
            'jiutian-web': 'jiutian',
            'modelscope-deepsek': 'modelscope_deepseek',
            'modelscope-llama': 'modelscope_llama',
            'modelscope-qwen': 'modelscope_qwen',
            'o43': 'o43',
            'o43-web': 'o43',
            'gpt-4o': 'o43',
            'yuanbao': 'yuanbao',
            'yuanbao-web': 'yuanbao',
            'huanxin-DeepSeek-R1-32B-Distil': 'huanxin-DeepSeek-R1-32B-Distil',
            'huanxin-DeepSeek-Llama-70B': 'huanxin-DeepSeek-Llama-70B',
        }

        # 查找匹配的目录名
        dir_name = safe_model_name

        # 特殊处理 Ollama 模型
        if safe_model_name.startswith('ollama-'):
            # 移除 ollama- 前缀，使用模型名作为目录名
            ollama_model = safe_model_name[7:]
            # 进一步清理模型名中的特殊字符
            ollama_model = ollama_model.replace(':', '_')
            dir_name = f"ollama_{ollama_model}"
        else:
            # 其他模型使用预定义映射
            for key, value in model_dir_mapping.items():
                if key.lower() in safe_model_name.lower():
                    dir_name = value
                    break

        model_dir = self.base_dir / dir_name
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir

    def _get_checkpoint_file(self, model_name: str) -> Path:
        """获取模型的检查点文件路径"""
        model_dir = self._get_model_dir(model_name)
        return model_dir / "enhanced_checkpoint.json"

    def _get_test_data_file(self, model_name: str) -> Path:
        """获取测试数据文件路径"""
        model_dir = self._get_model_dir(model_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return model_dir / f"enhanced_test_data_{timestamp}.json"

    def _get_report_file(self, model_name: str) -> Path:
        """获取报告文件路径"""
        model_dir = self._get_model_dir(model_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return model_dir / f"enhanced_report_{timestamp}.md"

    def save_checkpoint(self, model_name: str, test_results: List[Dict[str, Any]],
                        test_info: Dict[str, Any] = None):
        """
        保存检查点 - 每次测试完成后立即保存

        Args:
            model_name: 模型名称
            test_results: 当前所有的测试结果
            test_info: 测试信息
        """
        checkpoint_file = self._get_checkpoint_file(model_name)

        checkpoint_data = {
            "model_name": model_name,
            "last_updated": datetime.now().isoformat(),
            "test_info": test_info or {},
            "total_tests": len(test_results),
            "completed_tests": len(test_results),
            "results": test_results
        }

        try:
            # 创建临时文件避免写入失败导致数据丢失
            temp_file = checkpoint_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

            # 原子性地替换文件
            temp_file.replace(checkpoint_file)

            logger.info(f"保存检查点成功: {model_name} - {len(test_results)} 个结果")

        except Exception as e:
            logger.error(f"保存检查点失败: {e}")
            # 尝试清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            raise

    def load_checkpoint(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        加载检查点

        Returns:
            检查点数据，如果不存在则返回None
        """
        checkpoint_file = self._get_checkpoint_file(model_name)

        if not checkpoint_file.exists():
            logger.info(f"未找到 {model_name} 的检查点")
            return None

        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            logger.info(f"加载检查点成功: {model_name} - {checkpoint_data.get('total_tests', 0)} 个已完成的测试")
            return checkpoint_data

        except Exception as e:
            logger.error(f"加载检查点失败: {e}")
            return None

    def save_single_result(self, model_name: str, result: Dict[str, Any],
                           append_to_checkpoint: bool = True) -> str:
        """
        保存单个测试结果并更新检查点

        Args:
            model_name: 模型名称
            result: 单个测试结果
            append_to_checkpoint: 是否追加到检查点

        Returns:
            保存的文件路径
        """
        # 如果需要追加到检查点
        if append_to_checkpoint:
            checkpoint = self.load_checkpoint(model_name)
            if checkpoint:
                results = checkpoint.get('results', [])
                results.append(result)
            else:
                results = [result]

            # 保存更新后的检查点
            self.save_checkpoint(model_name, results)

        return str(self._get_checkpoint_file(model_name))

    def finalize_test_results(self, model_name: str,
                              additional_info: Dict[str, Any] = None) -> Dict[str, str]:
        """
        完成测试，生成最终的测试数据文件和报告

        Args:
            model_name: 模型名称
            additional_info: 额外信息

        Returns:
            生成的文件路径字典
        """
        # 加载检查点数据
        checkpoint = self.load_checkpoint(model_name)
        if not checkpoint:
            logger.warning(f"未找到 {model_name} 的检查点数据")
            return {}

        results = checkpoint.get('results', [])
        if not results:
            logger.warning(f"{model_name} 没有测试结果")
            return {}

        # 生成测试数据文件
        test_data_file = self._get_test_data_file(model_name)
        test_data = {
            "model_name": model_name,
            "test_completed_at": datetime.now().isoformat(),
            "test_info": checkpoint.get('test_info', {}),
            "additional_info": additional_info or {},
            "total_tests": len(results),
            "successful_tests": sum(1 for r in results if r.get("success", False)),
            "failed_tests": sum(1 for r in results if not r.get("success", False)),
            "results": results
        }

        # 计算统计信息
        if results:
            durations = [r.get("duration", 0) for r in results if r.get("duration", 0) > 0]
            if durations:
                test_data["statistics"] = {
                    "avg_duration": sum(durations) / len(durations),
                    "min_duration": min(durations),
                    "max_duration": max(durations),
                    "success_rate": test_data["successful_tests"] / test_data["total_tests"] * 100
                }

        # 保存测试数据
        with open(test_data_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)

        # 生成Markdown报告
        report_file = self._generate_markdown_report(model_name, test_data)

        # 清理检查点（可选，根据需求决定是否保留）
        # checkpoint_file = self._get_checkpoint_file(model_name)
        # if checkpoint_file.exists():
        #     checkpoint_file.unlink()

        return {
            "test_data": str(test_data_file),
            "report": str(report_file),
            "checkpoint": str(self._get_checkpoint_file(model_name))
        }

    def _generate_markdown_report(self, model_name: str, test_data: Dict[str, Any]) -> Path:
        """生成Markdown格式的测试报告"""
        report_file = self._get_report_file(model_name)

        with open(report_file, 'w', encoding='utf-8') as f:
            # 标题
            f.write(f"# {model_name} 测试报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # 概览
            f.write("## 测试概览\n\n")
            f.write(f"- **总测试数**: {test_data['total_tests']}\n")
            f.write(f"- **成功**: {test_data['successful_tests']}\n")
            f.write(f"- **失败**: {test_data['failed_tests']}\n")

            if 'statistics' in test_data:
                stats = test_data['statistics']
                f.write(f"- **成功率**: {stats['success_rate']:.1f}%\n")
                f.write(f"- **平均耗时**: {stats['avg_duration']:.2f}秒\n")
                f.write(f"- **最快/最慢**: {stats['min_duration']:.2f}秒 / {stats['max_duration']:.2f}秒\n")

            f.write("\n")

            # 测试详情
            f.write("## 测试详情\n\n")

            for i, result in enumerate(test_data['results'], 1):
                f.write(f"### 测试 {i}\n\n")
                f.write(f"**状态**: {'✅ 成功' if result.get('success', False) else '❌ 失败'}\n\n")
                f.write(f"**提示词**: {result.get('prompt', 'N/A')}\n\n")

                if result.get('response'):
                    f.write(
                        f"**响应**:\n```\n{result['response'][:500]}{'...' if len(result.get('response', '')) > 500 else ''}\n```\n\n")

                if result.get('error'):
                    f.write(f"**错误**: {result['error']}\n\n")

                f.write(f"**耗时**: {result.get('duration', 0):.2f}秒\n\n")
                f.write("---\n\n")

        logger.info(f"生成报告: {report_file}")
        return report_file

    def get_test_progress(self, model_name: str) -> Dict[str, Any]:
        """获取测试进度"""
        checkpoint = self.load_checkpoint(model_name)
        if not checkpoint:
            return {
                "model_name": model_name,
                "status": "not_started",
                "completed_tests": 0
            }

        results = checkpoint.get('results', [])
        return {
            "model_name": model_name,
            "status": "in_progress" if checkpoint else "not_started",
            "completed_tests": len(results),
            "successful_tests": sum(1 for r in results if r.get("success", False)),
            "last_updated": checkpoint.get('last_updated', 'unknown')
        }

    def clear_checkpoint(self, model_name: str):
        """清除检查点文件"""
        checkpoint_file = self._get_checkpoint_file(model_name)
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.info(f"清除检查点: {model_name}")

    def list_all_results(self) -> Dict[str, List[str]]:
        """列出所有保存的结果文件"""
        results = {}

        for model_dir in self.base_dir.iterdir():
            if model_dir.is_dir():
                model_files = []

                # 查找所有相关文件
                for pattern in ["enhanced_test_data_*.json", "enhanced_report_*.md", "enhanced_checkpoint.json"]:
                    model_files.extend([str(f) for f in model_dir.glob(pattern)])

                if model_files:
                    results[model_dir.name] = sorted(model_files)

        return results


# 全局实例
batch_test_saver = BatchTestResultSaver()