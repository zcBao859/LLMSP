# evaluation/constants.py
"""评测系统常量定义"""

# 任务状态
TASK_STATUS = {
    'PENDING': 'pending',
    'RUNNING': 'running',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'CANCELLED': 'cancelled'
}

# 数据集类别
DATASET_CATEGORIES = [
    ('safety', '安全性'),
    ('bias', '偏见'),
    ('toxicity', '毒性'),
    ('privacy', '隐私'),
    ('robustness', '鲁棒性'),
    ('ethics', '伦理'),
    ('factuality', '事实性'),
    ('custom', '自定义'),
]

# 文件类型
ALLOWED_DATASET_EXTENSIONS = ['.json', '.jsonl', '.csv']
ALLOWED_CONFIG_EXTENSIONS = ['.py']

# 工具脚本名称
TOOLS = {
    'CASE_ANALYZER': 'case_analyzer.py',
    'PREDICTION_MERGER': 'prediction_merger.py',
    'CODE_COLLECTOR': 'collect_code_preds.py',
    'MODEL_COMPARATOR': 'viz_multi_model.py',
    'PROMPT_VIEWER': 'prompt_viewer.py',
    'API_TESTER': 'test_api_model.py',
    'CONFIG_LISTER': 'list_configs.py',
    'ALIGNMENT_CONVERTER': 'convert_alignmentbench.py'
}

# 默认限制
DEFAULT_LIMITS = {
    'MAX_BAD_CASES': 100,
    'MAX_PROMPT_COUNT': 10,
    'MIN_COMPARE_TASKS': 2,
    'LOG_TAIL_LINES': 100,
    'PREVIEW_SAMPLES': 10
}

# 缓存超时（秒）
CACHE_TIMEOUT = {
    'TASK_PROGRESS': 300,    # 5分钟
    'CONFIG_LIST': 3600,     # 1小时
    'CELERY_TASK': 86400     # 24小时
}