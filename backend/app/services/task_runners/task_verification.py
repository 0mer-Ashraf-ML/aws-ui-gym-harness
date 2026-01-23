import os
import sys
import json
import time
import logging
import uuid
import warnings
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import urlparse

# Suppress InsecureRequestWarning when using verify=False for staging/self-signed certs
from urllib3.exceptions import InsecureRequestWarning
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

from app.services.verification import GraderConfigVerifier
from app.services.verification.assertion_engine import ConfigurationError


LOCAL_BACKEND_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}

# Cache to avoid repeated health checks for the same base URL
_BACKEND_URL_CACHE = {}


def _check_backend_health(url: str, logger: Optional[logging.Logger] = None, timeout: int = 2) -> bool:
    """
    Check if a backend URL is reachable by making a lightweight request.
    
    Args:
        url: The backend URL to check
        logger: Optional logger for debug info
        timeout: Request timeout in seconds (default: 2)
    
    Returns:
        True if backend is reachable (2xx response), False otherwise
    """
    def _log(level: str, message: str):
        if logger:
            getattr(logger, level, logger.info)(message)
    
    # Try common health check endpoints
    health_endpoints = [
        f"{url}/api/v1/users",  # Most verifiers use this endpoint
        f"{url}/health",
        f"{url}/api/health",
    ]
    
    for endpoint in health_endpoints:
        try:
            _log("debug", f"🏥 Health check: trying {endpoint}")
            # verify=False to handle self-signed or staging SSL certificates
            response = requests.get(endpoint, timeout=timeout, allow_redirects=False, verify=False)
            
            # Accept any 2xx status code (200-299)
            if 200 <= response.status_code < 300:
                _log("debug", f"✅ Health check passed: {endpoint} returned {response.status_code}")
                return True
            else:
                _log("debug", f"⚠️  Health check: {endpoint} returned {response.status_code}")
                
        except requests.exceptions.Timeout:
            _log("debug", f"⏱️  Health check timeout: {endpoint}")
        except requests.exceptions.ConnectionError:
            _log("debug", f"🔌 Health check connection failed: {endpoint}")
        except Exception as e:
            _log("debug", f"❌ Health check error for {endpoint}: {e}")
    
    # All endpoints failed
    _log("debug", f"❌ Health check failed for all endpoints on {url}")
    return False


def resolve_backend_api_base(task_data: Dict[str, Any], logger: Optional[logging.Logger] = None) -> str:
    """
    Resolve the backend API URL for the given gym task.
    
    This function transforms the gym's base URL into an API endpoint URL.
    It supports multiple URL patterns used by different gyms:
    1. Try base_url/api (path pattern)
    2. Try base_url with -api in hostname (hostname pattern)
    
    The URL is sourced from task_data (gym-agnostic), never from environment variables.
    Results are cached to avoid repeated health checks.
    """

    def _log(level: str, message: str):
        if logger:
            getattr(logger, level, logger.info)(message)

    def _normalize(url: str) -> str:
        if not url:
            return ""
        candidate = url.strip()
        if not candidate:
            return ""
        candidate = candidate.rstrip("/")
        if "://" not in candidate:
            candidate = f"https://{candidate}"

        parsed = urlparse(candidate)
        scheme = parsed.scheme or "https"
        host = parsed.hostname or ""
        if not host:
            return candidate.rstrip("/")

        if host in LOCAL_BACKEND_HOSTS:
            # For local backend hosts, prefer known backend port over parsed port
            # This ensures localhost URLs always resolve to the backend API port (8765)
            port = os.getenv("DESKZEN_BACKEND_PORT") or "8765"
            return f"{scheme}://{host}:{port}".rstrip("/")

        port_suffix = f":{parsed.port}" if parsed.port else ""
        return f"{scheme}://{host}{port_suffix}".rstrip("/")

    # Determine source URL from task data (gym-agnostic, no hardcoded URLs)
    candidates = [
        ("backend_api_url", task_data.get("backend_api_url")),
        ("base_url", task_data.get("base_url")),
        ("task_link", task_data.get("task_link")),
    ]

    source_url = None
    source_name = None
    
    for source, raw_url in candidates:
        normalized = _normalize(raw_url)
        if normalized:
            source_url = normalized
            source_name = source
            break

    if not source_url:
        _log("warning", "⚠️ Unable to determine backend API base URL from task metadata")
        return ""

    # Check cache first
    cache_key = source_url
    if cache_key in _BACKEND_URL_CACHE:
        cached_url = _BACKEND_URL_CACHE[cache_key]
        _log("info", f"🔧 Backend API base resolved from {source_name} (cached): {cached_url}")
        return cached_url

    # For localhost URLs, skip health check and return immediately
    parsed = urlparse(source_url)
    if parsed.hostname in LOCAL_BACKEND_HOSTS:
        _log("info", f"🔧 Backend API base resolved from {source_name}: {source_url}")
        _BACKEND_URL_CACHE[cache_key] = source_url
        return source_url

    # For non-.turing.com domains, use as-is without health check
    if not parsed.hostname or not parsed.hostname.endswith(".turing.com"):
        _log("info", f"🔧 Backend API base resolved from {source_name}: {source_url}")
        _BACKEND_URL_CACHE[cache_key] = source_url
        return source_url

    # For .turing.com domains, try multiple patterns with health checks
    _log("info", f"🔍 Trying multiple URL patterns for {source_url}")
    
    # Pattern 1: Append /api to path (e.g., https://aws-deskzen-prod.turing.com/api)
    url_with_api_path = f"{source_url}/api"
    
    # Pattern 2: Add -api to hostname (e.g., https://aws-deskzen-prod-api.turing.com)
    url_with_api_hostname = source_url
    if "-api." not in parsed.hostname:
        hostname_with_api = parsed.hostname.replace(".turing.com", "-api.turing.com")
        port_suffix = f":{parsed.port}" if parsed.port else ""
        url_with_api_hostname = f"{parsed.scheme}://{hostname_with_api}{port_suffix}"
    
    # Try each pattern with health check
    url_patterns = [
        ("path pattern (/api)", url_with_api_path),
        ("hostname pattern (-api)", url_with_api_hostname),
    ]
    
    def _strip_api_suffix(url: str) -> str:
        """
        Strip /api suffix from URL path to ensure consistency.
        Callers (db_snapshots, verifiers) will append /api/v1/... themselves.
        
        Examples:
        - https://aws-deskzen-prod.turing.com/api -> https://aws-deskzen-prod.turing.com
        - https://aws-ui-gym-deskzen-api.turing.com -> https://aws-ui-gym-deskzen-api.turing.com
        """
        parsed_url = urlparse(url)
        if parsed_url.path == '/api' or parsed_url.path == '/api/':
            # Strip /api from path
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            _log("debug", f"🔧 Stripped /api suffix: {url} -> {base_url}")
            return base_url
        return url
    
    for pattern_name, pattern_url in url_patterns:
        _log("info", f"🔍 Trying {pattern_name}: {pattern_url}")
        
        if _check_backend_health(pattern_url, logger):
            # Strip /api suffix before returning (callers will add /api/v1/... themselves)
            base_url = _strip_api_suffix(pattern_url)
            _log("info", f"✅ {pattern_name} succeeded: {pattern_url}")
            _log("info", f"🔧 Backend API base resolved from {source_name}: {base_url}")
            _BACKEND_URL_CACHE[cache_key] = base_url
            return base_url
        else:
            _log("info", f"❌ {pattern_name} failed: {pattern_url}")
    
    # All patterns failed - use first pattern as fallback for backward compatibility
    fallback_url = _strip_api_suffix(url_with_api_path)
    _log("warning", f"⚠️ All URL patterns failed health check, using fallback: {fallback_url}")
    _log("info", f"🔧 Backend API base resolved from {source_name}: {fallback_url}")
    _BACKEND_URL_CACHE[cache_key] = fallback_url
    return fallback_url


class TaskVerification:
    """Task verification functionality for API-based and manual verification"""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.run_id = self._generate_run_id()
        self.current_auth_token = None  # Add auth token storage
        self.logger.info(f"🆔 Generated Run ID: {self.run_id}")
    
    def _generate_run_id(self) -> str:
        """Generate a 16-digit unique run ID"""
        # Generate UUID and take first 16 characters
        unique_id = str(uuid.uuid4()).replace('-', '')[:16]
        return f"run_{unique_id}"
    
    def set_auth_token(self, token: str):
        """Set the current auth token for verification calls"""
        self.current_auth_token = token
        self.logger.info("✅ Auth token set for verification")
    
    def get_auth_token(self) -> Optional[str]:
        """Get the current auth token"""
        return self.current_auth_token
        
    def _add_run_id_to_url(self, url: str, verification_strategy: str = None) -> str:
        """Add run_id parameter to URL based on verification strategy"""
        if not url:
            return url
        
        # Ensure verification_strategy is lowercase string (handle enum conversion)
        if verification_strategy:
            if hasattr(verification_strategy, 'value'):
                verification_strategy = verification_strategy.value
            elif isinstance(verification_strategy, str):
                verification_strategy = verification_strategy.lower()
        
        # For local_storage_assertions strategy, don't add run_id to URL
        if verification_strategy == "local_storage_assertions":
            return url
            
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}run_id={self.run_id}"
    
    def _backend_verification(self, task: Dict[str, Any], execution_results: Dict) -> Dict[str, Any]:
        """Backend verification method using API call - separate from existing verification"""
        self.logger.info(f"🔍 Starting backend verification for task: {task['task_id']}")
        
        backend_verification_start_time = time.time()
        backend_verification_results = {
            'task_id': task['task_id'],
            'run_id': self.run_id,
            'verification_method': 'backend_api',
            'verification_completed': False,
            'verification_status': 'Unknown',
            'verification_summary': 'Backend verification attempted',
            'verification_time': 0,
            'verification_comments': '',
            'api_response': None,
            'api_error': None
        }
        
        try:
            # Prepare API call parameters
            api_params = {
                "run_id": self.run_id,
                "prompt_id": f"{task['task_id']}"
            }
            
            # Generate verification URL from gym's base URL
            base_url = task.get('base_url', '')
            if base_url:
                # Remove trailing slash from base_url if present
                base_url = base_url.rstrip('/')
                # Construct verification URL
                verification_api_url = f"{base_url}/api/v1/run/verify"
                self.logger.info(f"🔗 Generated verification URL from base URL: {verification_api_url}")
            else:
                # Fallback to localhost if no base URL
                verification_api_url = "http://localhost:3001/api/v1/run/verify"
                self.logger.warning(f"⚠️ No base_url found in task data, using fallback: {verification_api_url}")
            
            # Make API call to verification endpoint
            self.logger.info(f"🌐 Making backend verification API call to: {verification_api_url}")
            self.logger.info(f"📋 API Parameters: {api_params}")
            self.logger.info(f"🔗 Full API URL: {verification_api_url}?{requests.compat.urlencode(api_params)}")
            self.logger.info(f"⏱️  API call timeout: 30 seconds")
            
            # Log the actual request being made
            self.logger.info(f"📤 Sending GET request to verification API...")
            
            response = requests.get(
                verification_api_url,
                params=api_params,
                timeout=30,  # 30 second timeout
                verify=False  # Handle self-signed/staging SSL certificates
            )
            
            # Log the response details
            self.logger.info(f"📥 API Response received:")
            self.logger.info(f"   Status Code: {response.status_code}")
            self.logger.info(f"   Response Message: {response.reason}")
            self.logger.info(f"   Response Headers: {dict(response.headers)}")
            self.logger.info(f"   Response Size: {len(response.content)} bytes")
            self.logger.info(f"   Response Time: {response.elapsed.total_seconds():.3f}s")
            
            # Log the raw response text for debugging
            if response.text:
                self.logger.info(f"📄 Raw Response Text: {response.text[:500]}...")
            else:
                self.logger.info(f"📄 Raw Response Text: (empty)")
            
            # Use raise_for_status() to catch HTTP errors - mark as CRASHED
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as http_error:
                self.logger.error(f"❌ Verify endpoint API returned error status: {http_error}")
                backend_verification_results['verification_status'] = 'CRASHED'
                backend_verification_results['verification_summary'] = f'API returned status code: {response.status_code}'
                backend_verification_results['verification_completed'] = True
                backend_verification_results['verification_time'] = time.time() - backend_verification_start_time
                backend_verification_results['api_response'] = {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'content': response.text[:1000] if response.text else None,
                    'response_time': response.elapsed.total_seconds(),
                    'response_size': len(response.content),
                    'full_url': f"{verification_api_url}?{requests.compat.urlencode(api_params)}",
                    'error': str(http_error)
                }
                return backend_verification_results
            
            # Parse JSON response - if it fails, mark as CRASHED
            try:
                response_data = response.json()
            except json.JSONDecodeError as json_error:
                self.logger.error(f"❌ Failed to parse verify endpoint response JSON: {json_error}")
                backend_verification_results['verification_status'] = 'CRASHED'
                backend_verification_results['verification_summary'] = f'Invalid JSON response: {response.text[:200]}'
                backend_verification_results['verification_completed'] = True
                backend_verification_results['verification_time'] = time.time() - backend_verification_start_time
                backend_verification_results['api_response'] = {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'content': response.text[:1000] if response.text else None,
                    'response_time': response.elapsed.total_seconds(),
                    'response_size': len(response.content),
                    'full_url': f"{verification_api_url}?{requests.compat.urlencode(api_params)}",
                    'error': f'JSON decode error: {str(json_error)}'
                }
                return backend_verification_results
            
            # API call successful - parse response data
            self.logger.info(f"✅ API call successful (HTTP {response.status_code})")
            self.logger.info(f"📋 Parsed JSON response data: {json.dumps(response_data, indent=2, default=str)}")
            
            # Extract verification status from response
            self.logger.info(f"🔍 Analyzing response for verification status...")
            self.logger.info(f"📋 Available fields in response: {list(response_data.keys())}")
            
            # Check for the specific API response format: {"prompt_id": "abc123", "result": "passed"}
            if 'result' in response_data:
                result_value = response_data['result']
                self.logger.info(f"📊 Found 'result' field: {result_value}")
                
                if result_value.lower() == 'passed':
                    response_data['verification_status'] = 'PASSED'
                    self.logger.info(f"✅ Result indicates PASSED: {result_value}")
                elif result_value.lower() == 'failed':
                    response_data['verification_status'] = 'FAILED'
                    self.logger.info(f"❌ Result indicates FAILED: {result_value}")
                else:
                    self.logger.warning(f"⚠️ Unknown result value: {result_value}, defaulting to FAILED")
                    response_data['verification_status'] = 'FAILED'
            
            # Fallback to other common field names if 'result' is not found
            elif 'status' in response_data:
                status_value = response_data['status']
                self.logger.info(f"📊 Found 'status' field: {status_value}")
                if status_value.upper() in ['PASSED', 'SUCCESS', 'COMPLETED']:
                    response_data['verification_status'] = 'PASSED'
                    self.logger.info(f"✅ Status indicates PASSED: {status_value}")
                else:
                    response_data['verification_status'] = 'FAILED'
                    self.logger.info(f"❌ Status indicates FAILED: {status_value}")
            elif 'verification_status' in response_data:
                status_value = response_data['verification_status']
                self.logger.info(f"📊 Found 'verification_status' field: {status_value}")
                if status_value.upper() in ['PASSED', 'SUCCESS', 'COMPLETED']:
                    response_data['verification_status'] = 'PASSED'
                    self.logger.info(f"✅ Verification status indicates PASSED: {status_value}")
                else:
                    response_data['verification_status'] = 'FAILED'
                    self.logger.info(f"❌ Verification status indicates FAILED: {status_value}")
            else:
                # Default to CRASHED if no clear status - missing expected fields indicates system issue
                self.logger.error(f"❌ No 'result', 'status', or 'verification_status' field found in response")
                self.logger.info(f"📋 Available fields: {list(response_data.keys())}")
                # Return error structure for crash case
                backend_verification_results['verification_status'] = 'CRASHED'
                backend_verification_results['verification_summary'] = 'No status field found in API response'
                backend_verification_results['verification_completed'] = True
                backend_verification_results['verification_time'] = time.time() - backend_verification_start_time
                backend_verification_results['api_response'] = {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'content': response.text[:1000] if response.text else None,
                    'response_time': response.elapsed.total_seconds(),
                    'response_size': len(response.content),
                    'full_url': f"{verification_api_url}?{requests.compat.urlencode(api_params)}",
                    'error': 'No status field found in response',
                    'available_fields': list(response_data.keys())
                }
                return backend_verification_results
            
            # Check for assertion_results and generate comments if present
            if 'assertion_results' in response_data:
                assertion_results = response_data['assertion_results']
                self.logger.info(f"📊 Found 'assertion_results' field with {len(assertion_results)} assertions")
                
                if isinstance(assertion_results, list) and len(assertion_results) > 0:
                    verification_comments = self._generate_verify_endpoint_comments(assertion_results)
                    response_data['verification_comments'] = verification_comments
                    self.logger.info(f"📝 Generated verification comments: {len(verification_comments)} characters")
                else:
                    self.logger.info(f"ℹ️ assertion_results is empty or not a list")
                    response_data['verification_comments'] = ''
            else:
                self.logger.info(f"ℹ️ No 'assertion_results' field found in response")
                response_data['verification_comments'] = ''
            
            response_data['verification_completed'] = True
            self.logger.info(f"✅ Backend verification completed: {response_data.get('verification_status', 'UNKNOWN')}")
            
            # Return only the JSON response data for verification.json
            return response_data
                
        except requests.exceptions.Timeout:
            self.logger.error(f"❌ Backend verification API call timed out")
            backend_verification_results['verification_status'] = 'CRASHED'
            backend_verification_results['verification_summary'] = 'API call timed out'
            backend_verification_results['api_error'] = 'timeout'
            
        except requests.exceptions.ConnectionError:
            self.logger.error(f"❌ Backend verification API connection failed - server may not be running")
            backend_verification_results['verification_status'] = 'CRASHED'
            backend_verification_results['verification_summary'] = 'API connection failed - server may not be running'
            backend_verification_results['api_error'] = 'connection_error'
            
        except Exception as api_error:
            self.logger.error(f"❌ Backend verification API call failed: {api_error}")
            backend_verification_results['verification_status'] = 'CRASHED'
            backend_verification_results['verification_summary'] = f'API call failed: {str(api_error)}'
            backend_verification_results['api_error'] = str(api_error)
        
        # Calculate verification time
        backend_verification_results['verification_time'] = time.time() - backend_verification_start_time
        
        # Log comprehensive verification summary
        self.logger.info("=" * 80)
        self.logger.info("🔍 BACKEND VERIFICATION COMPLETE - FINAL SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"📋 Task ID: {backend_verification_results['task_id']}")
        self.logger.info(f"🆔 Run ID: {backend_verification_results['run_id']}")
        self.logger.info(f"⏱️  Total Time: {backend_verification_results['verification_time']:.3f}s")
        self.logger.info(f"📊 Final Status: {backend_verification_results['verification_status']}")
        self.logger.info(f"✅ Completed: {backend_verification_results['verification_completed']}")
        self.logger.info(f"🔗 Method: {backend_verification_results['verification_method']}")
        
        if backend_verification_results.get('api_response'):
            api_resp = backend_verification_results['api_response']
            self.logger.info(f"🌐 API Response Details:")
            self.logger.info(f"   Status Code: {api_resp.get('status_code', 'N/A')}")
            self.logger.info(f"   Response Time: {api_resp.get('response_time', 'N/A')}s")
            self.logger.info(f"   Response Size: {api_resp.get('response_size', 'N/A')} bytes")
            self.logger.info(f"   Full URL: {api_resp.get('full_url', 'N/A')}")
        
        if backend_verification_results.get('verification_summary'):
            summary = backend_verification_results['verification_summary']
            self.logger.info(f"📝 Verification Summary: {summary[:300]}...")
        
        if backend_verification_results.get('api_error'):
            self.logger.error(f"❌ API Error: {backend_verification_results['api_error']}")
        
        self.logger.info("=" * 80)
        
        return backend_verification_results
    
    def _local_storage_assertions_verification(self, task: Dict[str, Any], execution_results: Dict, results_dir: Path) -> Dict[str, Any]:
        """Local storage assertions verification method"""
        self.logger.info(f"🔍 Starting local storage assertions verification for task: {task['task_id']}")
        
        verification_start_time = time.time()
        verification_results = {
            'task_id': task['task_id'],
            'run_id': self.run_id,
            'verification_method': 'local_storage_assertions',
            'verification_completed': False,
            'verification_status': 'Unknown',
            'verification_summary': 'Local storage assertions verification attempted',
            'verification_time': 0,
            'verification_comments': '',
            'actual_state_response': None,
            'expected_state_response': None,
            'api_error': None
        }
        
        try:
            # Find localStorageDump file in execution results
            localStorageDump = None
            if 'localStorageDump' in execution_results:
                localStorageDump = execution_results['localStorageDump']
            else:
                # Try to find it in the results directory - look for the actual filename pattern
                localStorage_files = list(results_dir.glob("*local_storage_dump*"))
                if not localStorage_files:
                    # Fallback to broader pattern
                    localStorage_files = list(results_dir.glob("*localStorage*"))
                if not localStorage_files:
                    # Another fallback for underscore pattern
                    localStorage_files = list(results_dir.glob("*local*storage*"))
                
                if localStorage_files:
                    self.logger.info(f"📁 Found localStorage file: {localStorage_files[0]}")
                    with open(localStorage_files[0], 'r') as f:
                        localStorageDump = f.read()
                else:
                    self.logger.warning(f"⚠️ No localStorage files found in {results_dir}")
                    self.logger.info(f"📁 Available files: {list(results_dir.glob('*'))}")
            
            if not localStorageDump:
                self.logger.error("❌ No localStorageDump found for local storage assertions verification - marking task as CRASHED")
                verification_results['verification_status'] = 'CRASHED'
                verification_results['verification_summary'] = 'No localStorageDump found - task crashed'
                verification_results['verification_completed'] = True
                return verification_results
            
            # Get base URL from task
            base_url = task.get('base_url', '')
            if not base_url:
                self.logger.error("❌ No base_url found in task data for local storage assertions verification")
                verification_results['verification_status'] = 'FAILED'
                verification_results['verification_summary'] = 'No base_url found in task data'
                return verification_results
            
            # Remove trailing slash from base_url if present
            base_url = base_url.rstrip('/')
            
            # Call get_actual_state endpoint
            actual_state_url = f"{base_url}/api/v1/get_actual_state"
            
            # Prepare form data for file upload (same as curl --form)
            form_data = {
                "taskId": task['task_id']
            }
            
            # Attach the final model response if available
            try:
                model_response = self._extract_final_model_response(execution_results, results_dir)
                model_response_present = bool(model_response)
                self.logger.info(f"🔎 modelResponse present (form): {model_response_present}")
                if model_response_present:
                    # Extract task completion response if "Task Completed:" is present
                    processed_model_response = self._extract_task_completion_response(model_response)
                    preview = (processed_model_response[:200] + '...') if len(processed_model_response) > 200 else processed_model_response
                    self.logger.info(f"📝 modelResponse preview (form): {preview}")
                    form_data["modelResponse"] = processed_model_response
                    self.logger.info("📝 Included modelResponse in actual state form data")
                else:
                    self.logger.info("ℹ️ No modelResponse detected to include in form data")
            except Exception as e:
                self.logger.warning(f"⚠️ Could not attach modelResponse: {e}")
            
            # Create a temporary file-like object for the localStorageDump
            import io
            localStorage_file = io.StringIO(localStorageDump)
            
            files = {
                "localStorageDump": ("local_storage_dump.json", localStorage_file, "application/json")
            }
            
            self.logger.info(f"🌐 Making actual state API call to: {actual_state_url}")
            self.logger.info(f"📤 Sending localStorageDump as file upload")
            actual_response = requests.post(actual_state_url, data=form_data, files=files, timeout=30, verify=False)
            
            # Use raise_for_status() to catch HTTP errors - mark as CRASHED
            try:
                actual_response.raise_for_status()
            except requests.exceptions.HTTPError as http_error:
                self.logger.error(f"❌ Actual state API returned error status: {http_error}")
                verification_results['verification_status'] = 'CRASHED'
                verification_results['verification_summary'] = f'Actual state API returned status code: {actual_response.status_code}'
                verification_results['verification_completed'] = True
                verification_results['verification_time'] = time.time() - verification_start_time
                verification_results['api_response'] = {
                    'status_code': actual_response.status_code,
                    'headers': dict(actual_response.headers),
                    'content': actual_response.text[:1000] if actual_response.text else None,
                    'response_time': actual_response.elapsed.total_seconds(),
                    'response_size': len(actual_response.content),
                    'full_url': actual_state_url,
                    'form_data': form_data,
                    'files': {"localStorageDump": "local_storage_dump.json (file upload)"},
                    'error': str(http_error)
                }
                return verification_results
            
            # Parse JSON response - if it fails, mark as CRASHED
            try:
                actual_data = actual_response.json()
            except json.JSONDecodeError as json_error:
                self.logger.error(f"❌ Failed to parse actual state response JSON: {json_error}")
                verification_results['verification_status'] = 'CRASHED'
                verification_results['verification_summary'] = 'Invalid JSON in actual state response'
                verification_results['verification_completed'] = True
                verification_results['verification_time'] = time.time() - verification_start_time
                verification_results['api_response'] = {
                    'status_code': actual_response.status_code,
                    'headers': dict(actual_response.headers),
                    'content': actual_response.text[:1000] if actual_response.text else None,
                    'response_time': actual_response.elapsed.total_seconds(),
                    'response_size': len(actual_response.content),
                    'full_url': actual_state_url,
                    'form_data': form_data,
                    'files': {"localStorageDump": "local_storage_dump.json (file upload)"},
                    'error': f'JSON decode error: {str(json_error)}'
                }
                return verification_results
            
            # Call get_expected_state endpoint (no raise_for_status - not critical)
            expected_state_url = f"{base_url}/api/v1/get_expected_state"
            expected_state_payload = {
                "taskId": task['task_id']
            }
            
            self.logger.info(f"🌐 Making expected state API call to: {expected_state_url}")
            expected_response = requests.post(expected_state_url, json=expected_state_payload, timeout=30, verify=False)
            
            # If we could not include a model response, and expected assertions require LLM rubric judge, crash early
            try:
                if not model_response_present and expected_response.status_code == 200:
                    self.logger.info("🔎 Evaluating expected assertions for LLM_RUBRIC_JUDGE requirement (form)")
                    expected_json = expected_response.json()
                    assertions = expected_json.get('assertions', []) if isinstance(expected_json, dict) else []
                    rubric_count = sum(1 for a in assertions if isinstance(a, dict) and a.get('operator') == 'LLM_RUBRIC_JUDGE')
                    requires_model = rubric_count > 0
                    self.logger.info(f"📊 Assertions count: {len(assertions)}, LLM_RUBRIC_JUDGE count: {rubric_count}")
                    if requires_model:
                        self.logger.error("❌ Missing modelResponse while expected assertions require LLM_RUBRIC_JUDGE. Marking as CRASHED.")
                        verification_results['verification_status'] = 'CRASHED'
                        verification_results['verification_summary'] = 'Model response missing for LLM_RUBRIC_JUDGE assertions'
                        verification_results['verification_completed'] = True
                        verification_results['verification_time'] = time.time() - verification_start_time
                        return verification_results
            except Exception as e:
                # Non-fatal; continue normal flow
                self.logger.warning(f"⚠️ Could not evaluate expected assertions for rubric requirement (form): {e}")
            
            # Parse assertions from actual state response
            assertions = actual_data.get('assertions', [])
            
            # Get expected state data for assertion titles
            expected_data = None
            if expected_response.status_code == 200:
                try:
                    expected_data = expected_response.json()
                except json.JSONDecodeError:
                    self.logger.warning("⚠️ Could not parse expected state response JSON")
            
            # Generate verification comments
            verification_comments = self._generate_verification_comments(assertions, expected_data)
            
            if not assertions:
                self.logger.warning("⚠️ No assertions found in actual state response")
                # Return actual_data with verification status info
                actual_data['verification_status'] = 'FAILED'
                actual_data['verification_summary'] = 'No assertions found in response'
                actual_data['verification_comments'] = verification_comments
                return actual_data
            else:
                # Check if all assertions pass
                all_passed = all(assertion.get('result') == 'pass' for assertion in assertions)
                
                if all_passed:
                    actual_data['verification_status'] = 'PASSED'
                    actual_data['verification_summary'] = f'All {len(assertions)} assertions passed'
                else:
                    actual_data['verification_status'] = 'FAILED'
                    failed_count = sum(1 for assertion in assertions if assertion.get('result') != 'pass')
                    actual_data['verification_summary'] = f'{failed_count}/{len(assertions)} assertions failed'
                
                actual_data['verification_comments'] = verification_comments
                actual_data['verification_completed'] = True
                
                # Return only the JSON response data for verification.json
                return actual_data
                
        except requests.exceptions.Timeout:
            self.logger.error("❌ Local storage assertions verification API call timed out")
            verification_results['verification_status'] = 'CRASHED'
            verification_results['verification_summary'] = 'API call timed out'
            verification_results['api_error'] = 'timeout'
            
        except requests.exceptions.ConnectionError:
            self.logger.error("❌ Local storage assertions verification API connection failed")
            verification_results['verification_status'] = 'CRASHED'
            verification_results['verification_summary'] = 'API connection failed'
            verification_results['api_error'] = 'connection_error'
            
        except Exception as e:
            self.logger.error(f"❌ Local storage assertions verification failed: {e}")
            verification_results['verification_status'] = 'CRASHED'
            verification_results['verification_summary'] = f'Verification failed: {str(e)}'
            verification_results['api_error'] = str(e)
        
        verification_results['verification_time'] = time.time() - verification_start_time
        return verification_results
    
    def _run_id_assertions_verification(self, task: Dict[str, Any], execution_results: Dict, results_dir: Path) -> Dict[str, Any]:
        """Run ID assertions verification method"""
        self.logger.info(f"🔍 Starting run ID assertions verification for task: {task['task_id']}")
        
        verification_start_time = time.time()
        verification_results = {
            'task_id': task['task_id'],
            'run_id': self.run_id,
            'verification_method': 'run_id_assertions',
            'verification_completed': False,
            'verification_status': 'Unknown',
            'verification_summary': 'Run ID assertions verification attempted',
            'verification_time': 0,
            'verification_comments': '',
            'actual_state_response': None,
            'expected_state_response': None,
            'api_error': None
        }
        
        try:
            # Get base URL from task
            base_url = task.get('base_url', '')
            if not base_url:
                self.logger.error("❌ No base_url found in task data for run ID assertions verification")
                verification_results['verification_status'] = 'FAILED'
                verification_results['verification_summary'] = 'No base_url found in task data'
                return verification_results
            
            # Remove trailing slash from base_url if present
            base_url = base_url.rstrip('/')
            
            # Call get_actual_state endpoint with run_id
            actual_state_url = f"{base_url}/api/v1/get_actual_state"
            actual_state_payload = {
                "taskId": task['task_id'],
                "run_id": self.run_id
            }
            
            # Attach the final model response if available
            try:
                model_response = self._extract_final_model_response(execution_results, results_dir)
                model_response_present = bool(model_response)
                self.logger.info(f"🔎 modelResponse present (json): {model_response_present}")
                if model_response_present:
                    preview = (model_response[:200] + '...') if len(model_response) > 200 else model_response
                    self.logger.info(f"📝 modelResponse preview (json): {preview}")
                    actual_state_payload["modelResponse"] = model_response
                    self.logger.info("📝 Included modelResponse in actual state JSON payload")
                else:
                    self.logger.info("ℹ️ No modelResponse detected to include in JSON payload")
            except Exception as e:
                self.logger.warning(f"⚠️ Could not attach modelResponse to JSON payload: {e}")
            
            self.logger.info(f"🌐 Making actual state API call to: {actual_state_url}")
            actual_response = requests.post(actual_state_url, json=actual_state_payload, timeout=30, verify=False)
            
            # Store actual state API response details (same format as verify endpoint)
            verification_results['api_response'] = {
                'status_code': actual_response.status_code,
                'headers': dict(actual_response.headers),
                'content': actual_response.text[:1000] if actual_response.text else None,
                'response_time': actual_response.elapsed.total_seconds(),
                'response_size': len(actual_response.content),
                'full_url': actual_state_url,
                'payload': actual_state_payload
            }
            
            # Call get_expected_state endpoint
            expected_state_url = f"{base_url}/api/v1/get_expected_state"
            expected_state_payload = {
                "taskId": task['task_id']
            }
            
            self.logger.info(f"🌐 Making expected state API call to: {expected_state_url}")
            expected_response = requests.post(expected_state_url, json=expected_state_payload, timeout=30, verify=False)
            
            # Store expected state API response details
            verification_results['expected_state_response'] = {
                'status_code': expected_response.status_code,
                'headers': dict(expected_response.headers),
                'content': expected_response.text[:1000] if expected_response.text else None,
                'response_time': expected_response.elapsed.total_seconds(),
                'response_size': len(expected_response.content),
                'full_url': expected_state_url,
                'payload': expected_state_payload
            }

            # If we could not include a model response, and expected assertions require LLM rubric judge, crash early
            try:
                if not model_response_present and expected_response.status_code == 200:
                    self.logger.info("🔎 Evaluating expected assertions for LLM_RUBRIC_JUDGE requirement (json)")
                    expected_json = expected_response.json()
                    assertions = expected_json.get('assertions', []) if isinstance(expected_json, dict) else []
                    rubric_count = sum(1 for a in assertions if isinstance(a, dict) and a.get('operator') == 'LLM_RUBRIC_JUDGE')
                    requires_model = rubric_count > 0
                    self.logger.info(f"📊 Assertions count: {len(assertions)}, LLM_RUBRIC_JUDGE count: {rubric_count}")
                    if requires_model:
                        self.logger.error("❌ Missing modelResponse while expected assertions require LLM_RUBRIC_JUDGE. Marking as CRASHED.")
                        verification_results['verification_status'] = 'CRASHED'
                        verification_results['verification_summary'] = 'Model response missing for LLM_RUBRIC_JUDGE assertions'
                        verification_results['verification_completed'] = True
                        verification_results['verification_time'] = time.time() - verification_start_time
                        return verification_results
            except Exception as e:
                # Non-fatal; continue normal flow
                self.logger.warning(f"⚠️ Could not evaluate expected assertions for rubric requirement (json): {e}")
            
            # Save responses to files (same format as verify endpoint)
            actual_state_file = results_dir / "actual_state.json"
            expected_state_file = results_dir / "expected_state.json"
            
            with open(actual_state_file, 'w') as f:
                json.dump(verification_results['api_response'], f, indent=2, default=str)
            
            with open(expected_state_file, 'w') as f:
                json.dump(verification_results['expected_state_response'], f, indent=2, default=str)
            
            # Parse assertions from actual state response
            if actual_response.status_code == 200:
                try:
                    actual_data = actual_response.json()
                    assertions = actual_data.get('assertions', [])
                    
                    # Get expected state data for assertion titles
                    expected_data = None
                    if expected_response.status_code == 200:
                        try:
                            expected_data = expected_response.json()
                        except json.JSONDecodeError:
                            self.logger.warning("⚠️ Could not parse expected state response JSON")
                    
                    # Generate verification comments
                    verification_results['verification_comments'] = self._generate_verification_comments(assertions, expected_data)
                    
                    if not assertions:
                        self.logger.warning("⚠️ No assertions found in actual state response")
                        verification_results['verification_status'] = 'FAILED'
                        verification_results['verification_summary'] = 'No assertions found in response'
                    else:
                        # Check if all assertions pass
                        all_passed = all(assertion.get('result') == 'pass' for assertion in assertions)
                        
                        if all_passed:
                            verification_results['verification_status'] = 'PASSED'
                            verification_results['verification_summary'] = f'All {len(assertions)} assertions passed'
                        else:
                            verification_results['verification_status'] = 'FAILED'
                            failed_count = sum(1 for assertion in assertions if assertion.get('result') != 'pass')
                            verification_results['verification_summary'] = f'{failed_count}/{len(assertions)} assertions failed'
                        
                        verification_results['verification_completed'] = True
                        
                except json.JSONDecodeError:
                    self.logger.error("❌ Invalid JSON in actual state response")
                    verification_results['verification_status'] = 'FAILED'
                    verification_results['verification_summary'] = 'Invalid JSON in actual state response'
            else:
                self.logger.error(f"❌ Actual state API returned status code: {actual_response.status_code}")
                verification_results['verification_status'] = 'FAILED'
                verification_results['verification_summary'] = f'Actual state API returned status code: {actual_response.status_code}'
                
        except requests.exceptions.Timeout:
            self.logger.error("❌ Run ID assertions verification API call timed out")
            verification_results['verification_status'] = 'FAILED'
            verification_results['verification_summary'] = 'API call timed out'
            verification_results['api_error'] = 'timeout'
            
        except requests.exceptions.ConnectionError:
            self.logger.error("❌ Run ID assertions verification API connection failed")
            verification_results['verification_status'] = 'FAILED'
            verification_results['verification_summary'] = 'API connection failed'
            verification_results['api_error'] = 'connection_error'
            
        except Exception as e:
            self.logger.error(f"❌ Run ID assertions verification failed: {e}")
            verification_results['verification_status'] = 'FAILED'
            verification_results['verification_summary'] = f'Verification failed: {str(e)}'
            verification_results['api_error'] = str(e)
        
        verification_results['verification_time'] = time.time() - verification_start_time
        return verification_results
        
    def _extract_task_completion_response(self, model_response: str) -> str:
        """Extract the natural response from the model.
        
        Args:
            model_response: The full model response text
            
        Returns:
            The natural response from the model
        """
        if not model_response or not isinstance(model_response, str):
            return model_response or ""
        
        # Return the full natural response without any special parsing
        self.logger.info(f"🎯 Using natural model response: {model_response[:100]}...")
        return model_response

    def _extract_final_model_response(self, execution_results: Dict[str, Any], results_dir: Path) -> str:
        """Best-effort extraction of the final model response for inclusion in verification calls.
        Priority order:
        1) Directly from execution_results common keys
        2) From conversation history files in results_dir
        3) From task_responses files in results_dir
        Returns empty string if nothing substantial is found.
        """
        try:
            # 1) Look for common keys in execution_results
            candidate_keys = [
                "modelResponse",
                "finalModelResponse",
                "final_response",
                "assistant_message",
                "finalMessage",
            ]
            for key in candidate_keys:
                value = execution_results.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            
            # 2) Look into conversation_history for last assistant content
            if results_dir and results_dir.exists():
                from pathlib import Path as _Path
                conversation_dir = _Path(results_dir) / "conversation_history"
                if conversation_dir.exists():
                    for conv_file in sorted(conversation_dir.glob("*_task_execution_conversation.json")):
                        try:
                            with open(conv_file, "r", encoding="utf-8", errors="ignore") as f:
                                conv_data = json.load(f)
                            messages = conv_data if isinstance(conv_data, list) else conv_data.get("messages", [])
                            conversation_flow = conv_data.get("conversation_flow", []) if isinstance(conv_data, dict) else []
                            # Check conversation_flow first
                            if conversation_flow:
                                for item in reversed(conversation_flow):
                                    if isinstance(item, dict) and item.get("role") == "assistant" and item.get("content"):
                                        content = item["content"]
                                        if isinstance(content, str) and content.strip():
                                            return content.strip()
                            # Fallback to messages
                            for msg in reversed(messages):
                                if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content"):
                                    content = msg["content"]
                                    if isinstance(content, str) and content.strip():
                                        return content.strip()
                                    if isinstance(content, list):
                                        for block in content:
                                            if isinstance(block, dict) and block.get("type") == "text":
                                                text = block.get("text", "")
                                                if text and text.strip():
                                                    return text.strip()
                        except Exception:
                            continue
                        break  # Only need the newest file
                
                # 3) Check task_responses for assistant message content
                task_responses_dir = _Path(results_dir) / "task_responses"
                if task_responses_dir.exists():
                    for response_file in sorted(task_responses_dir.glob("*.json")):
                        try:
                            with open(response_file, "r", encoding="utf-8", errors="ignore") as f:
                                response_data = json.load(f)
                            item_summary = response_data.get("item_summary", [])
                            for item in reversed(item_summary):
                                if item.get("type") == "message" and item.get("role") == "assistant":
                                    content = item.get("content") or item.get("content_preview")
                                    if isinstance(content, str) and content.strip():
                                        return content.strip()
                        except Exception:
                            continue
                        break
        except Exception as e:
            self.logger.warning(f"⚠️ _extract_final_model_response failed: {e}")
        return ""

    def execute_api_verification_step(
        self, 
        task: Dict[str, Any], 
        execution_results: Dict, 
        results_dir: Path,
        browser_computer: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Execute API-based verification step"""
        self.logger.info(f"🔍 Starting API-based verification step for task: {task['task_id']}")
        self.logger.info(f"🔍 Task description: {task.get('task_description', 'N/A')}")
        self.logger.info(f"🔍 Execution results: {execution_results}")
        
        verification_start_time = time.time()
        
        try:
            # Determine verification strategy
            verification_strategy = task.get('verification_strategy', 'verification_endpoint')
            
            # Ensure verification_strategy is lowercase string (handle enum conversion)
            if hasattr(verification_strategy, 'value'):
                verification_strategy = verification_strategy.value
            elif isinstance(verification_strategy, str):
                verification_strategy = verification_strategy.lower()
            
            self.logger.info(f"🔍 Using verification strategy: {verification_strategy}")
            
            # Route to appropriate verification method
            if verification_strategy == 'local_storage_assertions':
                verification_results = self._local_storage_assertions_verification(task, execution_results, results_dir)
            elif verification_strategy == 'run_id_assertions':
                verification_results = self._run_id_assertions_verification(task, execution_results, results_dir)
            elif verification_strategy == 'grader_config':
                # Pass browser_computer to GraderConfigVerifier for window.get_states() calls
                grader_verifier = GraderConfigVerifier(
                    logger=self.logger,
                    browser_computer=browser_computer
                )
                verification_results = grader_verifier.verify_task(
                    task=task,
                    execution_results=execution_results,
                    results_dir=results_dir,
                )
            elif verification_strategy == "verifier_api_script":
                verification_results = {
                    "task_id": task["task_id"],
                    "run_id": self.run_id,
                    "verification_method": "verifier_api_script",
                    "verification_completed": False,
                    "verification_status": "Unknown",
                    "verification_summary": "API Script verification attempted",
                    "verification_time": 0,
                    "verification_comments": "",
                    "actual_state_response": None,
                    "expected_state_response": None,
                    "api_error": None,
                }

                module_name = execution_results.get("verifier_module_name")
                verifier_module = sys.modules.get(module_name)
                if verifier_module is None:
                    # Fallback: try to load the verifier module if not already loaded
                    verifier_path = task.get("verifier_path", "")
                    if verifier_path and os.path.isfile(verifier_path):
                        self.logger.info(f"📦 Loading verifier module from: {verifier_path}")
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(module_name, verifier_path)
                        verifier_module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = verifier_module
                        spec.loader.exec_module(verifier_module)
                        self.logger.info(f"✅ Verifier module loaded successfully")
                    else:
                        message = (
                            f"Verifier module '{module_name}' not loaded. "
                            f"Expected script at {verifier_path or 'Unknown'} for task {task['task_id']}."
                        )
                        self.logger.error(f"❌ {message}")
                        raise ConfigurationError(message)
                backend_url = resolve_backend_api_base(task, self.logger)
                if not backend_url:
                    raise ConfigurationError(
                        f"Unable to determine backend API base URL for task {task['task_id']}"
                    )
                # Get auth token (not run_id) for verifier
                auth_token = self.current_auth_token
                self.logger.info(f"🔑 Token for on_end: {'present' if auth_token else 'MISSING'}")
                self.logger.info(f"🚀  Running verifier on_end method")
                verifier_result = verifier_module.on_end(
                    prompt=task.get("prompt"),
                    base_url=backend_url,
                    verifier_on_start_data=execution_results["verifier_on_start_data"],
                    token=auth_token,
                )
                self.logger.info(f"🚀  Verifier on_end method completed")
                self.logger.info(f"🚀  Verifier result: {verifier_result}")
                verification_results["verification_completed"] = True
                verification_results["verification_status"] = (
                    "PASSED" if verifier_result["result"] == "passed" else "FAILED"
                )
                # Store the details from verifier_result for failure diagnostics
                if "details" in verifier_result:
                    verification_results["details"] = verifier_result["details"]
                    self.logger.info(f"✅ Stored verification details: {list(verifier_result['details'].keys())}")

            else:
                # Default to backend verification (verification_endpoint)
                verification_results = self._backend_verification(task, execution_results)

            verification_results.setdefault('task_id', task['task_id'])
            verification_results.setdefault('run_id', self.run_id)
            verification_results.setdefault(
                'verification_time', time.time() - verification_start_time
            )

            self.logger.info(f"📋 File content preview:")
            self.logger.info(f"   - Task ID: {verification_results.get('task_id', 'N/A')}")
            self.logger.info(f"   - Run ID: {verification_results.get('run_id', 'N/A')}")
            self.logger.info(f"   - Status: {verification_results.get('verification_status', 'N/A')}")
            self.logger.info(f"   - Method: {verification_results.get('verification_method', 'N/A')}")
            self.logger.info(f"   - Time: {verification_results.get('verification_time', 0):.3f}s")

            # Log verification summary
            self.logger.info(f"🔍 Verification summary for {task['task_id']}:")
            self.logger.info(f"  - Completed: {verification_results.get('verification_completed', False)}")
            self.logger.info(f"  - Status: {verification_results.get('verification_status', 'Unknown')}")
            self.logger.info(f"  - Time: {verification_results.get('verification_time', 0):.2f}s")
            self.logger.info(f"  - Method: {verification_results.get('verification_method', 'Unknown')}")
            
            return verification_results
            
        except ConfigurationError:
            # Configuration errors should crash immediately
            self.logger.error("❌ Configuration error in verification - re-raising", exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f"❌ API verification step failed: {e}")
            verification_time = time.time() - verification_start_time
            
            error_results = {
                'task_id': task['task_id'],
                'verification_completed': False,
                'verification_status': "FAILED",
                'verification_time': verification_time,
                'verification_steps': 0,
                'verification_method': 'api_error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
            return error_results
    
    def analyze_completion_indicators(self, text: str, step_name: str) -> bool:
        """Analyze text for completion indicators based on step type"""
        try:
            text_lower = text.lower()
            
            # Step 1: Task execution completion - look for natural completion indicators
            if step_name == 'step1_task_execution':
                completion_patterns = [
                    r'completed',
                    r'finished',
                    r'done',
                    r'successful',
                    r'accomplished',
                    r'achieved',
                    r'final task summary',
                    r'task summary'
                ]
                
                import re
                for pattern in completion_patterns:
                    if re.search(pattern, text_lower):
                        self.logger.info(f"✅ Step 1 completion detected: '{pattern}' found in response")
                        return True
                
                self.logger.info(f"⏳ Step 1 not complete: no completion indicators found")
                return False
            
            # Step 2: Verification completion - look for verification completion indicators
            elif step_name == 'step2_verification':
                completion_patterns = [
                    r'verified',
                    r'confirmed',
                    r'checked',
                    r'validated',
                    r'verification summary',
                    r'verification complete',
                    r'passed',
                    r'successful'
                ]
                
                import re
                for pattern in completion_patterns:
                    if re.search(pattern, text_lower):
                        self.logger.info(f"✅ Step 2 completion detected: '{pattern}' found in response")
                        return True
                
                self.logger.info(f"⏳ Step 2 not complete: no verification completion indicators found")
                return False
            
            # General completion indicators for other steps
            else:
                completion_patterns = [
                    r'completed',
                    r'finished',
                    r'done',
                    r'successful',
                    r'passed',
                    r'verified',
                    r'confirmed'
                ]
                
                import re
                for pattern in completion_patterns:
                    if re.search(pattern, text_lower):
                        self.logger.info(f"✅ General completion detected: '{pattern}' found in response")
                        return True
                
                return False
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing completion indicators: {e}")
            return False
    
    def get_run_id(self) -> str:
        """Get the current run ID"""
        return self.run_id
    
    def create_verification_summary(self, task_result: Dict[str, Any]) -> Dict[str, Any]:
        """Create a comprehensive verification summary"""
        summary = {
            'task_id': task_result.get('task_id', 'unknown'),
            'run_id': self.run_id,
            'execution_status': task_result.get('execution_status', 'unknown'),
            'verification_status': task_result.get('verification_status', 'unknown'),
            'api_verification_status': task_result.get('api_verification_status', 'unknown'),
            'overall_status': task_result.get('status', 'unknown'),
            'execution_steps': task_result.get('execution_steps', 0),
            'verification_steps': task_result.get('verification_steps', 0),
            'total_time': task_result.get('total_time', 0),
            'timestamp': datetime.now().isoformat()
        }
        
        # Add API verification details if available
        if 'api_verification_results' in task_result:
            api_results = task_result['api_verification_results']
            summary['api_verification'] = {
                'status': api_results.get('verification_status', 'unknown'),
                'method': api_results.get('verification_method', 'unknown'),
                'time': api_results.get('verification_time', 0),
                'summary': api_results.get('verification_summary', 'No summary available'),
                'api_error': api_results.get('api_error', None)
            }
        
        return summary
    
    def _safe_get_verification_status(self, result: Dict[str, Any]) -> str:
        """Safely extract verification status from result, handling None cases"""
        try:
            verification_results = result.get('verification_results')
            if verification_results and isinstance(verification_results, dict):
                return verification_results.get('verification_status', 'UNKNOWN')
            else:
                return 'UNKNOWN'
        except Exception as e:
            self.logger.warning(f"⚠️ Error extracting verification status: {e}")
            return 'UNKNOWN'
    
    def _validate_conversation_structure(self, items: List[Dict], context: str):
        """Validate conversation structure and log any issues"""
        if not items:
            self.logger.warning(f"⚠️ {context}: No items to validate")
            return
        
        self.logger.info(f"🔍 {context}: Validating conversation structure with {len(items)} items")
        
        # Check for reasoning items without proper pairing
        reasoning_items = []
        computer_use_items = []
        
        for i, item in enumerate(items):
            if not item:
                self.logger.warning(f"⚠️ {context}: Empty item at index {i}")
                continue
                
            item_type = item.get('type', 'unknown')
            item_id = item.get('id', 'no_id')
            
            if item_type == 'reasoning':
                reasoning_items.append((i, item_id))
                self.logger.info(f"📝 {context}: Found reasoning item at index {i} with ID: {item_id}")
                
            elif item_type == 'computer_use':
                computer_use_items.append((i, item_id))
                self.logger.info(f"💻 {context}: Found computer_use item at index {i} with ID: {item_id}")
                
            elif item_type == 'message':
                self.logger.info(f"💬 {context}: Found message item at index {i} with ID: {item_id}")
                
            elif item_type == 'computer_call':
                computer_use_items.append((i, item_id))
                self.logger.info(f"🖱️ {context}: Found computer_call item at index {i} with ID: {item_id}")

            elif item_type == 'computer_call_output':
                self.logger.info(f"🖥️ {context}: Found computer_call_output item at index {i}")

            elif item_type in {'function_call', 'function_call_output'}:
                self.logger.info(f"🛠️ {context}: Found {item_type} item at index {i} with ID: {item_id}")
                
            else:
                self.logger.warning(f"⚠️ {context}: Unknown item type '{item_type}' at index {i}")
        
        # Log summary
        self.logger.info(f"📊 {context}: Validation summary - {len(reasoning_items)} reasoning, {len(computer_use_items)} computer_use items")
        
        # Check for potential issues
        if len(reasoning_items) != len(computer_use_items):
            self.logger.warning(
                f"⚠️ {context}: Mismatch between reasoning ({len(reasoning_items)}) and computer_use ({len(computer_use_items)}) items"
            )
            enforce_env = os.getenv("CUA_ENFORCE_TOOL_STRUCTURE", "0").lower()
            if enforce_env in {"1", "true", "yes"}:
                return False

        return True
    
    def _generate_verification_comments(self, assertions: List[Dict], expected_data: Dict = None) -> str:
        """Generate verification comments based on assertion results"""
        if not assertions:
            return ''
        
        # Check if all assertions pass
        all_passed = all(assertion.get('result') == 'pass' for assertion in assertions)
        
        if all_passed:
            return f'All {len(assertions)} assertions passed'
        
        # Generate detailed comments for failed assertions
        failed_comments = []
        expected_assertions = expected_data.get('assertions', []) if expected_data else []
        
        # Use order-based matching since assertions have the same order in expected and actual
        for i, assertion in enumerate(assertions):
            if assertion.get('result') != 'pass':
                # Get title from expected assertions using the same index
                title = 'Unknown assertion'
                if i < len(expected_assertions):
                    title = expected_assertions[i].get('title', 'Unknown assertion')
                
                # Check if there's an error (actual key missing)
                if assertion.get('error'):
                    comment = f"{title} -- error: {assertion['error']}"
                else:
                    # Format: title -- expected value: {expected} and actual value: {actual}
                    expected_val = assertion.get('expected', 'N/A')
                    actual_val = assertion.get('actual', 'N/A')
                    comment = f"{title} -- expected value: {expected_val} and actual value: {actual_val}"
                
                failed_comments.append(comment)
        
        # Join failed comments with line breaks
        return '\n\n'.join(failed_comments)
    
    def _generate_verify_endpoint_comments(self, assertions: List[Dict]) -> str:
        """Generate verification comments for verify endpoint assertions (which already have titles)"""
        if not assertions:
            return ''
        
        # Check if all assertions pass
        all_passed = all(assertion.get('result') == 'pass' for assertion in assertions)
        
        if all_passed:
            return f'All {len(assertions)} assertions passed'
        
        # Generate detailed comments for failed assertions
        failed_comments = []
        
        for assertion in assertions:
            if assertion.get('result') != 'pass':
                # Use title directly from the assertion
                title = assertion.get('title', 'Unknown assertion')
                
                # Check if there's an error
                if assertion.get('error'):
                    comment = f"{title} -- error: {assertion['error']}"
                else:
                    # Format: title -- expected value: {expected} and actual value: {actual}
                    expected_val = assertion.get('expected', 'N/A')
                    actual_val = assertion.get('actual', 'N/A')
                    comment = f"{title} -- expected value: {expected_val} and actual value: {actual_val}"
                
                failed_comments.append(comment)
        
        # Join failed comments with line breaks
        return '\n\n'.join(failed_comments)
