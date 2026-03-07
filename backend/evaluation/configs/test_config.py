from opencompass.configs import datasets
from opencompass.configs.models import huggingface as hf_models
from opencompass.partitioners import NaivePartitioner
from opencompass.runners import LocalRunner
from opencompass.tasks import OpenICLInferTask

# 数据集配置
datasets = [
    # 简单的测试数据集
    {
        'path': 'json',
        'data_files': [{'path': 'test_data.json'}],  # 需要创建这个文件
        'type': 'test',
        'name': 'test_dataset',
    }
]

# 模型配置
models = [
    {
        'type': 'huggingface',
        'path': 'gpt2',  # 使用小模型快速测试
        'model_kwargs': {
            'device_map': 'auto',
            'torch_dtype': 'float16'
        }
    }
]

# 评测配置
work_dir = 'outputs/test_eval'
infer_cfg = dict(
    partitioner=dict(
        type=NaivePartitioner,
        max_num_samples=10  # 只测试10个样本
    ),
    runner=dict(
        type=LocalRunner,
        max_num_workers=1,
        task=dict(
            type=OpenICLInferTask
        )
    )
)
