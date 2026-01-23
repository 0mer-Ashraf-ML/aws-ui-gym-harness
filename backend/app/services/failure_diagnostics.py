"""
Failure diagnostics service for analyzing iteration failures.

Categorizes failures into meaningful groups without requiring database changes.
"""

import json
import logging
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Categories for iteration failures"""
    MODEL_BLOCKED = "model_blocked"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_ERROR = "verification_error"  # Verification script crashed/errored
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    UNKNOWN = "unknown"


class FailureDiagnostics:
    """Analyze iteration failures and categorize them"""
    
    # Keywords that indicate model explicitly stated it couldn't complete
    MODEL_BLOCKED_KEYWORDS = [
        "couldn't find",
        "unable to proceed",
        "unable to complete",
        "limitation",
        "no evident option",
        "cannot access",
        "not accessible",
        "appears to be limited",
        "might either require",
        "no direct access",
        "couldn't locate",
        "failed to find",
        "could not find",
        "no clear way",
        "seems impossible",
        "were unsuccessful",
        "was unsuccessful",
        "did not provide",
        "does not provide",
        "might be restricted",
        "may be restricted",
        "requiring specific permissions",
        "not available in the current view",
        "not present in this view",
        "no way to access",
        "could not locate",
        "failed to locate",
        "unable to find",
    ]
    
    TIMEOUT_KEYWORDS = [
        "timeout",
        "time limit",
        "exceeded",
        "timed out",
        "time exceeded",
    ]
    
    @staticmethod
    def categorize_failure(
        iteration,
        completion_reason: Optional[str] = None,
        last_model_response: Optional[str] = None,
        verification_details: Optional[Dict] = None,
        error_message: Optional[str] = None,
    ) -> Dict:
        """
        Analyze iteration data to determine failure category.
        
        Args:
            iteration: Iteration database model
            completion_reason: Optional override for completion reason
            last_model_response: Optional override for last model response
            verification_details: Optional parsed verification details dict
            error_message: Optional error message
            
        Returns:
            Dict with category, reason_text, and other diagnostic info
        """
        # Extract data from iteration if not provided
        if completion_reason is None:
            completion_reason = iteration.last_model_response or ""
        
        if last_model_response is None:
            last_model_response = iteration.last_model_response or ""
        
        if error_message is None:
            error_message = iteration.error_message or ""
        
        # Parse verification_details if it's a string
        if verification_details is None and iteration.verification_details:
            try:
                verification_details = json.loads(iteration.verification_details)
            except (json.JSONDecodeError, TypeError):
                verification_details = {}
        
        if not verification_details:
            verification_details = {}
        
        # Combine all text for analysis
        combined_text = f"{completion_reason} {last_model_response}".lower()
        
        # Determine category
        category = FailureCategory.UNKNOWN
        reason_text = "Unknown failure reason"
        
        # Check for timeout
        if any(keyword in combined_text for keyword in FailureDiagnostics.TIMEOUT_KEYWORDS):
            category = FailureCategory.TIMEOUT
            reason_text = "Task execution exceeded time limits"
        
        # Check for system crash/error
        elif error_message or "crashed" in iteration.status.lower() if hasattr(iteration, 'status') else False:
            category = FailureCategory.CRASHED
            reason_text = error_message[:200] if error_message else "System error during execution"
        
        # Check for model explicitly stating it cannot complete (BEFORE checking verification)
        # This should take priority over verification_failed
        elif any(keyword in combined_text for keyword in FailureDiagnostics.MODEL_BLOCKED_KEYWORDS):
            category = FailureCategory.MODEL_BLOCKED
            # Extract a meaningful excerpt from the model's response
            reason_text = FailureDiagnostics._extract_model_explanation(
                last_model_response or completion_reason
            )
        
        # Check if verification step failed or had errors
        elif verification_details.get("verification_status") == "FAILED":
            # First check if verification script itself crashed/had errors
            verification_completed = verification_details.get("verification_completed", True)
            
            if not verification_completed:
                # Verification script had technical errors
                category = FailureCategory.VERIFICATION_ERROR
                error_info = verification_details.get("error", "")
                verification_method = verification_details.get("verification_method", "")
                if error_info:
                    reason_text = f"Verification script error: {error_info[:150]}"
                else:
                    reason_text = f"Verification script failed to complete ({verification_method})"
            else:
                # Verification script ran successfully but reported task failed
                # Double-check: if completion_reason suggests model gave up, it's MODEL_BLOCKED
                if any(phrase in combined_text for phrase in ["gave up", "cannot complete", "unable to", "not possible"]):
                    category = FailureCategory.MODEL_BLOCKED
                    reason_text = FailureDiagnostics._extract_model_explanation(
                        last_model_response or completion_reason
                    )
                else:
                    category = FailureCategory.VERIFICATION_FAILED
                    # Extract specific failure reasons from verification results
                    reason_text = FailureDiagnostics._extract_verification_failure_details(verification_details)
        
        # If status is failed but we can't determine why
        elif iteration.status == "failed":
            # Try to extract any useful info from completion reason
            if completion_reason and len(completion_reason) > 10:
                reason_text = completion_reason[:200]
            else:
                reason_text = "Task failed - unable to determine specific reason"
        
        return {
            "category": category,
            "reason_text": reason_text,
            "completion_reason": completion_reason[:500] if completion_reason else None,
            "verification_status": verification_details.get("verification_status"),
            "has_error": bool(error_message),
        }
    
    @staticmethod
    def _extract_model_explanation(text: str) -> str:
        """
        Extract a concise explanation from model's response.
        
        Looks for sentences that explain why the model couldn't complete.
        """
        if not text:
            return "Model stated it could not complete the task"
        
        # Look for key phrases that explain the issue
        sentences = text.split(". ")
        
        # Find sentences with blocking keywords
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in FailureDiagnostics.MODEL_BLOCKED_KEYWORDS):
                # Return the first relevant sentence, truncated
                clean_sentence = sentence.strip()
                if clean_sentence:
                    return clean_sentence[:200] + ("..." if len(clean_sentence) > 200 else "")
        
        # If no specific sentence found, return beginning of text
        return text[:200] + ("..." if len(text) > 200 else "")
    
    @staticmethod
    def _extract_verification_failure_details(verification_details: Dict) -> str:
        """
        Extract specific failure details from verification results.
        
        Parses grader_results and API responses to show which specific checks failed and why.
        """
        # Try verification_comments first (explicit failure message)
        if verification_details.get("verification_comments"):
            comments = verification_details["verification_comments"].strip()
            if comments:
                return comments[:250]
        
        # Check for grader_results (from grader_config verification)
        grader_results = verification_details.get("grader_results", [])
        if grader_results:
            failed_checks = []
            for grader in grader_results:
                if not grader.get("passed", False):
                    # Extract grader type and details
                    grader_type = grader.get("type", "unknown")
                    details = grader.get("details", "")
                    
                    # Check for specific assertion failures
                    assertions = grader.get("assertions", [])
                    failed_assertions = [a for a in assertions if not a.get("passed", False)]
                    
                    if failed_assertions:
                        # Build detailed failure message from assertions
                        for assertion in failed_assertions[:2]:  # Limit to first 2 assertions
                            message = assertion.get("message", "")
                            expected = assertion.get("expected")
                            actual = assertion.get("actual")
                            
                            if message:
                                failed_checks.append(message)
                            elif expected is not None and actual is not None:
                                failed_checks.append(f"Expected {expected}, got {actual}")
                    elif details:
                        failed_checks.append(f"{grader_type}: {details}")
                    else:
                        failed_checks.append(f"{grader_type} check failed")
            
            if failed_checks:
                # Combine failure messages, truncate if too long
                combined = "; ".join(failed_checks)
                return combined[:250] + ("..." if len(combined) > 250 else "")
        
        # Check for API verifier details (from verifier API script)
        # The API response structure is: {"result": "failed", "details": {...}}
        # The response_data is stored directly in verification_details
        details_obj = verification_details.get("details")
        
        # If not in details, check if api_response exists (legacy structure)
        if not details_obj:
            api_response = verification_details.get("api_response")
            if isinstance(api_response, dict):
                details_obj = api_response.get("details")
        
        if isinstance(details_obj, dict) and details_obj:
            failure_reasons = []
            
            # Check for ticket state issues (DeskZen open/close/restore tasks)
            if "target_in_active" in details_obj:
                target_in_active = details_obj.get("target_in_active", False)
                target_in_deleted = details_obj.get("target_in_deleted", False)
                
                if not target_in_active and target_in_deleted:
                    failure_reasons.append("Task failed: Ticket still in deleted state (not restored to active)")
                elif not target_in_active and not target_in_deleted:
                    failure_reasons.append("Task failed: Target ticket not found in active or deleted lists")
                elif target_in_active and target_in_deleted:
                    failure_reasons.append("Task failed: Ticket incorrectly appears in both active and deleted lists")
                else:
                    # target_in_active is True, target_in_deleted is False - this should pass, but it failed?
                    failure_reasons.append("Task failed: Unexpected verification state (ticket in active but verification failed)")
            
            # Check for agent assignment issues (DeskZen assign tasks)
            if "assigned_agent_name" in details_obj or "expected_agent" in details_obj:
                expected = details_obj.get("expected_agent")
                actual = details_obj.get("assigned_agent_name")
                if expected and actual and expected != actual:
                    failure_reasons.append(f"Task failed: Ticket assigned to wrong agent (expected '{expected}', got '{actual}')")
                elif not actual:
                    failure_reasons.append("Task failed: Ticket not assigned to any agent")
            
            # Check for status/state mismatches
            if "expected_status" in details_obj and "actual_status" in details_obj:
                expected = details_obj.get("expected_status")
                actual = details_obj.get("actual_status")
                if expected != actual:
                    failure_reasons.append(f"Task failed: Expected status '{expected}', got '{actual}'")
            
            # If we found specific reasons, return them
            if failure_reasons:
                return "; ".join(failure_reasons)
            
            # If details exist but we couldn't parse them, provide a summary
            if len(details_obj) > 0:
                # Try to create a meaningful summary from the details
                key_info = []
                for key, value in list(details_obj.items())[:5]:  # First 5 keys
                    if not key.startswith("_") and key not in ["run_id", "timestamp"]:
                        key_info.append(f"{key}={value}")
                if key_info:
                    summary = "Task failed verification: " + ", ".join(key_info)
                    return summary[:250] + ("..." if len(summary) > 250 else "")
        
        # Check verification_summary for additional context
        summary = verification_details.get("verification_summary", "")
        if summary and len(summary) > 10:
            return f"Verification reported failure: {summary[:180]}"
        
        # Fallback - indicate verification completed but task failed
        return "Verification completed: Task requirements not met (check iteration details for specifics)"
    
    @staticmethod
    def group_failures_by_category(
        categorized_failures: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        Group categorized failures by their category.
        
        Args:
            categorized_failures: List of dicts with 'category' key
            
        Returns:
            Dict mapping category names to lists of failures
        """
        grouped = {}
        
        for failure in categorized_failures:
            category = failure.get("category", FailureCategory.UNKNOWN)
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(failure)
        
        return grouped

