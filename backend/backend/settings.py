"""
Django settings for backend project.
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# 添加 openai_api 应用目录定义
OPENAI_API_DIR = os.path.join(BASE_DIR, 'openai_api')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', "django-insecure-9ju!$6r=+qzs!&@ga86$7(x)5h_vx1c9am=afmg&z#w55)%xd_")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 第三方应用
    "rest_framework",
    "corsheaders",
    # 自定义应用
    #"chat",
    "evaluation",
    "openai_api",  # 添加 openai_api 应用
    'subjective'  #主观评测
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "openai_api.middleware.RequestLoggingMiddleware",  # 添加 openai_api 的中间件
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS设置
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-jiutian-url',  # 添加 openai_api 需要的自定义头
]

# REST Framework配置（合并两个项目的配置）
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'EXCEPTION_HANDLER': 'openai_api.exceptions.custom_exception_handler',  # 添加自定义异常处理
}

# 缓存配置
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

# ========== JIUTIAN API Service 配置 ==========
JIUTIAN_CONFIG = {
    'APP_NAME': 'JIUTIAN API Service',
    'APP_VERSION': '1.0.0',
    'API_PREFIX': '/api/v1',
    'REQUEST_TIMEOUT': int(os.environ.get('REQUEST_TIMEOUT', '60')),
    'MAX_RETRIES': int(os.environ.get('MAX_RETRIES', '3')),
    'STREAM_CHUNK_SIZE': int(os.environ.get('STREAM_CHUNK_SIZE', '10')),
    'RATE_LIMIT_ENABLED': os.environ.get('RATE_LIMIT_ENABLED', 'False').lower() == 'true',
    'RATE_LIMIT_REQUESTS': int(os.environ.get('RATE_LIMIT_REQUESTS', '100')),
    'RATE_LIMIT_PERIOD': int(os.environ.get('RATE_LIMIT_PERIOD', '60')),
}

# ========== AI模型配置（合并） ==========
MODEL_CONFIGS = {
    # 魔搭配置
    "modelscope": {
        "base_url": "https://api-inference.modelscope.cn/v1/",
        "api_key": os.environ.get("MODELSCOPE_API_KEY", ""),
        "verify_ssl": True,
        "timeout": 60,
        "default_temperature": 0.7,
        "default_top_p": 0.9,
        "default_max_tokens": 2000
    },

    # 环信配置
    "huanxin": {
        "verify_ssl": False,
        "timeout": 60,
        "models": {
            "huanxin-DeepSeek-R1-32B-Distil": {
                "api_url": os.environ.get("HUANXIN_DEEPSEEK_R1_32B_URL", ""),
                "api_key": os.environ.get("HUANXIN_DEEPSEEK_R1_32B_API_KEY", "")
            },
            "huanxin-DeepSeek-Llama-70B": {
                "api_url": os.environ.get("HUANXIN_DEEPSEEK_LLAMA_70B_URL", ""),
                "api_key": os.environ.get("HUANXIN_DEEPSEEK_LLAMA_70B_API_KEY", "")
            },
        }
    },

    # 豆包API配置
    "doubao_api": {
        "api_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key": os.environ.get("DOUBAO_API_KEY", ""),
        "verify_ssl": False
    },

    # Ollama配置（使用你原有的配置）
    "ollama": {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://172.27.187.5:11434"),
        "timeout": int(os.environ.get("OLLAMA_TIMEOUT", "120")),
        "max_tokens": int(os.environ.get("OLLAMA_MAX_TOKENS", "100000")),
    },

    # Web爬虫配置
    "o43_web": {
        "platform_name": "o43_web",
        "base_url": "https://share.mosha.cloud/",
        "browser_config": {
            "headless": True,
            "timeout": 30000,
            "slow_mo": 100,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-tools",
                "--window-size=1920,1080",
            ]
        }
    },

    "jiutian_web": {
        "platform_name": "jiutian_web",
        "base_url": "https://jiutian.10086.cn/largemodel/playground/#/playground/jiutian-lan",
        "browser_config": {
            "headless": False,
            "timeout": 30000,
            "slow_mo": 100,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-tools",
                "--window-size=1920,1080",
            ]
        }
    },

    "doubao_web": {
        "platform_name": "doubao_web",
        "base_url": "https://www.doubao.com/chat",
        "browser_config": {
            "headless": False,
            "timeout": 30000,
            "slow_mo": 100,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-tools",
                "--window-size=1920,1080",
            ]
        }
    },

    "yuanbao_web": {
        "platform_name": "yuanbao_web",
        "base_url": "https://yuanbao.tencent.com/chat",
        "browser_config": {
            "headless": True,
            "timeout": 30000,
            "slow_mo": 100,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-tools",
                "--window-size=1920,1080",
            ]
        }
    },
}

# 模型响应保存配置
MODEL_RESPONSES_DIR = os.path.join(BASE_DIR, 'test', 'results')
Path(MODEL_RESPONSES_DIR).mkdir(parents=True, exist_ok=True)

# 响应保存相关配置
RESPONSE_SAVER_CONFIG = {
    'base_dir': MODEL_RESPONSES_DIR,
    'max_response_length': 50000,
    'auto_export': True,
    'export_formats': ['json', 'csv'],
    'checkpoint_interval': 10,
}

# 模型路由配置
MODEL_ROUTER_CONFIG = {
    "default_model": "huanxin-DeepSeek-R1-32B-Distil",
    "model_aliases": {
        "deepseek-r1": "huanxin-DeepSeek-R1-32B-Distil",
        "deepseek-llama": "huanxin-DeepSeek-Llama-70B",
        "doubao": "doubao-seed-1-6-250615",
        "doubao-web": "doubao-web",
        "yuanbao": "yuanbao-web",
        "yuanbao-web": "yuanbao-web",
        "jiutian": "jiutian-web",
        "gpt-4o": "o43-web",
        "o43": "o43-web",
        "o43-web": "o43-web",
        "llama3": "ollama-llama3:latest",
        "qwen2": "ollama-qwen2:latest",
        "mistral": "ollama-mistral:latest",
        "codellama": "ollama-codellama:latest",
    },
    "model_limits": {
        "huanxin-DeepSeek-R1-32B-Distil": {"max_tokens": 4096, "rate_limit": 100},
        "huanxin-DeepSeek-Llama-70B": {"max_tokens": 8192, "rate_limit": 50},
        "doubao-seed-1-6-250615": {"max_tokens": 4096, "rate_limit": 200},
        "doubao-web": {"max_tokens": 4096, "rate_limit": 10},
        "yuanbao-web": {"max_tokens": 4096, "rate_limit": 10},
        "jiutian-web": {"max_tokens": 4096, "rate_limit": 10},
        "o43-web": {"max_tokens": 4096, "rate_limit": 10}
    }
}

# Web爬取器配置
WEB_SCRAPER_CONFIG = {
    "state_dir": os.path.join(OPENAI_API_DIR, "browser_states"),
    "state_retention_days": 7,
    "max_retries": 3,
    "retry_delay": 5,
    "max_concurrent_browsers": 5,
    "browser_idle_timeout": 300,
    "use_stealth": True,
    "randomize_viewport": True,
    "randomize_user_agent": True,
    "auto_save_state": True,
    "state_check_interval": 3600,
}

# 创建必要的目录
os.makedirs(WEB_SCRAPER_CONFIG["state_dir"], exist_ok=True)
os.makedirs(os.path.join(OPENAI_API_DIR, "screenshots"), exist_ok=True)

# 模型测试配置
MODEL_TEST_CONFIG = {
    "test_prompts": [
        "你好",
        "1+1等于多少",
        "请用一句话介绍自己"
    ],
    "health_check_interval": 300,
    "quality_benchmarks": {
        "response_time": 10.0,
        "min_response_length": 10,
        "success_rate": 0.95
    }
}

# ========== 原有配置保留 ==========
# OpenCompass配置
USE_OPENCOMPASS = True
OPENCOMPASS_PATH = os.path.join(BASE_DIR, 'evaluation', 'opencompass')

# Ollama配置（保留你的配置）
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://172.27.187.5:11434')
OLLAMA_DEFAULT_MODEL = os.getenv('OLLAMA_DEFAULT_MODEL', 'deepseek-R1:14b')

# DeepSeek API配置（保留你的配置）
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', 'sk-70fb662f54104507a7d513765cde7ada')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_DEFAULT_MODEL = os.getenv('DEEPSEEK_DEFAULT_MODEL', 'deepseek-chat')

# 默认AI提供商
DEFAULT_AI_PROVIDER = os.getenv('DEFAULT_AI_PROVIDER', 'deepseek')

# Celery配置
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SOFT_TIME_LIMIT = 300
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_CONCURRENCY = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50

# 评测相关配置
EVALUATION_CONFIG = {
    'MAX_CONCURRENT_TASKS': 5,
    'TASK_TIMEOUT': 3600,
    'RESULT_RETENTION_DAYS': 90,
    'enable_monitoring': True,
    'monitor_cache_timeout': 300,
    'enable_logging': True,
    'log_sample_details': True,
    'max_log_samples': 1000,
    'batch_size': 1,
    'timeout': 60,
    'retry_times': 3,
    'progress_update_interval': 10,
}

EVALUATION_LOG_DIR = BASE_DIR / 'evaluation_logs'
EVALUATION_LOG_DIR.mkdir(exist_ok=True)

# 创建日志目录
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# 日志配置（合并两个项目的配置）
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'evaluation_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/evaluation.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'openai_api_file': {  # 添加 openai_api 的日志文件
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'openai_api.log'),
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'chat': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'evaluation': {
            'handlers': ['evaluation_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'openai_api': {  # 添加 openai_api 的日志配置
            'handlers': ['console', 'openai_api_file'],
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'openai_api.api.adapters': {  # 添加适配器的详细日志
            'handlers': ['console', 'openai_api_file'],
            'level': os.environ.get('ADAPTER_LOG_LEVEL', 'DEBUG'),
            'propagate': False,
        },
    },
}

# 测试环境检测
import sys
TESTING = 'test' in sys.argv or os.environ.get('TESTING')

if TESTING:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    CELERY_ALWAYS_EAGER = True
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True

# 添加GZip中间件
MIDDLEWARE.insert(0, 'django.middleware.gzip.GZipMiddleware')

# 打印调试信息
if DEBUG:
    print(f"[Settings] BASE_DIR: {BASE_DIR}")
    print(f"[Settings] OPENAI_API_DIR: {OPENAI_API_DIR}")
    print(f"[Settings] State directory: {WEB_SCRAPER_CONFIG['state_dir']}")
    print(f"[Settings] openai_api app integrated successfully!")