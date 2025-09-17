# evaluation/middleware.py
import logging
import json
import traceback

logger = logging.getLogger(__name__)


class DebugRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 只对特定路径进行详细记录
        if request.path in ['/v1', '/api/v1/', '/v1/', '/api/v1']:
            logger.warning("=" * 60)
            logger.warning(f"🔍 MYSTERIOUS REQUEST DETECTED!")
            logger.warning(f"Path: {request.path}")
            logger.warning(f"Method: {request.method}")
            logger.warning(f"Time: {request.META.get('REQUEST_TIME', 'Unknown')}")

            # 记录所有请求头
            logger.warning("Headers:")
            for header, value in request.headers.items():
                logger.warning(f"  {header}: {value}")

            # 记录客户端信息
            logger.warning(f"Client IP: {self.get_client_ip(request)}")
            logger.warning(f"User Agent: {request.META.get('HTTP_USER_AGENT', 'None')}")
            logger.warning(f"Referer: {request.META.get('HTTP_REFERER', 'None')}")

            # 如果是 POST 请求，尝试记录请求体
            if request.method == 'POST':
                try:
                    body = request.body.decode('utf-8')[:1000]
                    logger.warning(f"Body (first 1000 chars): {body}")
                except:
                    logger.warning("Could not decode body")

            # 记录调用栈
            logger.warning("Call Stack:")
            for line in traceback.format_stack()[:5]:
                logger.warning(line.strip())

            logger.warning("=" * 60)

        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip