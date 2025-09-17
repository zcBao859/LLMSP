# backend/openai_api/middleware.py
"""
Custom middleware for the JIUTIAN API Service
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponse

logger = logging.getLogger(__name__)

# evaluation/middleware.py
import logging
import json
import traceback

logger = logging.getLogger(__name__)



class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all incoming requests and outgoing responses
    """
    
    def process_request(self, request):
        """Log incoming request"""
        request._start_time = time.time()
        logger.info(f"Request: {request.method} {request.path}")
        return None
    
    def process_response(self, request, response):
        """Log outgoing response"""
        if hasattr(request, '_start_time'):
            process_time = time.time() - request._start_time
            logger.info(
                f"Response: {request.method} {request.path} - "
                f"Status: {response.status_code} - Time: {process_time:.3f}s"
            )
            
            # Add process time header
            response['X-Process-Time'] = str(process_time)
        
        return response