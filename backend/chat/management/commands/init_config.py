from django.core.management.base import BaseCommand
from django.conf import settings
from chat.models import SystemConfig


class Command(BaseCommand):
    help = '初始化系统配置'

    def handle(self, *args, **options):
        # 初始化Ollama配置
        SystemConfig.set_config(
            'ollama_base_url',
            getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
            'Ollama服务地址'
        )

        SystemConfig.set_config(
            'ollama_default_model',
            getattr(settings, 'OLLAMA_DEFAULT_MODEL', 'llama2'),
            'Ollama默认模型'
        )

        # 初始化DeepSeek配置
        SystemConfig.set_config(
            'deepseek_api_key',
            getattr(settings, 'DEEPSEEK_API_KEY', ''),
            'DeepSeek API密钥'
        )

        SystemConfig.set_config(
            'deepseek_base_url',
            getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
            'DeepSeek API地址'
        )

        SystemConfig.set_config(
            'deepseek_default_model',
            getattr(settings, 'DEEPSEEK_DEFAULT_MODEL', 'deepseek-chat'),
            'DeepSeek默认模型'
        )

        # 设置默认提供商
        SystemConfig.set_config(
            'default_provider',
            getattr(settings, 'DEFAULT_AI_PROVIDER', 'ollama'),
            '默认AI服务提供商'
        )

        self.stdout.write(self.style.SUCCESS('系统配置初始化完成'))

        # 显示配置状态
        self.stdout.write('\n当前配置:')
        self.stdout.write(f'- Ollama地址: {SystemConfig.get_config("ollama_base_url")}')
        self.stdout.write(f'- Ollama默认模型: {SystemConfig.get_config("ollama_default_model")}')
        self.stdout.write(f'- DeepSeek API地址: {SystemConfig.get_config("deepseek_base_url")}')
        self.stdout.write(f'- DeepSeek默认模型: {SystemConfig.get_config("deepseek_default_model")}')
        self.stdout.write(f'- 默认提供商: {SystemConfig.get_config("default_provider")}')

        api_key = SystemConfig.get_config("deepseek_api_key")
        if api_key:
            self.stdout.write(f'- DeepSeek API密钥: 已配置 ({api_key[:8]}...)')
        else:
            self.stdout.write(self.style.WARNING('- DeepSeek API密钥: 未配置'))