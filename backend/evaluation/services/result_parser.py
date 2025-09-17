# evaluation/services/result_parser.py
"""结果解析器 - 解析OpenCompass输出结果"""
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import pandas as pd

logger = logging.getLogger(__name__)


class ResultParser:
    """OpenCompass结果解析器"""

    METRIC_MAPPINGS = {
        'accuracy': 'accuracy',
        'acc': 'accuracy',
        'bleu': 'bleu_score',
        'rouge': 'rouge_score',
        'pass@': 'pass_rate',
        'score': 'score'
    }

    def parse_file(self, file_path: Path) -> Dict:
        """根据文件类型自动选择解析方法"""
        if not file_path.exists():
            return {}

        parsers = {
            '.json': self._parse_json,
            '.csv': self._parse_csv,
            '.log': self._parse_log,
            '.txt': self._parse_log
        }

        parser = parsers.get(file_path.suffix)
        if not parser:
            logger.warning(f"Unsupported file type: {file_path}")
            return {}

        try:
            return parser(file_path)
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return {}

    def _parse_json(self, file_path: Path) -> Dict:
        """解析JSON文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 处理不同的JSON格式
        if 'results' in data:
            return self._normalize_results(data['results'])
        else:
            return self._normalize_results(data)

    def _parse_csv(self, file_path: Path) -> Dict:
        """解析CSV文件"""
        df = pd.read_csv(file_path)
        results = {}

        for _, row in df.iterrows():
            model = row.get('model', 'unknown')
            dataset = row.get('dataset', 'unknown')

            if model not in results:
                results[model] = {}
            if dataset not in results[model]:
                results[model][dataset] = {}

            # 提取所有数值列
            for col in df.columns:
                if col not in ['model', 'dataset'] and pd.notna(row[col]):
                    try:
                        results[model][dataset][col] = float(row[col])
                    except ValueError:
                        pass

        return results

    def _parse_log(self, file_path: Path) -> Dict:
        """解析日志文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        results = {}

        # 查找结果表格
        table_pattern = r'[-=]{3,}.*?[-=]{3,}'
        for table in re.findall(table_pattern, content, re.DOTALL):
            results.update(self._parse_table(table))

        # 查找JSON片段
        json_pattern = r'\{[^{}]*"(?:accuracy|score|bleu|rouge)"[^{}]*\}'
        for match in re.findall(json_pattern, content):
            try:
                data = json.loads(match)
                results.update(self._normalize_results(data))
            except:
                pass

        return results

    def _parse_table(self, table_text: str) -> Dict:
        """解析表格文本"""
        lines = table_text.strip().split('\n')
        if len(lines) < 3:
            return {}

        # 查找表头
        header_idx = None
        for i, line in enumerate(lines):
            if '|' in line and any(w in line.lower() for w in ['model', 'dataset', 'accuracy', 'score']):
                header_idx = i
                break

        if header_idx is None:
            return {}

        headers = [h.strip() for h in lines[header_idx].split('|') if h.strip()]
        results = {}

        # 解析数据行
        for line in lines[header_idx + 2:]:
            if '|' not in line:
                continue

            values = [v.strip() for v in line.split('|') if v.strip()]
            if len(values) != len(headers):
                continue

            row = dict(zip(headers, values))
            model = row.get('model', row.get('Model', 'unknown'))
            dataset = row.get('dataset', row.get('Dataset', 'unknown'))

            if model not in results:
                results[model] = {}
            if dataset not in results[model]:
                results[model][dataset] = {}

            # 提取数值
            for key, value in row.items():
                if key.lower() not in ['model', 'dataset']:
                    try:
                        numeric_value = float(value.rstrip('%'))
                        metric_name = self._normalize_metric_name(key)
                        results[model][dataset][metric_name] = numeric_value
                    except:
                        pass

        return results

    def _normalize_results(self, data: Dict) -> Dict:
        """标准化结果格式"""
        if not isinstance(data, dict):
            return {}

        results = {}

        for key, value in data.items():
            if isinstance(value, dict):
                # 可能是 {model: {dataset: metrics}} 格式
                if all(isinstance(v, dict) for v in value.values()):
                    results[key] = {}
                    for dataset, metrics in value.items():
                        if isinstance(metrics, dict):
                            results[key][dataset] = {
                                self._normalize_metric_name(k): v
                                for k, v in metrics.items()
                                if isinstance(v, (int, float))
                            }
                # 可能是 {dataset: metrics} 格式
                else:
                    results['default'] = {key: value}

        return results

    def _normalize_metric_name(self, name: str) -> str:
        """标准化指标名称"""
        name = name.lower().strip()

        for pattern, normalized in self.METRIC_MAPPINGS.items():
            if pattern in name:
                return normalized

        # 默认处理
        return re.sub(r'[^a-z0-9_]', '_', name).strip('_')

    def merge_results(self, result_files: List[Path]) -> Dict:
        """合并多个结果文件"""
        merged = {}

        for file_path in result_files:
            results = self.parse_file(file_path)

            # 深度合并
            for model, model_data in results.items():
                if model not in merged:
                    merged[model] = {}

                if isinstance(model_data, dict):
                    for dataset, metrics in model_data.items():
                        if dataset not in merged[model]:
                            merged[model][dataset] = {}
                        if isinstance(metrics, dict):
                            merged[model][dataset].update(metrics)

        return merged

    def extract_best_scores(self, results: Dict) -> Dict:
        """提取最佳分数"""
        best_scores = {}

        for model, model_data in results.items():
            scores = []
            dataset_scores = {}

            for dataset, metrics in model_data.items():
                if isinstance(metrics, dict):
                    dataset_values = [v for v in metrics.values() if isinstance(v, (int, float))]
                    if dataset_values:
                        avg_score = sum(dataset_values) / len(dataset_values)
                        dataset_scores[dataset] = avg_score
                        scores.append(avg_score)

            best_scores[model] = {
                'overall_score': sum(scores) / len(scores) if scores else 0,
                'dataset_scores': dataset_scores
            }

        return best_scores