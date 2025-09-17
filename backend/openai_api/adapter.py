# backend/openai_api/adapter.py
"""
JIUTIAN API Adapter for Django
"""
import json
import logging
from typing import Iterator, Dict, Any, List, Optional, Union
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings

from .exceptions import UpstreamAPIError, TimeoutError
from .utils import generate_completion_id, get_current_timestamp, calculate_tokens


logger = logging.getLogger(__name__)


@dataclass
class ChatCompletion:
    """Internal chat completion object"""
    id: str = field(default_factory=generate_completion_id)
    object: str = "chat.completion"
    created: int = field(default_factory=get_current_timestamp)
    model: str = "jiutian-model"
    choices: List[Dict] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)


class JiutianAdapter:
    """JIUTIAN API to OpenAI Protocol Adapter"""
    
    def __init__(self, base_url: str, api_key: str):
        """
        Initialize adapter
        
        Args:
            base_url: JIUTIAN API URL
            api_key: JIUTIAN API Key (should include Bearer prefix)
        """
        self.base_url = base_url
        self.api_key = api_key
        self._setup_session()
    
    def _setup_session(self):
        """Setup HTTP session"""
        self.session = requests.Session()
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=settings.JIUTIAN_CONFIG['MAX_RETRIES'],
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": f"{settings.JIUTIAN_CONFIG['APP_NAME']}/{settings.JIUTIAN_CONFIG['APP_VERSION']}"
        })
    
    def create(
            self,
            messages: List[Dict[str, str]],
            model: str = "jiutian-model",
            stream: bool = False,
            **kwargs  # Accept all other parameters
    ) -> Union[ChatCompletion, Iterator[Dict]]:
        """
        Create chat completion - only pass user-provided parameters
        """
        logger.info(f"Creating chat completion: model={model}, stream={stream}")
        
        # Format messages
        prompt = self._format_messages(messages)
        logger.debug(f"Formatted prompt: {prompt[:100]}...")
        
        if stream:
            return self._stream_response(prompt, model, **kwargs)
        return self._create_response(prompt, model, **kwargs)
    
    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """
        Convert OpenAI format messages to JIUTIAN format
        
        Args:
            messages: OpenAI format message list
            
        Returns:
            str: JIUTIAN format prompt
        """
        # Log original messages
        logger.info("========== Original Messages from User ==========")
        logger.info(json.dumps(messages, ensure_ascii=False, indent=2))
        logger.info("================================================")
        
        parts = []
        role_map = {"system": "系统", "user": "用户", "assistant": "助手"}
        
        # Check if there's a system message
        has_system = any(msg["role"] == "system" for msg in messages)
        
        # Add default if no system message
        if not has_system:
            parts.append("系统: 你是一个有帮助的助手")
        
        # Convert messages
        for msg in messages:
            role = role_map.get(msg["role"], msg["role"])
            content = msg["content"].strip()
            if content:
                parts.append(f"{role}: {content}")
        
        formatted_prompt = "\n".join(parts)
        
        # Log formatted prompt
        logger.info("========== Formatted Prompt for JIUTIAN ==========")
        logger.info(formatted_prompt)
        logger.info("==================================================")
        
        return formatted_prompt
    
    def _call_api(self, prompt: str, **params) -> Dict[str, Any]:
        """
        Call JIUTIAN API
        
        Only send explicitly provided parameters, no default values
        """
        # Base data structure with only required prompt
        data = {
            "prompt": prompt
        }
        
        # Only add parameters that were passed in
        for key, value in params.items():
            if value is not None:  # Only add non-None values
                data[key] = value
        
        # Log request data
        logger.info("========== Request Data to JIUTIAN API ==========")
        logger.info(f"URL: {self.base_url}")
        logger.info(f"Headers: {dict(self.session.headers)}")
        logger.info("Request Body:")
        logger.info(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("=================================================")
        
        try:
            logger.debug(f"Calling JIUTIAN API: {self.base_url}")
            response = self.session.post(
                self.base_url,
                json=data,
                timeout=settings.JIUTIAN_CONFIG['REQUEST_TIMEOUT']
            )
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"API response received: {len(str(result))} bytes")
            
            # Log raw API response
            logger.info("========== JIUTIAN API Raw Response ==========")
            logger.info(json.dumps(result, ensure_ascii=False, indent=2))
            logger.info("==============================================")
            
            return result
            
        except requests.exceptions.Timeout:
            logger.error("JIUTIAN API request timeout")
            raise TimeoutError("JIUTIAN API request timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"JIUTIAN API request failed: {e}")
            raise UpstreamAPIError(f"Failed to call JIUTIAN API: {str(e)}", details=str(e))
    
    def _extract_text(self, response: Dict) -> str:
        """
        Extract text from JIUTIAN response
        
        Args:
            response: JIUTIAN API response
            
        Returns:
            str: Extracted text content
        """
        # Main extraction logic
        if "text" in response and isinstance(response["text"], list):
            text = response["text"][0] if response["text"] else ""
            
            # Handle special tags
            if "</think>" in text:
                text = text.split("</think>", 1)[1].strip()
            
            # Extract actual reply (remove role markers)
            lines = text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                # Skip role marker lines
                if line.startswith(("系统:", "用户:", "助手:")):
                    continue
                cleaned_lines.append(line)
            
            result = '\n'.join(cleaned_lines).strip()
            if result:
                # Log extracted text
                logger.info("========== Extracted Model Reply ==========")
                logger.info(f"Extracted text: {result}")
                logger.info("==========================================")
                return result
            
            # If cleaned result is empty, return original text
            logger.info("========== Extracted Model Reply (Original) ==========")
            logger.info(f"Original text (cleaned result empty): {text.strip()}")
            logger.info("======================================================")
            return text.strip()
        
        # Alternative extraction strategies
        for field in ["response", "result", "output", "content", "completion"]:
            if field in response:
                value = response[field]
                if isinstance(value, str):
                    logger.info(f"========== Extracted Model Reply (from field: {field}) ==========")
                    logger.info(f"Extracted text: {value}")
                    logger.info("==================================================================")
                    return value
                elif isinstance(value, list) and value:
                    extracted = str(value[0])
                    logger.info(f"========== Extracted Model Reply (from field: {field}) ==========")
                    logger.info(f"Extracted text: {extracted}")
                    logger.info("==================================================================")
                    return extracted
        
        # If unable to extract, return JSON string
        logger.warning("Unable to extract text from response, returning JSON")
        json_str = json.dumps(response, ensure_ascii=False, indent=2)
        logger.info("========== Model Reply (Full JSON) ==========")
        logger.info(json_str)
        logger.info("=============================================")
        return json_str
    
    def _create_response(
            self,
            prompt: str,
            model: str,
            **kwargs  # Accept all parameters
    ) -> ChatCompletion:
        """
        Create non-streaming response
        
        Only pass user-provided parameters
        """
        # Call API - pass all kwargs directly
        api_response = self._call_api(prompt, **kwargs)
        
        # Extract content
        content = self._extract_text(api_response)
        
        # Calculate token usage
        prompt_tokens = calculate_tokens(prompt)
        completion_tokens = calculate_tokens(content)
        
        # Create response object
        completion = ChatCompletion(
            model=model,
            choices=[{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        )
        
        return completion
    
    def _stream_response(
            self,
            prompt: str,
            model: str,
            **kwargs  # Accept all parameters
    ) -> Iterator[Dict]:
        """Create streaming response"""
        completion_id = generate_completion_id()
        created = get_current_timestamp()
        
        # Initial chunk
        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }]
        }
        
        try:
            # Call API - pass all kwargs directly
            api_response = self._call_api(prompt, **kwargs)
            content = self._extract_text(api_response)
            
            # Output in chunks
            chunk_size = settings.JIUTIAN_CONFIG['STREAM_CHUNK_SIZE']
            for i in range(0, len(content), chunk_size):
                chunk_content = content[i:i + chunk_size]
                yield {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk_content},
                        "finish_reason": None
                    }]
                }
            
            # End chunk
            yield {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "error"
                }],
                "error": str(e)
            }