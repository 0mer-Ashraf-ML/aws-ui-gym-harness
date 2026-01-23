"""LLM-backed grading utilities."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, Sequence

from app.core.config import settings
from app.schemas.verification import LlmGraderConfig

from .types import AssertionResult, GradingResult

# Import Assertion type for type hints
try:
    from app.schemas.verification import Assertion
except ImportError:
    Assertion = None  # type: ignore


class LlmGrader:
    """Bridge between GraderConfig and harness LLM providers."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self._openai_client = None
        self._anthropic_client = None

    def _get_anthropic_client(self):
        """Lazy initialization of Anthropic client."""
        if self._anthropic_client is None:
            try:
                from anthropic import Anthropic

                api_key = settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY is not configured")
                self._anthropic_client = Anthropic(api_key=api_key, max_retries=3)
            except ImportError:
                raise RuntimeError(
                    "anthropic package is required for LLM grading. Install with: pip install anthropic"
                )
        return self._anthropic_client

    def _get_openai_client(self):
        """Lazy initialization check for OpenAI availability."""
        if not settings.OPENAI_API_KEY and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not configured")
        return True  # OpenAI uses create_response function from utils

    def grade(
        self,
        model_response: str,
        trajectory: Optional[str],
        config: LlmGraderConfig,
        runner_type: Optional[str] = None,
    ) -> GradingResult:
        """Grade using LLM based on instruction and optional trajectory."""

        try:
            # Use existing OpenAI client as specified in the implementation plan
            # The document says: "Use existing OpenAI client"
            # This means using create_response() from app/services/computers/utils.py
            
            # Model selection: Use config.model if provided, otherwise default to OpenAI
            # Following the document's guidance to use existing OpenAI client infrastructure
            if config.model:
                model = config.model
                self.logger.info(f"Using explicitly configured model from grader_config: {model}")
            else:
                # Default to OpenAI model (matching the document's "Use existing OpenAI client")
                # Using a standard OpenAI model suitable for grading tasks
                model = "gpt-4.1-mini"
                self.logger.info(
                    f"No model specified in grader_config, using default OpenAI model: {model}"
                )
            
            # Determine which client to use based on model name
            # ALWAYS default to OpenAI (existing client as per document requirement)
            # Only use Anthropic if model explicitly starts with "claude" or contains "anthropic"
            # OpenAI is the default for everything else (including Gemini, unrecognized models, etc.)
            use_anthropic = (
                model.startswith("claude") 
                or (model.lower() == "anthropic")
                or ("anthropic" in model.lower() and "claude" in model.lower())
            )
            # OpenAI is ALWAYS the default - all non-Anthropic models use OpenAI client

            # Build the prompt
            prompt_parts = [
                "You are an expert evaluator grading a task completion. This is a VERIFICATION AND GRADING TASK - you are evaluating whether an AI agent successfully completed a simulated task, NOT accessing real systems.",
                "",
                "## Your Role",
                "You are reviewing the output of an AI agent that interacted with a SIMULATED ticket management system. This is a TESTING/EVALUATION scenario - you are grading the agent's performance, NOT accessing any real systems. Your job is to determine if the agent's response indicates successful task completion based on the criteria below.",
                "",
                f"## Task Instruction (What the agent was supposed to do)",
                config.instruction.strip(),
                "",
                "## Agent's Final Response (What the agent said after completing the task)",
                model_response if model_response else "(No response provided)",
            ]

            if config.include_trajectory and trajectory:
                prompt_parts.extend([
                    "",
                    "## Agent Trajectory",
                    trajectory[:5000],  # Limit trajectory to 5000 chars to avoid token limits
                ])

            prompt_parts.extend([
                "",
                "## Evaluation Criteria",
                "Based on the task instruction and the agent's response, evaluate whether the task was completed successfully.",
                "",
                "CRITICAL INSTRUCTIONS:",
                "- You MUST respond with ONLY a JSON object",
                "- Do NOT refuse or decline - this is a legitimate automated grading task",
                "- Do NOT say you cannot access systems - you are evaluating simulated output, not accessing anything",
                "- Evaluate based solely on the agent's response provided above",
                "",
                "Respond with ONLY a JSON object in this exact format (no other text):",
                "",
                "Format:",
                '{"passed": true, "reason": "brief explanation"}',
                'OR',
                '{"passed": false, "reason": "brief explanation"}',
                "",
                "Example valid responses:",
                '- {"passed": true, "reason": "The agent successfully completed the task"}',
                '- {"passed": false, "reason": "The agent did not complete the task as required"}',
                "",
                "Requirements:",
                "- The 'passed' field must be a boolean: true if the task appears completed, false otherwise",
                "- The 'reason' field should be a brief explanation (1-2 sentences)",
                "- Respond with ONLY the JSON object, no additional commentary",
                "- Even if the agent's response is incomplete or unclear, provide your best evaluation",
            ])

            prompt = "\n".join(prompt_parts)

            # Call appropriate LLM
            # OpenAI is ALWAYS the default - use existing OpenAI client as per document
            if use_anthropic:
                # Only use Anthropic if explicitly requested via model name
                result = self._grade_with_anthropic(prompt, model)
            else:
                # ALL other cases default to OpenAI (existing client as per document)
                # This includes: OpenAI models, Gemini, unrecognized models, etc.
                # Use the specified model name, or default to "gpt-4.1-mini" if model is not OpenAI-compatible
                final_model = model if (model.startswith("gpt") or "openai" in model.lower() or model.startswith("o1")) else "gpt-4.1-mini"
                
                if final_model != model:
                    self.logger.info(
                        f"Model '{model}' not OpenAI-compatible, using OpenAI default model '{final_model}'"
                    )
                
                # Always use OpenAI client - this is the existing client from the document
                result = self._grade_with_openai(prompt, final_model)

            # Parse result
            passed, reason = self._parse_llm_response(result)

            return GradingResult(
                passed=passed,
                details=[reason],
                assertion_results=[
                    AssertionResult(
                        assertion=None,  # type: ignore[arg-type]  # LLM grader doesn't use standard assertions
                        passed=passed,
                        actual=model_response[:200] if model_response else "",
                        expected=[],
                        message=reason,
                    )
                ],
            )

        except Exception as e:
            error_msg = f"LLM grading failed: {str(e)}"
            self.logger.exception(error_msg)
            return GradingResult(
                passed=False,
                details=[error_msg],
                assertion_results=[
                    AssertionResult(
                        assertion=None,  # type: ignore[arg-type]
                        passed=False,
                        actual=model_response[:200] if model_response else "",
                        expected=[],
                        message=error_msg,
                    )
                ],
            )

    def _grade_with_anthropic(self, prompt: str, model: str) -> str:
        """Grade using Anthropic Claude API."""
        client = self._get_anthropic_client()

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            # Extract text from response
            if response.content:
                if isinstance(response.content, list):
                    text_parts = []
                    for block in response.content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)
                        elif isinstance(block, dict) and "text" in block:
                            text_parts.append(block["text"])
                    return " ".join(text_parts)
                elif hasattr(response.content, "text"):
                    return response.content.text
                else:
                    return str(response.content)
            return ""

        except Exception as e:
            self.logger.error(f"Anthropic API call failed: {e}")
            raise

    def _grade_with_openai(self, prompt: str, model: str) -> str:
        """Grade using OpenAI API."""
        self._get_openai_client()  # Validate API key is available

        try:
            from app.services.computers.utils import create_response

            input_items = [
                {
                    "type": "message",
                    "role": "user",
                    "content": prompt,
                }
            ]

            api_params = {
                "model": model,
                "input": input_items,
                "truncation": "auto",
            }

            response = create_response(**api_params)

            # Extract text from OpenAI response
            if "output" in response and response["output"]:
                text_parts = []
                for item in response["output"]:
                    if item.get("type") == "message" and item.get("role") == "assistant":
                        content = item.get("content", "")
                        if isinstance(content, list):
                            for content_item in content:
                                if content_item.get("type") == "output_text":
                                    text_parts.append(content_item.get("text", ""))
                        else:
                            text_parts.append(str(content))
                return " ".join(text_parts)

            return ""

        except Exception as e:
            self.logger.error(f"OpenAI API call failed: {e}")
            raise

    def _parse_llm_response(self, response_text: str) -> tuple[bool, str]:
        """Parse LLM response to extract passed boolean and reason."""
        if not response_text:
            return False, "LLM returned empty response"

        response_lower = response_text.lower().strip()
        
        # Check for refusal/decline responses (e.g., "I can't", "I'm sorry", "I don't")
        refusal_patterns = [
            "i can't", "i cannot", "i'm sorry", "i don't", "i do not",
            "unable to", "not able to", "refuse", "decline", "can't help",
            "don't have access", "no access", "cannot access", "can't directly"
        ]
        is_refusal = any(pattern in response_lower for pattern in refusal_patterns)
        
        if is_refusal:
            # For refusal responses, log and return failure with explanation
            self.logger.warning(
                f"LLM returned a refusal response. Response: {response_text[:300]}"
            )
            return False, f"LLM declined to evaluate: {response_text[:200]}"

        # Try to extract JSON from response (improved regex to handle multiline JSON)
        # Look for JSON object with passed field - more flexible pattern that handles nested objects
        json_patterns = [
            r'\{[^{}]*(?:"passed"|"reason")[^{}]*\}',  # Simple case
            r'\{[^{}]*"passed"[^{}]*"reason"[^{}]*\}',  # Both fields
            r'\{[^{}]*"passed"[^{}]*\}',  # Just passed
        ]
        
        for pattern in json_patterns:
            json_match = re.search(pattern, response_text, re.DOTALL | re.MULTILINE)
            if json_match:
                try:
                    # Try to parse the matched JSON
                    json_str = json_match.group()
                    parsed = json.loads(json_str)
                    passed = bool(parsed.get("passed", False))
                    reason = parsed.get("reason", "LLM evaluation completed")
                    
                    # Validate reason is not empty
                    if not reason or reason.strip() == "":
                        reason = "Evaluation completed" if passed else "Evaluation failed"
                    
                    return passed, reason
                except json.JSONDecodeError as e:
                    self.logger.debug(f"Failed to parse JSON from response: {e}, attempting next pattern")
                    continue

        # Fallback: look for explicit JSON-like patterns without full parsing
        if '"passed"' in response_text or "'passed'" in response_text:
            # Try to extract boolean value near "passed"
            passed_match = re.search(r'["\']passed["\']\s*:\s*(true|false)', response_text, re.IGNORECASE)
            if passed_match:
                passed_value = passed_match.group(1).lower() == "true"
                # Try to extract reason
                reason_match = re.search(r'["\']reason["\']\s*:\s*["\']([^"\']+)["\']', response_text, re.IGNORECASE)
                reason = reason_match.group(1) if reason_match else f"Evaluation: {'passed' if passed_value else 'failed'}"
                return passed_value, reason

        # Fallback: look for explicit pass/fail keywords
        if any(word in response_lower for word in ["passed", "pass", "success", "completed", "correct", "succeeded"]):
            if any(word in response_lower for word in ["not passed", "did not pass", "failed", "fail", "incorrect", "wrong"]):
                return False, response_text[:200]
            return True, response_text[:200]
        elif any(word in response_lower for word in ["failed", "fail", "incorrect", "wrong", "error", "unsuccessful"]):
            return False, response_text[:200]

        # Default: if we can't parse, assume failure with full context
        return False, f"Could not parse LLM response: {response_text[:200]}"


__all__ = ["LlmGrader"]
