from django.core.management.base import BaseCommand
from django.conf import settings
from chat.models import SystemConfig
from chat.ollama_service import OllamaService
from chat.deepseek_service import DeepSeekService
import json


class Command(BaseCommand):
    help = '测试AI服务连接'

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            type=str,
            choices=['ollama', 'deepseek', 'all'],
            default='all',
            help='要测试的AI服务提供商'
        )
        parser.add_argument(
            '--message',
            type=str,
            default='你好，请简单介绍一下你自己。',
            help='测试消息'
        )

    def handle(self, *args, **options):
        provider = options['provider']
        test_message = options['message']

        if provider in ['ollama', 'all']:
            self.test_ollama(test_message)

        if provider in ['deepseek', 'all']:
            self.test_deepseek(test_message)

    def test_ollama(self, message):
        """测试Ollama服务"""
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write('测试 Ollama 服务...')
        self.stdout.write('=' * 50)

        try:
            service = OllamaService()
            self.stdout.write(f'Ollama URL: {service.base_url}')
            self.stdout.write(f'默认模型: {service.default_model}')

            # 健康检查
            self.stdout.write('\n1. 健康检查...')
            if service.check_health():
                self.stdout.write(self.style.SUCCESS('✓ Ollama服务正常'))
            else:
                self.stdout.write(self.style.ERROR('✗ Ollama服务不可用'))
                return

            # 获取模型列表
            self.stdout.write('\n2. 获取可用模型...')
            models = service.list_models()
            if models:
                self.stdout.write(f'可用模型数量: {len(models)}')
                for model in models[:5]:  # 只显示前5个
                    self.stdout.write(f'  - {model.get("name", "unknown")}')
                if len(models) > 5:
                    self.stdout.write(f'  ... 还有 {len(models) - 5} 个模型')
            else:
                self.stdout.write(self.style.WARNING('没有找到可用模型'))

            # 测试对话
            self.stdout.write(f'\n3. 测试对话功能...')
            self.stdout.write(f'发送消息: {message}')

            response = service.chat([
                {"role": "user", "content": message}
            ])

            if 'message' in response:
                content = response['message']['content']
                self.stdout.write(self.style.SUCCESS('\n✓ 对话测试成功！'))
                self.stdout.write(f'\nAI回复:\n{content[:200]}...' if len(content) > 200 else f'\nAI回复:\n{content}')
            else:
                self.stdout.write(self.style.ERROR('✗ 未收到有效回复'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Ollama测试失败: {str(e)}'))

    def test_deepseek(self, message):
        """测试DeepSeek服务"""
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write('测试 DeepSeek 服务...')
        self.stdout.write('=' * 50)

        try:
            service = DeepSeekService()
            self.stdout.write(f'DeepSeek URL: {service.base_url}')
            self.stdout.write(f'默认模型: {service.default_model}')

            if service.api_key:
                self.stdout.write(f'API密钥: {service.api_key[:8]}...')
            else:
                self.stdout.write(self.style.WARNING('API密钥未配置'))
                self.stdout.write('请设置 DEEPSEEK_API_KEY 环境变量或通过管理界面配置')
                return

            # 健康检查
            self.stdout.write('\n1. 健康检查...')
            if service.check_health():
                self.stdout.write(self.style.SUCCESS('✓ DeepSeek API正常'))
            else:
                self.stdout.write(self.style.ERROR('✗ DeepSeek API不可用'))
                return

            # 显示可用模型
            self.stdout.write('\n2. 可用模型:')
            models = service.list_models()
            for model in models:
                self.stdout.write(f'  - {model["name"]}: {model["description"]}')

            # 测试对话
            self.stdout.write(f'\n3. 测试对话功能...')
            self.stdout.write(f'发送消息: {message}')

            response = service.chat([
                {"role": "user", "content": message}
            ])

            if 'message' in response:
                content = response['message']['content']
                self.stdout.write(self.style.SUCCESS('\n✓ 对话测试成功！'))
                self.stdout.write(f'\nAI回复:\n{content[:200]}...' if len(content) > 200 else f'\nAI回复:\n{content}')

                # 显示token使用情况
                if response.get('usage'):
                    usage = response['usage']
                    self.stdout.write(f'\nToken使用:')
                    self.stdout.write(f'  - 输入: {usage.get("prompt_tokens", 0)}')
                    self.stdout.write(f'  - 输出: {usage.get("completion_tokens", 0)}')
                    self.stdout.write(f'  - 总计: {usage.get("total_tokens", 0)}')
            else:
                self.stdout.write(self.style.ERROR('✗ 未收到有效回复'))

            # 测试流式响应
            self.stdout.write('\n4. 测试流式响应...')
            stream_response = service.chat(
                [{"role": "user", "content": "数到5"}],
                stream=True
            )

            self.stdout.write('流式输出: ', ending='')
            for chunk in stream_response:
                if 'message' in chunk and 'content' in chunk['message']:
                    self.stdout.write(chunk['message']['content'], ending='')
                if chunk.get('done'):
                    break

            self.stdout.write(self.style.SUCCESS('\n\n✓ 流式响应测试成功！'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ DeepSeek测试失败: {str(e)}'))