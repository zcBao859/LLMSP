import os
import sys
from pathlib import Path

# 获取当前脚本所在目录
current_dir = Path(__file__).parent.absolute()
evaluation_dir = current_dir

# 确保 evaluation 目录在 Python 路径中
# 这样 opencompass 可以作为包被正确导入
if str(evaluation_dir) not in sys.path:
    sys.path.insert(0, str(evaluation_dir))

# 如果是从服务运行的，打印调试信息
if os.environ.get('OPENCOMPASS_RUN_FROM_SERVICE'):
    print(f"Running from service...")
    print(f"Current directory: {os.getcwd()}")
    print(f"Script directory: {current_dir}")
    print(f"Python path: {sys.path[:3]}...")  # 只打印前3个

    # 如果设置了 OPENCOMPASS_ROOT，使用它
    if 'OPENCOMPASS_ROOT' in os.environ:
        opencompass_root = Path(os.environ['OPENCOMPASS_ROOT'])
        print(f"OPENCOMPASS_ROOT: {opencompass_root}")

        # 确保 configs 目录存在
        configs_dir = opencompass_root / 'configs'
        if configs_dir.exists():
            print(f"Configs directory found: {configs_dir}")
        else:
            print(f"WARNING: Configs directory not found: {configs_dir}")

# 导入并运行 OpenCompass
try:
    from opencompass.cli.main import main

    if __name__ == '__main__':
        # 运行 main 函数
        main()

except ImportError as e:
    print(f"Error importing OpenCompass: {e}")
    print(f"Current Python path:")
    for i, p in enumerate(sys.path):
        print(f"  {i}: {p}")

    # 尝试查找 opencompass 包
    opencompass_path = evaluation_dir / 'opencompass'
    if opencompass_path.exists():
        print(f"\nOpenCompass directory found at: {opencompass_path}")
        print("Directory contents:")
        for item in opencompass_path.iterdir():
            if item.is_dir():
                print(f"  [DIR] {item.name}")
            else:
                print(f"  [FILE] {item.name}")

        # 检查 cli 目录
        cli_path = opencompass_path / 'cli'
        if cli_path.exists():
            print(f"\nCLI directory found at: {cli_path}")
            if (cli_path / 'main.py').exists():
                print("  main.py exists")
            else:
                print("  WARNING: main.py not found in cli directory")
    else:
        print(f"\nERROR: OpenCompass directory not found at: {opencompass_path}")

    raise