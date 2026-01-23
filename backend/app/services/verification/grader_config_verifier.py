"""Coordinator for GraderConfig-based verification."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from app.schemas.verification import GraderConfig

from .answer_grader import AnswerGrader
from .assertion_engine import AssertionEngine, ConfigurationError
from .llm_grader import LlmGrader
from .state_grader import StateGrader
from .types import GradingContext, GradingResult
from .url_grader import UrlGrader

# Type hint for Playwright Page (optional dependency)
try:
    from playwright.sync_api import Page as PlaywrightPage
except ImportError:
    PlaywrightPage = Any  # type: ignore


class GraderConfigVerifier:
    """High-level orchestrator that will replace gym-side verification."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        assertion_engine: Optional[AssertionEngine] = None,
        state_grader: Optional[StateGrader] = None,
        answer_grader: Optional[AnswerGrader] = None,
        url_grader: Optional[UrlGrader] = None,
        llm_grader: Optional[LlmGrader] = None,
        browser_page: Optional[PlaywrightPage] = None,
        browser_computer: Optional[Any] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.assertion_engine = assertion_engine or AssertionEngine(logger=self.logger)
        self.state_grader = state_grader or StateGrader(
            assertion_engine=self.assertion_engine, logger=self.logger
        )
        self.answer_grader = answer_grader or AnswerGrader(
            assertion_engine=self.assertion_engine, logger=self.logger
        )
        self.url_grader = url_grader or UrlGrader(
            assertion_engine=self.assertion_engine, logger=self.logger
        )
        self.llm_grader = llm_grader or LlmGrader(logger=self.logger)
        
        # Browser access for window.get_states() calls
        self.browser_page = browser_page
        self.browser_computer = browser_computer
        
        # If computer is provided but page is not, try to extract page from computer
        if not self.browser_page and self.browser_computer:
            if hasattr(self.browser_computer, '_page'):
                self.browser_page = self.browser_computer._page
            elif hasattr(self.browser_computer, 'page'):
                self.browser_page = self.browser_computer.page

    def verify_task(
        self,
        task: Dict[str, Any],
        execution_results: Dict[str, Any],
        results_dir: Path,
    ) -> Dict[str, Any]:
        """Execute GraderConfig-driven verification workflow."""

        try:
            grader_config_payload = task.get("grader_config")
            if not grader_config_payload:
                error_msg = "Task does not supply a grader_config payload"
                self.logger.error(error_msg)
                return {
                    "verification_method": "grader_config",
                    "verification_completed": False,
                    "verification_status": "FAILED",
                    "verification_summary": error_msg,
                    "grader_results": [],
                    "error": error_msg,
                }

            try:
                config = GraderConfig.model_validate(grader_config_payload)
            except Exception as e:
                error_msg = f"Invalid grader_config payload: {str(e)}"
                self.logger.error(error_msg)
                return {
                    "verification_method": "grader_config",
                    "verification_completed": False,
                    "verification_status": "FAILED",
                    "verification_summary": error_msg,
                    "grader_results": [],
                    "error": error_msg,
                }

            context = GradingContext(
                task=task,
                execution_results=execution_results,
                results_dir=str(results_dir),
            )

            # Collect states with error handling
            try:
                actual_state, expected_states = self._collect_states(config, context)
            except ConfigurationError:
                # Configuration errors should crash immediately
                self.logger.error("Configuration error during state collection - re-raising", exc_info=True)
                raise
            except Exception as e:
                error_msg = f"Failed to collect states: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                return {
                    "verification_method": "grader_config",
                    "verification_completed": False,
                    "verification_status": "FAILED",
                    "verification_summary": error_msg,
                    "grader_results": [],
                    "error": error_msg,
                }

            grader_summaries: List[Dict[str, Any]] = []
            overall_passed = True
            errors: List[str] = []

            # State graders
            if config.state_grader_configs:
                for index, state_config in enumerate(config.state_grader_configs, start=1):
                    try:
                        result = self.state_grader.grade(
                            actual_state=actual_state,
                            expected_states=expected_states,
                            config=state_config,
                        )
                        grader_summaries.append(
                            self._serialise_grader_result(
                                grader_type="state",
                                ordinal=index,
                                result=result,
                            )
                        )
                        overall_passed &= result.passed
                    except ConfigurationError:
                        # Configuration errors should crash immediately
                        self.logger.error(f"State grader {index} configuration error - re-raising", exc_info=True)
                        raise
                    except Exception as e:
                        error_msg = f"State grader {index} failed: {str(e)}"
                        self.logger.error(error_msg, exc_info=True)
                        errors.append(error_msg)
                        grader_summaries.append({
                            "type": "state",
                            "ordinal": index,
                            "passed": False,
                            "details": [error_msg],
                            "error": error_msg,
                        })
                        overall_passed = False

            # Answer grader
            if config.answer_grader_config:
                try:
                    model_response = self._extract_final_model_response(context)
                    result = self.answer_grader.grade(
                        model_response=model_response,
                        expected_states=expected_states,
                        config=config.answer_grader_config,
                        response_context=execution_results,
                    )
                    grader_summaries.append(
                        self._serialise_grader_result(
                            grader_type="answer",
                            ordinal=1,
                            result=result,
                            extra={"model_response": model_response},
                        )
                    )
                    overall_passed &= result.passed
                except ConfigurationError:
                    # Configuration errors should crash immediately
                    self.logger.error("Answer grader configuration error - re-raising", exc_info=True)
                    raise
                except Exception as e:
                    error_msg = f"Answer grader failed: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    grader_summaries.append({
                        "type": "answer",
                        "ordinal": 1,
                        "passed": False,
                        "details": [error_msg],
                        "error": error_msg,
                    })
                    overall_passed = False

            # URL grader
            if config.url_grader_config:
                try:
                    final_url = self._extract_final_url(context)
                    result = self.url_grader.grade(final_url, config.url_grader_config)
                    grader_summaries.append(
                        self._serialise_grader_result(
                            grader_type="url",
                            ordinal=1,
                            result=result,
                            extra={"final_url": final_url},
                        )
                    )
                    overall_passed &= result.passed
                except ConfigurationError:
                    # Configuration errors should crash immediately
                    self.logger.error("URL grader configuration error - re-raising", exc_info=True)
                    raise
                except Exception as e:
                    error_msg = f"URL grader failed: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    grader_summaries.append({
                        "type": "url",
                        "ordinal": 1,
                        "passed": False,
                        "details": [error_msg],
                        "error": error_msg,
                    })
                    overall_passed = False

            # LLM graders
            if config.llm_grader_configs:
                trajectory = execution_results.get("trajectory")
                model_response = self._extract_final_model_response(context)
                # Extract runner_type from task for auto-selecting model
                runner_type = task.get("runner_type") or task.get("model_type")
                for index, llm_config in enumerate(config.llm_grader_configs, start=1):
                    try:
                        result = self.llm_grader.grade(
                            model_response=model_response,
                            trajectory=trajectory,
                            config=llm_config,
                            runner_type=runner_type,
                        )
                        grader_summaries.append(
                            self._serialise_grader_result(
                                grader_type="llm",
                                ordinal=index,
                                result=result,
                                extra={"instruction": llm_config.instruction},
                            )
                        )
                        overall_passed &= result.passed
                    except Exception as e:
                        error_msg = f"LLM grader {index} failed: {str(e)}"
                        self.logger.error(error_msg, exc_info=True)
                        errors.append(error_msg)
                        grader_summaries.append({
                            "type": "llm",
                            "ordinal": index,
                            "passed": False,
                            "details": [error_msg],
                            "error": error_msg,
                        })
                        overall_passed = False

            summary_text = self._build_summary(grader_summaries, overall_passed)
            if errors:
                summary_text += f" Errors: {'; '.join(errors)}"

            return {
                "verification_method": "grader_config",
                "verification_completed": True,
                "verification_status": "PASSED" if overall_passed else "FAILED",
                "verification_summary": summary_text,
                "grader_results": grader_summaries,
                **({"errors": errors} if errors else {}),
            }

        except ConfigurationError:
            # Configuration errors should crash the entire verification
            self.logger.error("Configuration error in verify_task - re-raising", exc_info=True)
            raise
        except Exception as e:
            error_msg = f"Unexpected error in GraderConfig verification: {str(e)}"
            self.logger.exception(error_msg)
            return {
                "verification_method": "grader_config",
                "verification_completed": False,
                "verification_status": "FAILED",
                "verification_summary": error_msg,
                "grader_results": [],
                "error": error_msg,
            }

    # Future helper methods (e.g., call_window_get_states) will be added during Step 4.

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _collect_states(
        self, config: GraderConfig, context: GradingContext
    ) -> tuple[Any, Sequence[Any]]:
        """Retrieve actual/expected states via window.get_states or fallbacks."""

        if (
            config.extract_states_config
            and config.extract_states_config.expected_state_functions
        ):
            try:
                payload = self.call_window_get_states(
                    expected_state_functions=[
                        fn.model_dump()  # type: ignore[union-attr]
                        for fn in config.extract_states_config.expected_state_functions
                    ],
                    context=context,
                )
                
                # Save get_states result to file
                self._save_get_states_result(payload, context)
                
                actual_state = payload.get("actual_state", {})
                expected_states = payload.get("expected_states") or []
                return actual_state, expected_states
            except Exception as e:
                self.logger.warning(
                    f"Failed to call window.get_states(): {e}. Falling back to execution_results."
                )
                # Fall through to fallback below

        # Fallback: reuse any state captured within execution_results to stay backward compatible
        actual_state = context.execution_results.get("actual_state", {})
        expected_states = context.execution_results.get("expected_states", [])
        return actual_state, expected_states

    def _save_get_states_result(
        self, payload: Dict[str, Any], context: GradingContext
    ) -> None:
        """Save the window.get_states() result to a file for debugging."""
        try:
            results_dir = context.results_dir
            if not results_dir:
                self.logger.warning("No results_dir available, skipping get_states file save")
                return
            
            # Convert string to Path if needed
            if isinstance(results_dir, str):
                results_dir = Path(results_dir)
            
            # Create get_states.json in the results directory
            get_states_file = results_dir / "get_states.json"
            
            self.logger.info(f"💾 Saving get_states result to: {get_states_file}")
            
            with open(get_states_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            
            self.logger.info(f"✅ Saved get_states result to: {get_states_file}")
            
        except Exception as e:
            # Don't fail verification if saving fails
            self.logger.warning(f"❌ Failed to save get_states result to file: {e}", exc_info=True)

    def call_window_get_states(
        self,
        expected_state_functions: Sequence[Dict[str, Any]],
        context: GradingContext,
    ) -> Dict[str, Any]:
        """Invoke window.get_states via mock service or browser automation.

        Priority order:
        1. Check cached payload in execution_results (for testing)
        2. If USE_MOCK_STATES_ENDPOINT=True: Use mock service (direct function call)
        3. Otherwise: Use browser automation to call window.get_states() in the browser
        
        Returns both actual_state (current gym state) and expected_states (computed from
        expected_state_functions).
        """
        # Check for cached payload first (useful for testing)
        cached_payload = context.execution_results.get("window_get_states_payload")
        if isinstance(cached_payload, dict):
            self.logger.debug("Using cached window.get_states payload")
            return cached_payload

        # Priority 2: Use mock service if feature flag is enabled
        from app.core.config import settings
        if getattr(settings, 'USE_MOCK_STATES_ENDPOINT', False):
            task = context.task
            task_id = task.get("task_id")
            
            self.logger.info(
                f"Using mock states service (feature flag enabled) for task {task_id}"
            )
            
            # Direct function call - no HTTP overhead!
            from app.services.verification.mock_states_service import get_mock_states
            
            try:
                mock_result = get_mock_states(
                    task_id=task_id,
                    expected_state_functions=list(expected_state_functions),
                )
                self.logger.info(
                    f"Successfully retrieved mock states: actual_state keys={list(mock_result.get('actual_state', {}).keys())}, "
                    f"expected_states count={len(mock_result.get('expected_states', []))}"
                )
                return mock_result
            except Exception as e:
                error_msg = f"Mock states service failed: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e

        # Priority 3: Browser automation (existing implementation)
        # Validate browser page is available
        if not self.browser_page:
            raise RuntimeError(
                "Browser page not available. Cannot call window.get_states(). "
                "Ensure browser_page or browser_computer is passed to GraderConfigVerifier."
            )

        # Check if page is closed (critical for batch runs where cleanup might happen)
        try:
            if hasattr(self.browser_page, 'is_closed') and self.browser_page.is_closed():
                raise RuntimeError(
                    "Browser page is closed. Cannot call window.get_states(). "
                    "The browser may have been cleaned up before verification."
                )
        except AttributeError:
            # Some page implementations may not have is_closed method
            pass
        except Exception as e:
            # If checking is_closed() itself raises an error, the page is likely invalid
            self.logger.warning(f"Could not check if page is closed: {e}")

        try:
            # Check if window.get_states exists in the browser
            # First, verify the function exists
            check_script = """
                () => {
                    if (typeof window === 'undefined' || typeof window.get_states !== 'function') {
                        return { error: 'window.get_states is not available' };
                    }
                    return { available: true };
                }
            """
            
            try:
                check_result = self.browser_page.evaluate(check_script)
            except Exception as check_error:
                # Handle browser/page errors during initial check
                error_msg = f"Browser check failed: {str(check_error)}"
                self.logger.error(error_msg, exc_info=True)
                raise RuntimeError(
                    f"Failed to check window.get_states() availability: {error_msg}. "
                    "The browser page may have been closed or is invalid."
                ) from check_error
            
            if isinstance(check_result, dict) and check_result.get("error"):
                error_msg = check_result.get("error", "Unknown error")
                raise RuntimeError(
                    f"window.get_states() is not available in the browser: {error_msg}. "
                    "Ensure the gym implements window.get_states() function."
                )

            # Call window.get_states with expected_state_functions
            # Serialize the functions list to JSON for JavaScript
            functions_json = json.dumps(expected_state_functions)
            
            call_script = f"""
                async () => {{
                    try {{
                        const expectedStateFunctions = {functions_json};
                        const result = await window.get_states(expectedStateFunctions);
                        return {{
                            success: true,
                            data: result
                        }};
                    }} catch (error) {{
                        return {{
                            success: false,
                            error: error.message || String(error),
                            stack: error.stack
                        }};
                    }}
                }}
            """
            
            self.logger.info(
                f"Calling window.get_states() with {len(expected_state_functions)} expected state function(s)"
            )
            
            try:
                result = self.browser_page.evaluate(call_script)
            except Exception as eval_error:
                # Handle browser/page errors (page closed, navigation, etc.)
                error_msg = f"Browser evaluation failed: {str(eval_error)}"
                self.logger.error(error_msg, exc_info=True)
                raise RuntimeError(
                    f"Failed to evaluate window.get_states() in browser: {error_msg}. "
                    "The browser page may have been closed or navigated away."
                ) from eval_error
            
            if isinstance(result, dict) and not result.get("success", True):
                error_msg = result.get("error", "Unknown error during window.get_states() call")
                stack = result.get("stack", "")
                self.logger.error(
                    f"window.get_states() failed: {error_msg}"
                    + (f"\nStack: {stack}" if stack else "")
                )
                raise RuntimeError(f"window.get_states() call failed: {error_msg}")

            # Extract the data payload
            if isinstance(result, dict):
                payload = result.get("data", result)  # Use 'data' field if present, else use entire result
            else:
                payload = result

            # Validate payload structure
            if not isinstance(payload, dict):
                raise ValueError(
                    f"window.get_states() returned unexpected type: {type(payload)}. "
                    "Expected a dictionary with 'actual_state' and 'expected_states'."
                )

            # Ensure expected_states is a list
            if "expected_states" in payload and not isinstance(payload["expected_states"], list):
                self.logger.warning(
                    "expected_states is not a list, converting to list"
                )
                payload["expected_states"] = [payload["expected_states"]]

            self.logger.info(
                f"Successfully retrieved states: actual_state keys={list(payload.get('actual_state', {}).keys())}, "
                f"expected_states count={len(payload.get('expected_states', []))}"
            )

            return payload

        except RuntimeError:
            # Re-raise RuntimeErrors (already logged)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error calling window.get_states(): {e}")
            raise RuntimeError(
                f"Failed to call window.get_states(): {e}"
            ) from e

    def _extract_final_model_response(self, context: GradingContext) -> str:
        execution_results = context.execution_results
        candidate_keys = [
            "modelResponse",
            "finalModelResponse",
            "final_response",
            "assistant_message",
            "finalMessage",
            "completion_reason",  # Also check completion_reason as fallback
        ]
        for key in candidate_keys:
            value = execution_results.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_final_url(self, context: GradingContext) -> str:
        execution_results = context.execution_results
        candidate_keys = ["final_url", "last_url", "current_url"]
        for key in candidate_keys:
            value = execution_results.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _serialise_grader_result(
        grader_type: str,
        ordinal: int,
        result: GradingResult,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": grader_type,
            "ordinal": ordinal,
            "passed": result.passed,
            "details": result.details,
            "assertions": [
                {
                    "operator": ar.assertion.operator.value if ar.assertion else "LLM_GRADE",
                    "passed": ar.passed,
                    "message": ar.message,
                    "expected": ar.expected,
                    "actual": ar.actual,
                }
                for ar in result.assertion_results
            ],
        }
        if extra:
            payload.update(extra)
        return payload

    @staticmethod
    def _build_summary(grader_payloads: List[Dict[str, Any]], passed: bool) -> str:
        total = len(grader_payloads)
        successes = sum(1 for payload in grader_payloads if payload.get("passed"))
        failures = total - successes
        
        if passed:
            return f"All {total}/{total} graders passed"
        elif successes == 0:
            return f"All {total}/{total} graders failed"
        else:
            return f"{successes}/{total} graders passed, {failures}/{total} failed"


__all__ = ["GraderConfigVerifier"]
