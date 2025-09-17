# backend/openai_api/exceptions.py
"""
Custom exception classes and exception handler for Django
"""
from typing import Optional, Any
from rest_framework import status
from rest_framework.views import exception_handler
from rest_framework.response import Response
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404


class JiutianAPIException(Exception):
    """JIUTIAN API base exception"""

    def __init__(self, message: str, status_code: int = 500, error_type: str = "internal_error"):
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        super().__init__(self.message)


class InvalidRequestError(JiutianAPIException):
    """Invalid request error"""

    def __init__(self, message: str = "Invalid request"):
        super().__init__(message, status_code=400, error_type="invalid_request_error")


class RateLimitError(JiutianAPIException):
    """Rate limit error"""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429, error_type="rate_limit_error")


class UpstreamAPIError(JiutianAPIException):
    """Upstream API error"""

    def __init__(self, message: str = "Upstream API error", details: Optional[Any] = None):
        super().__init__(message, status_code=502, error_type="upstream_error")
        self.details = details


class TimeoutError(JiutianAPIException):
    """Timeout error"""

    def __init__(self, message: str = "Request timeout"):
        super().__init__(message, status_code=504, error_type="timeout_error")


class ConfigurationError(JiutianAPIException):
    """Configuration error"""

    def __init__(self, message: str = "Configuration error"):
        super().__init__(message, status_code=500, error_type="configuration_error")


def format_error_response(error: Exception) -> dict:
    """
    Format error response in OpenAI API format

    Args:
        error: Exception object

    Returns:
        dict: Error response dictionary
    """
    if isinstance(error, JiutianAPIException):
        return {
            "error": {
                "message": error.message,
                "type": error.error_type,
                "code": error.status_code
            }
        }

    # Default error format
    return {
        "error": {
            "message": str(error),
            "type": "internal_error",
            "code": 500
        }
    }


def custom_exception_handler(exc, context):
    """
    Custom exception handler for Django REST Framework

    This handler formats all exceptions to match OpenAI API error format
    """
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # Handle Django's built-in Http404
    if isinstance(exc, Http404):
        exc = ObjectDoesNotExist(str(exc))

    # Handle custom exceptions
    if isinstance(exc, JiutianAPIException):
        response = Response(
            format_error_response(exc),
            status=exc.status_code
        )
    elif isinstance(exc, ObjectDoesNotExist):
        response = Response(
            {
                "error": {
                    "message": "Resource not found",
                    "type": "not_found",
                    "code": 404
                }
            },
            status=status.HTTP_404_NOT_FOUND
        )
    elif response is not None:
        # Format DRF exceptions to match OpenAI format
        error_message = "Bad request"
        if hasattr(response, 'data'):
            if isinstance(response.data, dict):
                # Extract error message from various formats
                if 'detail' in response.data:
                    error_message = str(response.data['detail'])
                elif 'non_field_errors' in response.data:
                    error_message = ' '.join(response.data['non_field_errors'])
                else:
                    # Combine all field errors
                    errors = []
                    for field, messages in response.data.items():
                        if isinstance(messages, list):
                            errors.extend([f"{field}: {msg}" for msg in messages])
                        else:
                            errors.append(f"{field}: {messages}")
                    if errors:
                        error_message = '; '.join(errors)

        response.data = {
            "error": {
                "message": error_message,
                "type": "invalid_request_error",
                "code": response.status_code
            }
        }
    else:
        # Handle unexpected exceptions
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error: {exc}", exc_info=True)

        response = Response(
            {
                "error": {
                    "message": "Internal server error",
                    "type": "internal_error",
                    "code": 500
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response