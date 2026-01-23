"""
Testing endpoint for GraderConfig verification.

This endpoint allows you to test GraderConfig objects without running a full task.
Simply provide the output from window.get_states() along with your GraderConfig,
and this endpoint will run the verification logic and return the results.

⚠️ NOTE: This endpoint is for testing purposes only and has no authentication.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

from app.schemas.verification import GraderConfig
from app.services.verification.grader_config_verifier import GraderConfigVerifier
from app.services.verification.types import GradingContext

logger = logging.getLogger(__name__)

router = APIRouter()


class GraderTestRequest(BaseModel):
    """Request payload for testing a GraderConfig."""
    
    grader_config: Dict[str, Any] = Field(
        ...,
        description="The GraderConfig object to test",
        example={
            "state_grader_configs": [
                {
                    "path_to_actual": "$.tickets[?(@.id=='2')].is_spam",
                    "assertions": [
                        {
                            "operator": "BOOL",
                            "expected": [True]
                        }
                    ]
                }
            ]
        }
    )
    
    get_states_output: Dict[str, Any] = Field(
        ...,
        description="The output from window.get_states() containing actual_state and expected_states",
        example={
            "actual_state": {
                "tickets": [
                    {"id": "1", "is_spam": False},
                    {"id": "2", "is_spam": True}
                ]
            },
            "expected_states": [
                {"ticket": {"id": "2", "is_spam": True}}
            ]
        }
    )
    
    execution_results: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional execution results for answer/URL grading (contains model_response, final_url, etc.)",
        example={
            "modelResponse": "The ticket has been marked as spam",
            "final_url": "https://example.com/tickets/2"
        }
    )
    
    task_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional task context for additional metadata (task_id, runner_type, etc.)",
        example={
            "task_id": "TEST-001",
            "runner_type": "default"
        }
    )

    class Config:
        json_schema_extra = {
            "example": {
                "grader_config": {
                    "state_grader_configs": [
                        {
                            "path_to_actual": "$.tickets[?(@.id=='2')].is_spam",
                            "assertions": [
                                {
                                    "operator": "BOOL",
                                    "expected": [True]
                                }
                            ]
                        }
                    ]
                },
                "get_states_output": {
                    "actual_state": {
                        "tickets": [
                            {"id": "1", "is_spam": False},
                            {"id": "2", "is_spam": True}
                        ]
                    },
                    "expected_states": [
                        {"ticket": {"id": "2", "is_spam": True}}
                    ]
                },
                "execution_results": {
                    "modelResponse": "I've marked ticket #2 as spam"
                }
            }
        }


class GraderTestResponse(BaseModel):
    """Response from testing a GraderConfig."""
    
    success: bool = Field(..., description="Whether the test ran successfully")
    verification_status: str = Field(..., description="Overall verification status (PASSED/FAILED)")
    verification_summary: str = Field(..., description="Human-readable summary of results")
    grader_results: List[Dict[str, Any]] = Field(..., description="Detailed results from each grader")
    validation_error: Optional[str] = Field(None, description="Validation error if config is invalid")
    execution_error: Optional[str] = Field(None, description="Error that occurred during verification")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "verification_status": "PASSED",
                "verification_summary": "1/1 graders passed",
                "grader_results": [
                    {
                        "type": "state",
                        "ordinal": 1,
                        "passed": True,
                        "details": ["All 1 assertion(s) passed"],
                        "assertions": [
                            {
                                "operator": "equals",
                                "passed": True,
                                "message": "Assertion passed",
                                "expected": [True],
                                "actual": [True]
                            }
                        ]
                    }
                ],
                "validation_error": None,
                "execution_error": None
            }
        }


@router.post("/test", response_model=GraderTestResponse)
async def test_grader_config(request: GraderTestRequest):
    """
    Test a GraderConfig without running a full task.
    
    This endpoint allows you to quickly validate and test your GraderConfig objects
    by providing:
    1. The GraderConfig to test
    2. The output from window.get_states() (or mocked data with the same structure)
    3. Optional execution results for answer/URL grading
    
    The endpoint will run the full verification pipeline and return detailed results
    showing which assertions passed or failed.
    
    **Use Cases:**
    - Quickly iterate on GraderConfig design
    - Test different scenarios without running full tasks
    - Validate assertion logic before deployment
    - Debug failing graders
    
    **Note:** This endpoint has no authentication and is intended for testing only.
    """
    try:
        # Step 1: Validate the GraderConfig
        logger.info("Validating GraderConfig...")
        try:
            config = GraderConfig.model_validate(request.grader_config)
            logger.info("✅ GraderConfig validation passed")
        except Exception as e:
            validation_error = f"Invalid GraderConfig: {str(e)}"
            logger.error(validation_error)
            return GraderTestResponse(
                success=False,
                verification_status="VALIDATION_ERROR",
                verification_summary=validation_error,
                grader_results=[],
                validation_error=validation_error,
                execution_error=None
            )
        
        # Step 2: Build mock task and context
        task = request.task_context or {}
        task["grader_config"] = request.grader_config
        
        execution_results = request.execution_results or {}
        # Inject the get_states output as cached payload (for extract_states_config workflows)
        execution_results["window_get_states_payload"] = request.get_states_output
        # ALSO inject actual_state and expected_states directly (for non-extract_states workflows)
        execution_results["actual_state"] = request.get_states_output.get("actual_state", {})
        execution_results["expected_states"] = request.get_states_output.get("expected_states", [])
        
        context = GradingContext(
            task=task,
            execution_results=execution_results,
            results_dir=None  # No need to save files during testing
        )
        
        # Step 3: Run verification
        logger.info("Running GraderConfig verification...")
        verifier = GraderConfigVerifier(logger=logger)
        
        # Manually collect states and run graders (we'll reuse the verify_task logic)
        # but we need to handle the case where we don't have a real task
        result = verifier.verify_task(
            task=task,
            execution_results=execution_results,
            results_dir=None  # type: ignore - Path is optional for testing
        )
        
        logger.info(f"✅ Verification complete: {result.get('verification_status')}")
        
        return GraderTestResponse(
            success=True,
            verification_status=result.get("verification_status", "UNKNOWN"),
            verification_summary=result.get("verification_summary", ""),
            grader_results=result.get("grader_results", []),
            validation_error=None,
            execution_error=result.get("error")
        )
        
    except Exception as e:
        error_msg = f"Unexpected error during grader test: {str(e)}"
        logger.exception(error_msg)
        return GraderTestResponse(
            success=False,
            verification_status="ERROR",
            verification_summary=error_msg,
            grader_results=[],
            validation_error=None,
            execution_error=error_msg
        )


@router.get("/health")
async def health_check():
    """
    Simple health check endpoint to verify the grader test service is running.
    """
    return {
        "status": "healthy",
        "service": "grader-test",
        "message": "Grader test endpoint is ready to accept requests"
    }

