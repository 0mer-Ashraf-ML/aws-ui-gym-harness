"""
Token Usage Tracker Service

This service extracts and stores token usage data from API responses
for OpenAI, Anthropic, and Gemini models.
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_usage import TokenUsage
from app.schemas.token_usage import TokenUsageCreate
from app.services.crud.token_usage import TokenUsageCRUD
from app.services.usage_extractor import UsageExtractor


logger = logging.getLogger(__name__)


class UsageTracker:
    """Track and store token usage from API responses"""
    
    # Cost per 1K tokens (approximate, should be updated regularly)
    # Format: {model_name: {input_cost_per_1k, output_cost_per_1k}}
    PRICING = {
        'openai': {
            'gpt-4': {'input': 0.03, 'output': 0.06},
            'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
            'gpt-4o': {'input': 0.005, 'output': 0.015},
            'gpt-3.5-turbo': {'input': 0.0015, 'output': 0.002},
        },
        'anthropic': {
            'claude-opus-4': {'input': 0.015, 'output': 0.075},
            'claude-sonnet-4': {'input': 0.003, 'output': 0.015},
            'claude-haiku-4': {'input': 0.0008, 'output': 0.004},
            'claude-3-opus': {'input': 0.015, 'output': 0.075},
            'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
            'claude-3-haiku': {'input': 0.00025, 'output': 0.00125},
        },
        'gemini': {
            'gemini-2.0-flash-exp': {'input': 0.00, 'output': 0.00},  # Free tier
            'gemini-1.5-pro': {'input': 0.00125, 'output': 0.005},
            'gemini-1.5-flash': {'input': 0.000075, 'output': 0.0003},
        }
    }
    
    def __init__(self, db: AsyncSession):
        """Initialize usage tracker with database session"""
        self.db = db
        self.crud = TokenUsageCRUD()
    
    async def track_openai_usage(
        self,
        response: Any,
        iteration_id: UUID,
        execution_id: UUID,
        model_version: Optional[str] = None
    ) -> Optional[TokenUsage]:
        """
        Track token usage from OpenAI API response.
        
        OpenAI responses have a 'usage' field with:
        - prompt_tokens
        - completion_tokens
        - total_tokens
        """
        try:
            # Extract usage using the accurate extractor
            usage_dict = UsageExtractor.extract_openai_usage(response)
            if not usage_dict:
                logger.warning("No usage information in OpenAI response")
                return None
            
            # Extract token counts
            input_tokens = usage_dict['input_tokens']
            output_tokens = usage_dict['output_tokens']
            total_tokens = usage_dict['total_tokens']
            cached_tokens = usage_dict['cached_tokens']
            
            # Calculate estimated cost
            estimated_cost = self._calculate_cost(
                model_name='openai',
                model_version=model_version or 'gpt-4',
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            # Create usage record
            usage_data = TokenUsageCreate(
                iteration_id=iteration_id,
                execution_id=execution_id,
                model_name='openai',
                model_version=model_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                api_calls_count=1,
                cached_tokens=cached_tokens,
                estimated_cost_usd=estimated_cost
            )
            
            # Store in database
            token_usage = await self.crud.create(self.db, usage_data)
            logger.info(f"✅ Tracked OpenAI usage: {total_tokens} tokens, ${estimated_cost:.4f}")
            
            return token_usage
            
        except Exception as e:
            logger.error(f"❌ Failed to track OpenAI usage: {e}")
            return None
    
    async def track_anthropic_usage(
        self,
        response: Any,
        iteration_id: UUID,
        execution_id: UUID,
        model_version: Optional[str] = None
    ) -> Optional[TokenUsage]:
        """
        Track token usage from Anthropic API response.
        
        Anthropic responses have a 'usage' field with:
        - input_tokens
        - output_tokens
        """
        try:
            # Extract usage using the accurate extractor
            usage_dict = UsageExtractor.extract_anthropic_usage(response)
            if not usage_dict:
                logger.warning("No usage information in Anthropic response")
                return None
            
            # Extract token counts
            input_tokens = usage_dict['input_tokens']
            output_tokens = usage_dict['output_tokens']
            total_tokens = usage_dict['total_tokens']
            cached_tokens = usage_dict['cached_tokens']
            
            # Calculate estimated cost
            estimated_cost = self._calculate_cost(
                model_name='anthropic',
                model_version=model_version or 'claude-sonnet-4',
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            # Create usage record
            usage_data = TokenUsageCreate(
                iteration_id=iteration_id,
                execution_id=execution_id,
                model_name='anthropic',
                model_version=model_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                api_calls_count=1,
                cached_tokens=cached_tokens,
                estimated_cost_usd=estimated_cost
            )
            
            # Store in database
            token_usage = await self.crud.create(self.db, usage_data)
            logger.info(f"✅ Tracked Anthropic usage: {total_tokens} tokens, ${estimated_cost:.4f}")
            
            return token_usage
            
        except Exception as e:
            logger.error(f"❌ Failed to track Anthropic usage: {e}")
            return None
    
    async def track_gemini_usage(
        self,
        response: Any,
        iteration_id: UUID,
        execution_id: UUID,
        model_version: Optional[str] = None
    ) -> Optional[TokenUsage]:
        """
        Track token usage from Gemini API response.
        
        Gemini responses have a 'usage_metadata' field with:
        - prompt_token_count
        - candidates_token_count
        - total_token_count
        """
        try:
            # Extract usage using the accurate extractor
            usage_dict = UsageExtractor.extract_gemini_usage(response)
            if not usage_dict:
                logger.warning("No usage information in Gemini response")
                return None
            
            # Extract token counts
            input_tokens = usage_dict['input_tokens']
            output_tokens = usage_dict['output_tokens']
            total_tokens = usage_dict['total_tokens']
            cached_tokens = usage_dict['cached_tokens']
            
            # Calculate estimated cost
            estimated_cost = self._calculate_cost(
                model_name='gemini',
                model_version=model_version or 'gemini-2.0-flash-exp',
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            # Create usage record
            usage_data = TokenUsageCreate(
                iteration_id=iteration_id,
                execution_id=execution_id,
                model_name='gemini',
                model_version=model_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                api_calls_count=1,
                cached_tokens=cached_tokens,
                estimated_cost_usd=estimated_cost
            )
            
            # Store in database
            token_usage = await self.crud.create(self.db, usage_data)
            logger.info(f"✅ Tracked Gemini usage: {total_tokens} tokens, ${estimated_cost:.4f}")
            
            return token_usage
            
        except Exception as e:
            logger.error(f"❌ Failed to track Gemini usage: {e}")
            return None
    
    async def track_usage_from_dict(
        self,
        usage_dict: Dict[str, Any],
        model_name: str,
        iteration_id: UUID,
        execution_id: UUID,
        model_version: Optional[str] = None
    ) -> Optional[TokenUsage]:
        """
        Track token usage from a dictionary (for manual tracking).
        
        Args:
            usage_dict: Dictionary with keys like 'input_tokens', 'output_tokens', etc.
            model_name: Model name (openai, anthropic, gemini)
            iteration_id: Iteration UUID
            execution_id: Execution UUID
            model_version: Optional model version
        """
        try:
            input_tokens = usage_dict.get('input_tokens', 0)
            output_tokens = usage_dict.get('output_tokens', 0)
            total_tokens = usage_dict.get('total_tokens', input_tokens + output_tokens)
            
            estimated_cost = self._calculate_cost(
                model_name=model_name,
                model_version=model_version or '',
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            usage_data = TokenUsageCreate(
                iteration_id=iteration_id,
                execution_id=execution_id,
                model_name=model_name,
                model_version=model_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                api_calls_count=usage_dict.get('api_calls_count', 1),
                cached_tokens=usage_dict.get('cached_tokens', 0),
                estimated_cost_usd=estimated_cost
            )
            
            token_usage = await self.crud.create(self.db, usage_data)
            logger.info(f"✅ Tracked {model_name} usage: {total_tokens} tokens, ${estimated_cost:.4f}")
            
            return token_usage
            
        except Exception as e:
            logger.error(f"❌ Failed to track usage from dict: {e}")
            return None
    
    def _calculate_cost(
        self,
        model_name: str,
        model_version: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate estimated cost based on token counts.
        
        Args:
            model_name: Model name (openai, anthropic, gemini)
            model_version: Model version
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Estimated cost in USD
        """
        try:
            # Get pricing for model
            if model_name not in self.PRICING:
                logger.warning(f"No pricing data for model: {model_name}")
                return 0.0
            
            # Try to find exact model version
            model_pricing = None
            for version_key, pricing in self.PRICING[model_name].items():
                if version_key in model_version.lower():
                    model_pricing = pricing
                    break
            
            if not model_pricing:
                # Use first available pricing as fallback
                model_pricing = list(self.PRICING[model_name].values())[0]
                logger.warning(f"Using fallback pricing for {model_name}/{model_version}")
            
            # Calculate cost (pricing is per 1K tokens)
            input_cost = (input_tokens / 1000) * model_pricing['input']
            output_cost = (output_tokens / 1000) * model_pricing['output']
            total_cost = input_cost + output_cost
            
            return round(total_cost, 6)
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate cost: {e}")
            return 0.0


    @staticmethod
    async def track_usage(
        db: AsyncSession,
        iteration_id: UUID,
        execution_id: UUID,
        model_name: str,
        api_response: Any,
        model_version: Optional[str] = None
    ) -> Optional[TokenUsage]:
        """
        Static method to track usage from any model API response.
        
        This is a convenience method that routes to the appropriate tracker
        based on the model_name.
        """
        tracker = UsageTracker(db)
        
        if model_name.lower() == 'openai':
            return await tracker.track_openai_usage(api_response, iteration_id, execution_id, model_version)
        elif model_name.lower() == 'anthropic':
            return await tracker.track_anthropic_usage(api_response, iteration_id, execution_id, model_version)
        elif model_name.lower() == 'gemini':
            return await tracker.track_gemini_usage(api_response, iteration_id, execution_id, model_version)
        else:
            logger.warning(f"Unknown model name: {model_name}")
            return None


async def create_usage_tracker(db: AsyncSession) -> UsageTracker:
    """Factory function to create a usage tracker instance"""
    return UsageTracker(db)

