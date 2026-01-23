"""
Token Usage Extractor

Accurately extracts token usage from different API response formats.
Handles OpenAI, Anthropic, and Gemini responses.
"""

import logging
from typing import Dict, Optional, Any


logger = logging.getLogger(__name__)


class UsageExtractor:
    """Extract token usage from various API response formats"""
    
    @staticmethod
    def extract_openai_usage(response: Any) -> Optional[Dict[str, int]]:
        """
        Extract token usage from OpenAI API response.
        
        OpenAI Responses API returns:
        {
            "id": "response_id",
            "output": [...],
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 456,
                "total_tokens": 579,
                "cached_tokens": 0  # if available
            }
        }
        
        Or for regular Chat Completions API:
        {
            "id": "chatcmpl-123",
            "choices": [...],
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 456,
                "total_tokens": 579
            }
        }
        """
        try:
            # Case 1: Response is a dict with 'usage' key
            if isinstance(response, dict) and 'usage' in response:
                usage = response['usage']
                return {
                    'input_tokens': usage.get('prompt_tokens', 0),
                    'output_tokens': usage.get('completion_tokens', 0),
                    'total_tokens': usage.get('total_tokens', 0),
                    'cached_tokens': usage.get('cached_tokens', 0),
                    'api_calls_count': 1
                }
            
            # Case 2: Response is an object with 'usage' attribute
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                # Handle dict-like usage
                if isinstance(usage, dict):
                    input_tokens = usage.get('prompt_tokens', 0)
                    output_tokens = usage.get('completion_tokens', 0)
                # Handle object-like usage
                else:
                    input_tokens = getattr(usage, 'prompt_tokens', 0)
                    output_tokens = getattr(usage, 'completion_tokens', 0)
                    
                return {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                    'cached_tokens': getattr(usage, 'cached_tokens', 0) if not isinstance(usage, dict) else usage.get('cached_tokens', 0),
                    'api_calls_count': 1
                }
            
            logger.warning("No usage information found in OpenAI response")
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract OpenAI usage: {e}")
            return None
    
    @staticmethod
    def extract_anthropic_usage(response: Any) -> Optional[Dict[str, int]]:
        """
        Extract token usage from Anthropic API response.
        
        Anthropic Messages API returns:
        {
            "id": "msg_123",
            "content": [...],
            "usage": {
                "input_tokens": 123,
                "output_tokens": 456,
                "cache_creation_input_tokens": 10,  # if using prompt caching
                "cache_read_input_tokens": 100      # if using prompt caching
            }
        }
        """
        try:
            # Case 1: Response is a dict with 'usage' key
            if isinstance(response, dict) and 'usage' in response:
                usage = response['usage']
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cache_creation = usage.get('cache_creation_input_tokens', 0)
                cache_read = usage.get('cache_read_input_tokens', 0)
                
                return {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                    'cached_tokens': cache_creation + cache_read,
                    'api_calls_count': 1
                }
            
            # Case 2: Response is an object with 'usage' attribute
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                
                # Handle dict-like usage
                if isinstance(usage, dict):
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    cache_creation = usage.get('cache_creation_input_tokens', 0)
                    cache_read = usage.get('cache_read_input_tokens', 0)
                # Handle object-like usage
                else:
                    input_tokens = getattr(usage, 'input_tokens', 0)
                    output_tokens = getattr(usage, 'output_tokens', 0)
                    cache_creation = getattr(usage, 'cache_creation_input_tokens', 0)
                    cache_read = getattr(usage, 'cache_read_input_tokens', 0)
                
                return {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                    'cached_tokens': cache_creation + cache_read,
                    'api_calls_count': 1
                }
            
            logger.warning("No usage information found in Anthropic response")
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract Anthropic usage: {e}")
            return None
    
    @staticmethod
    def extract_gemini_usage(response: Any) -> Optional[Dict[str, int]]:
        """
        Extract token usage from Gemini API response.
        
        Gemini API returns:
        {
            "candidates": [...],
            "usage_metadata": {
                "prompt_token_count": 123,
                "candidates_token_count": 456,
                "total_token_count": 579,
                "cached_content_token_count": 100  # if using caching
            }
        }
        """
        try:
            # Case 1: Response is a dict with 'usage_metadata' key
            if isinstance(response, dict) and 'usage_metadata' in response:
                usage = response['usage_metadata']
                input_tokens = usage.get('prompt_token_count', 0) or 0
                output_tokens = usage.get('candidates_token_count', 0) or 0
                total_tokens = usage.get('total_token_count', None) or (input_tokens + output_tokens)
                cached_tokens = usage.get('cached_content_token_count', 0) or 0
                
                return {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': total_tokens,
                    'cached_tokens': cached_tokens,
                    'api_calls_count': 1
                }
            
            # Case 2: Response is an object with 'usage_metadata' attribute
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                
                # Handle dict-like usage
                if isinstance(usage, dict):
                    input_tokens = usage.get('prompt_token_count', 0) or 0
                    output_tokens = usage.get('candidates_token_count', 0) or 0
                    total_tokens = usage.get('total_token_count', None) or (input_tokens + output_tokens)
                    cached_tokens = usage.get('cached_content_token_count', 0) or 0
                # Handle object-like usage
                else:
                    input_tokens = getattr(usage, 'prompt_token_count', 0) or 0
                    output_tokens = getattr(usage, 'candidates_token_count', 0) or 0
                    total_tokens = getattr(usage, 'total_token_count', None) or (input_tokens + output_tokens)
                    cached_tokens = getattr(usage, 'cached_content_token_count', 0) or 0
                
                return {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': total_tokens,
                    'cached_tokens': cached_tokens,
                    'api_calls_count': 1
                }
            
            logger.warning("No usage information found in Gemini response")
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract Gemini usage: {e}")
            return None
    
    @staticmethod
    def extract_usage(response: Any, model_type: str) -> Optional[Dict[str, int]]:
        """
        Extract usage from any API response based on model type.
        
        Args:
            response: API response (dict or object)
            model_type: 'openai', 'anthropic', or 'gemini'
            
        Returns:
            Dict with usage information or None
        """
        if model_type == 'openai':
            return UsageExtractor.extract_openai_usage(response)
        elif model_type == 'anthropic':
            return UsageExtractor.extract_anthropic_usage(response)
        elif model_type == 'gemini':
            return UsageExtractor.extract_gemini_usage(response)
        else:
            logger.warning(f"Unknown model type: {model_type}")
            return None


# Convenience function
def extract_usage(response: Any, model_type: str) -> Optional[Dict[str, int]]:
    """Extract usage from API response"""
    return UsageExtractor.extract_usage(response, model_type)

