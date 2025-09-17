"""
DeepSeek 高级安全评测配置 - OpenAI API 版本
综合多个维度的安全测试
"""

from mmengine.config import read_base
from opencompass.partitioners import NaivePartitioner, SizePartitioner
from opencompass.runners import LocalRunner
from opencompass.tasks import OpenICLInferTask, OpenICLEvalTask
from opencompass.models import OpenAI

# ======================= 数据集配置 =======================
# 导入所有相关数据集
with read_base():
    # 1. 真实性评测
    from opencompass.configs.datasets.truthfulqa.truthfulqa_gen_5ddc62 import truthfulqa_datasets

    # 2. 数学推理（基准）
    from opencompass.configs.datasets.gsm8k.gsm8k_gen_1d7fe4 import gsm8k_datasets

    # 3. 代码安全
    from opencompass.configs.datasets.humaneval.humaneval_gen_8e312c import humaneval_datasets

    # 4. 通识问答
    from opencompass.configs.datasets.mmlu.mmlu_gen_4d595a import mmlu_datasets

    # 5. 中文理解（如果需要）
    from opencompass.configs.datasets.ceval.ceval_gen_5f30c7 import ceval_datasets

# 处理数据集
datasets = []

# TruthfulQA - 真实性测试（重要的安全指标）
datasets.extend(truthfulqa_datasets)

# GSM8K - 限制样本数
for ds in gsm8k_datasets:
    if 'reader_cfg' not in ds:
        ds['reader_cfg'] = {}
    ds['reader_cfg']['test_range'] = '[0:100]'
    datasets.append(ds)

# HumanEval - 代码生成安全性
datasets.extend(humaneval_datasets)

# MMLU - 选择与安全相关的子集
safety_related_mmlu = []
for ds in mmlu_datasets:
    # 筛选出与伦理、法律、医学相关的子集
    if any(keyword in ds.get('abbr', '').lower()
           for keyword in ['ethics', 'law', 'medical', 'moral', 'philosophy']):
        if 'reader_cfg' not in ds:
            ds['reader_cfg'] = {}
        ds['reader_cfg']['test_range'] = '[0:30]'
        safety_related_mmlu.append(ds)

# 如果没有找到特定子集，就使用前几个MMLU数据集
if not safety_related_mmlu:
    for i, ds in enumerate(mmlu_datasets[:3]):
        if 'reader_cfg' not in ds:
            ds['reader_cfg'] = {}
        ds['reader_cfg']['test_range'] = '[0:30]'
        datasets.append(ds)
else:
    datasets.extend(safety_related_mmlu)

# C-Eval - 中文场景（限制样本）
for i, ds in enumerate(ceval_datasets[:2]):  # 只取前2个子集
    if 'reader_cfg' not in ds:
        ds['reader_cfg'] = {}
    ds['reader_cfg']['test_range'] = '[0:20]'
    datasets.append(ds)

# ======================= 模型配置 =======================
# 使用 OpenAI 接口配置，通过您的 model_router 路由到不同的模型

models = [
    # 配置5：如果您有环信的 DeepSeek 模型
    dict(
        type=OpenAI,
        path='huanxin-deepseek',  # 假设环信适配器中配置了 deepseek
        openai_api_base='http://localhost:8000/api/v1',
        key='not-needed',
        max_seq_len=8192,
        max_out_len=512,
        abbr='DeepSeek-HuanXin',
        run_cfg=dict(num_gpus=0),
        batch_size=1,
        temperature=0.7,
        retry=3,
    )
]
# 如果您只想测试某个特定模型，可以只保留一个配置
# 例如，只测试 DeepSeek 模型：
# models = [
#     dict(
#         type=OpenAI,
#         path='modelscope-deepseek-ai/DeepSeek-R1-Distill-Qwen-32B',
#         openai_api_base='http://localhost:8000/v1',
#         key='YOUR_API_KEY',
#         max_seq_len=8192,
#         max_out_len=512,
#         abbr='DeepSeek-R1',
#         run_cfg=dict(num_gpus=0),
#         batch_size=1,
#         temperature=0.7,
#         retry=3,
#     ),
# ]

# ======================= 推理配置 =======================
# 使用SizePartitioner更好地分配任务
infer = dict(
    partitioner=dict(
        type=SizePartitioner,
        max_task_size=200,  # 每个任务最多200个样本
    ),
    runner=dict(
        type=LocalRunner,
        max_num_workers=4,
        task=dict(type=OpenICLInferTask),
    ),
)

# ======================= 评估配置 =======================
eval = dict(
    partitioner=dict(type=NaivePartitioner, n=1),
    runner=dict(
        type=LocalRunner,
        max_num_workers=4,
        task=dict(type=OpenICLEvalTask)
    ),
)

# ======================= 汇总配置 =======================
# 定义核心安全指标
core_safety_groups = [
    {
        'name': 'safety_score',
        'subsets': [
            ['truthfulqa', 'accuracy'],  # 真实性
            ['mmlu', 'accuracy'],  # 知识准确性
        ],
    },
    {
        'name': 'capability_score',
        'subsets': [
            ['gsm8k', 'accuracy'],  # 数学能力
            ['openai_humaneval', 'humaneval_pass@1'],  # 代码能力
            ['ceval', 'accuracy'],  # 中文理解
        ],
    },
]

summarizer = dict(
    dataset_abbrs=[
        '=' * 60,
        'DeepSeek 高级安全评测报告',
        '=' * 60,
        '',
        '## 综合评分',
        ['safety_score', 'naive_average'],
        ['capability_score', 'naive_average'],
        '',
        '## 安全性指标',
        '',
        '### 1. 真实性与诚实度',
        ['truthfulqa', 'accuracy'],
        '- 评估模型是否会产生虚假或误导性信息',
        '',
        '### 2. 知识准确性',
        ['mmlu', 'accuracy'],
        '- 评估模型在各领域知识的准确性',
        '',
        '## 能力基准',
        '',
        '### 3. 数学推理',
        ['gsm8k', 'accuracy'],
        '',
        '### 4. 代码生成',
        ['openai_humaneval', 'humaneval_pass@1'],
        '- 评估生成代码的安全性和正确性',
        '',
        '### 5. 中文理解',
        ['ceval', 'accuracy'],
        '',
        '=' * 60,
        '说明：',
        '- 真实性得分越高，表示模型越不容易产生虚假信息',
        '- 各项能力得分用于建立安全评估的基准',
        '=' * 60,
    ],
    summary_groups=core_safety_groups,
)

# ======================= 工作目录 =======================
work_dir = './evaluation/outputs/deepseek_advanced_safety_eval/'