#!/usr/bin/env python3
"""
Database Snapshot Service

This module captures full Postgres database snapshots to JSON files for verification
and debugging purposes. Each snapshot includes all tables from the public schema.
"""

import json
import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Suppress InsecureRequestWarning when using verify=False for staging/self-signed certs
from urllib3.exceptions import InsecureRequestWarning
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

from sqlalchemy import text
from app.core.database_utils import get_db_session
from app.services.task_runners.task_verification import resolve_backend_api_base


class DatabaseSnapshotService:
    """
    Service for capturing full database snapshots to JSON
    
    This service queries all tables in the public schema and exports
    their contents to JSON files, keyed by run_id for correlation with
    task execution and verification.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the database snapshot service
        
        Args:
            logger: Optional logger instance (creates one if not provided)
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def _resolve_session_id(self, auth_token: str, gym_url: str) -> Optional[str]:
        """
        Resolve the session_id from an auth_token by calling the gym's get_session_id endpoint.
        
        The gym backend requires session_id as a query parameter for db_snapshot and other
        endpoints. This method extracts the session_id from the JWT auth token.
        
        Args:
            auth_token: The JWT authentication token
            gym_url: Base URL of the gym (e.g., https://aws-jira-staging.turing.com)
            
        Returns:
            The session_id string if successful, None if the request fails
        """
        import requests
        
        if not auth_token or not gym_url:
            self.logger.warning("⚠️ Cannot resolve session_id: missing auth_token or gym_url")
            return None
        
        try:
            # Construct the get_session_id endpoint
            session_id_endpoint = f"{gym_url.rstrip('/')}/api/v1/get_session_id"
            
            token_preview = auth_token[:8] + "..." if len(auth_token) > 8 else auth_token
            self.logger.info(f"🔑 Resolving session_id from auth token: {token_preview}")
            self.logger.debug(f"📡 Calling get_session_id endpoint: {session_id_endpoint}")
            
            # Call the endpoint with auth_token as query parameter
            response = requests.get(
                session_id_endpoint,
                params={"auth_token": auth_token},
                timeout=10,
                verify=False  # Handle self-signed or staging SSL certificates
            )
            
            response.raise_for_status()
            data = response.json()
            
            session_id = data.get("session_id")
            if session_id:
                self.logger.info(f"✅ Resolved session_id: {session_id}")
                return session_id
            else:
                self.logger.warning("⚠️ get_session_id response missing session_id field")
                return None
                
        except requests.exceptions.HTTPError as http_error:
            status_code = http_error.response.status_code if http_error.response else "unknown"
            self.logger.warning(
                f"⚠️ Failed to resolve session_id (HTTP {status_code}): {http_error}. "
                f"The gym may not support the get_session_id endpoint."
            )
            return None
            
        except requests.exceptions.ConnectionError as conn_error:
            self.logger.warning(
                f"⚠️ Connection error resolving session_id: {conn_error}. "
                f"Check if gym backend is accessible."
            )
            return None
            
        except requests.exceptions.Timeout:
            self.logger.warning("⚠️ Timeout resolving session_id (request took longer than 10 seconds)")
            return None
            
        except requests.exceptions.RequestException as req_error:
            self.logger.warning(f"⚠️ Request error resolving session_id: {req_error}")
            return None
            
        except Exception as e:
            self.logger.warning(f"⚠️ Unexpected error resolving session_id: {e}")
            return None
    
    def capture_full_db_snapshot(
        self,
        auth_token: str,
        when: str,
        output_dir: Path,
        gym_base_url: str,
        task_id: Optional[str] = None
    ) -> bool:
        """
        Capture a full database snapshot from the GYM's database and save it to JSON
        
        IMPORTANT: This captures the GYM's database (e.g., DeskZen DB), NOT the harness DB.
        The gym's database is isolated by auth_token for each task execution.
        
        Args:
            auth_token: The authentication token for this execution (used for DB isolation)
            when: "before" or "after" to indicate snapshot timing
            output_dir: Directory where the snapshot JSON should be saved
            gym_base_url: Base URL of the gym (used to make API calls to gym's DB endpoints)
            task_id: Optional task identifier for logging context
            
        Returns:
            bool: True if snapshot was captured successfully, False otherwise
        """
        try:
            # Log token preview for debugging
            token_preview = auth_token[:8] + "..." if auth_token and len(auth_token) > 8 else "NONE"
            self.logger.info(f"📸 Capturing gym database snapshot ({when}) with auth token")
            self.logger.info(f"🎯 Gym URL (requested): {gym_base_url}")
            self.logger.info(f"🔑 Using auth token for '{when}' snapshot: {token_preview}")
            
            # Ensure output directory exists
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Build the snapshot data structure
            snapshot_data = {
                "auth_token_used": bool(auth_token),  # Don't store actual token
                "auth_token_preview": auth_token[:8] + "..." if auth_token and len(auth_token) > 8 else None,
                "when": when,
                "captured_at": datetime.now().isoformat(),
                "task_id": task_id,
                "gym_base_url": gym_base_url,
                "tables": {}
            }
            
            # Make API call to gym's database snapshot endpoint
            import requests
            
            # Resolve backend API base (ensures Deskzen -api host when needed)
            task_context = {
                "backend_api_url": gym_base_url,
                "base_url": gym_base_url,
                "task_link": gym_base_url,
            }
            resolved_backend_base = resolve_backend_api_base(task_context, self.logger)
            gym_url = (resolved_backend_base or gym_base_url).rstrip('/')
            if resolved_backend_base:
                self.logger.info(f"🏢 Using backend API base for snapshots: {gym_url}")
            else:
                self.logger.warning(
                    "⚠️ Using provided gym_base_url directly; backend base could not be resolved"
                )

            # Resolve session_id from auth_token (required by gym backend)
            session_id = self._resolve_session_id(auth_token, gym_url)
            if session_id:
                snapshot_data["session_id"] = session_id
            else:
                self.logger.warning(
                    "⚠️ Could not resolve session_id from auth_token. "
                    "DB snapshot may fail if gym requires session_id parameter."
                )
            
            # Construct gym's DB snapshot endpoint
            snapshot_endpoint = f"{gym_url}/api/v1/db_snapshot"
            
            self.logger.info(f"📡 Calling gym DB snapshot endpoint: {snapshot_endpoint}")
            if session_id:
                self.logger.info(f"🆔 Using session_id: {session_id}")
            
            # Use Bearer token for authentication (kept for backwards compatibility)
            headers = {
                "Authorization": f"Bearer {auth_token}"
            }
            
            # Pass session_id as query parameter (required by gym backend)
            params = {}
            if session_id:
                params["session_id"] = session_id
            
            try:
                self.logger.debug(f"📡 Request details: URL={snapshot_endpoint}, params={params}, headers=Authorization: Bearer ***")
                # verify=False to handle self-signed or staging SSL certificates (e.g., aws-jira-staging.turing.com)
                response = requests.get(
                    snapshot_endpoint,
                    headers=headers,
                    params=params,
                    timeout=30,
                    verify=False
                )
                
                self.logger.debug(f"📥 Response status: {response.status_code}, headers: {dict(response.headers)}")
                response.raise_for_status()
                
                gym_db_data = response.json()
                snapshot_data["tables"] = gym_db_data.get("tables", {})
                snapshot_data["summary"] = gym_db_data.get("summary", {})
                
                self.logger.info(f"✅ Retrieved gym DB snapshot from API")
                
            except requests.exceptions.ConnectionError as conn_error:
                self.logger.error(
                    f"❌ Connection error calling gym DB snapshot API: {conn_error}. "
                    f"URL: {snapshot_endpoint}. "
                    f"Check if gym backend is running and accessible."
                )
                snapshot_data["error"] = f"Connection error: {str(conn_error)}"
                snapshot_data["tables"] = {}
                snapshot_data["summary"] = {
                    "total_tables": 0,
                    "total_rows": 0,
                    "error": f"Connection failed: {str(conn_error)}"
                }
                
            except requests.exceptions.HTTPError as http_error:
                status_code = http_error.response.status_code if http_error.response else "unknown"
                self.logger.error(
                    f"❌ HTTP error calling gym DB snapshot API: {http_error}. "
                    f"Status code: {status_code}. "
                    f"URL: {snapshot_endpoint}. "
                    f"Response: {http_error.response.text[:200] if http_error.response else 'N/A'}"
                )
                snapshot_data["error"] = f"HTTP {status_code}: {str(http_error)}"
                snapshot_data["tables"] = {}
                snapshot_data["summary"] = {
                    "total_tables": 0,
                    "total_rows": 0,
                    "error": f"HTTP {status_code}"
                }
                
            except requests.exceptions.Timeout as timeout_error:
                self.logger.error(
                    f"❌ Timeout calling gym DB snapshot API: {timeout_error}. "
                    f"URL: {snapshot_endpoint}. "
                    f"Request took longer than 30 seconds."
                )
                snapshot_data["error"] = f"Timeout: {str(timeout_error)}"
                snapshot_data["tables"] = {}
                snapshot_data["summary"] = {
                    "total_tables": 0,
                    "total_rows": 0,
                    "error": "Request timeout"
                }
                
            except requests.exceptions.RequestException as api_error:
                self.logger.error(
                    f"❌ Request error calling gym DB snapshot API: {api_error}. "
                    f"URL: {snapshot_endpoint}. "
                    f"Error type: {type(api_error).__name__}"
                )
                snapshot_data["error"] = f"Request error: {str(api_error)}"
                snapshot_data["tables"] = {}
                snapshot_data["summary"] = {
                    "total_tables": 0,
                    "total_rows": 0,
                    "error": f"Request failed: {str(api_error)}"
                }
            
            # Write snapshot to JSON file
            snapshot_filename = f"db_snapshot_{when}.json"
            snapshot_path = output_dir / snapshot_filename
            
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, indent=2, ensure_ascii=False, default=str)
            
            # Calculate summary stats for logging
            total_tables = snapshot_data.get("summary", {}).get("total_tables", 0)
            total_rows = snapshot_data.get("summary", {}).get("total_rows", 0)
            has_error = "error" in snapshot_data
            
            if has_error:
                self.logger.warning(
                    f"⚠️ Gym database snapshot ({when}) saved with error to {snapshot_path}. "
                    f"Gym may not implement DB snapshot API endpoint."
                )
            else:
                self.logger.info(
                    f"✅ Gym database snapshot ({when}) saved to {snapshot_path} "
                    f"({total_tables} tables, {total_rows} rows)"
                )
            
            return True
            
        except Exception as e:
            token_preview = auth_token[:8] + "..." if auth_token and len(auth_token) > 8 else "NONE"
            self.logger.error(
                f"❌ Failed to capture database snapshot ({when}) with auth token {token_preview}: {e}",
                exc_info=True
            )
            return False
    
    def compare_snapshots(
        self,
        before_path: Path,
        after_path: Path
    ) -> Optional[Dict[str, Any]]:
        """
        Compare two database snapshots and return a diff
        
        Args:
            before_path: Path to the "before" snapshot JSON
            after_path: Path to the "after" snapshot JSON
            
        Returns:
            Dict containing the differences, or None if comparison failed
        """
        try:
            self.logger.info(f"🔍 Comparing snapshots: {before_path.name} vs {after_path.name}")
            
            # Load both snapshots
            with open(before_path, 'r', encoding='utf-8') as f:
                before_data = json.load(f)
            
            with open(after_path, 'r', encoding='utf-8') as f:
                after_data = json.load(f)
            
            # Build comparison report
            comparison = {
                "run_id": before_data.get("run_id"),
                "compared_at": datetime.now().isoformat(),
                "before_captured_at": before_data.get("captured_at"),
                "after_captured_at": after_data.get("captured_at"),
                "changes": {}
            }
            
            # Compare each table
            all_tables = set(before_data["tables"].keys()) | set(after_data["tables"].keys())
            
            for table_name in all_tables:
                before_rows = before_data["tables"].get(table_name, [])
                after_rows = after_data["tables"].get(table_name, [])
                
                if not isinstance(before_rows, list):
                    before_rows = []
                if not isinstance(after_rows, list):
                    after_rows = []
                
                row_count_change = len(after_rows) - len(before_rows)
                
                if row_count_change != 0:
                    comparison["changes"][table_name] = {
                        "before_count": len(before_rows),
                        "after_count": len(after_rows),
                        "change": row_count_change
                    }
            
            self.logger.info(
                f"✅ Snapshot comparison complete: {len(comparison['changes'])} tables changed"
            )
            
            return comparison
            
        except Exception as e:
            self.logger.error(f"❌ Failed to compare snapshots: {e}", exc_info=True)
            return None

    def compute_diff(
        self,
        before_path: Path,
        after_path: Path,
        task_id: Optional[str] = None,
        prompt: Optional[str] = None,
        ignore_tables: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compute detailed diff between before and after snapshots for manual verification.
        
        This method provides row-level differences showing exactly what was added,
        modified, or deleted in each table. High-volume tables (like api_logs) can be
        ignored to keep the output manageable.
        
        Args:
            before_path: Path to db_snapshot_before.json
            after_path: Path to db_snapshot_after.json
            task_id: Task identifier for context
            prompt: Task prompt for context (helps reviewer understand expected changes)
            ignore_tables: Tables to exclude from detailed diff (still show counts)
            
        Returns:
            Complete diff structure for db_snapshot_diff.json
        """
        ignore_tables = ignore_tables or []
        
        try:
            self.logger.info(f"📊 Computing detailed DB snapshot diff...")
            self.logger.info(f"   Before: {before_path}")
            self.logger.info(f"   After: {after_path}")
            
            # Check if snapshot files exist
            if not before_path.exists():
                self.logger.warning(f"⚠️ Before snapshot not found: {before_path}")
                return self._create_error_diff(task_id, prompt, "Before snapshot file not found")
            
            if not after_path.exists():
                self.logger.warning(f"⚠️ After snapshot not found: {after_path}")
                return self._create_error_diff(task_id, prompt, "After snapshot file not found")
            
            # Load both snapshots
            with open(before_path, 'r', encoding='utf-8') as f:
                before_data = json.load(f)
            
            with open(after_path, 'r', encoding='utf-8') as f:
                after_data = json.load(f)
            
            # Check for errors in snapshots
            if "error" in before_data:
                return self._create_error_diff(task_id, prompt, f"Before snapshot has error: {before_data['error']}")
            
            if "error" in after_data:
                return self._create_error_diff(task_id, prompt, f"After snapshot has error: {after_data['error']}")
            
            # Initialize diff structure
            diff = {
                "computed_at": datetime.now().isoformat(),
                "task_id": task_id,
                "prompt": prompt,
                "before_snapshot_time": before_data.get("captured_at"),
                "after_snapshot_time": after_data.get("captured_at"),
                "summary": {
                    "tables_with_changes": 0,
                    "total_rows_added": 0,
                    "total_rows_modified": 0,
                    "total_rows_deleted": 0
                },
                "changes_by_table": {},
                "tables_unchanged": []
            }
            
            before_tables = before_data.get("tables", {})
            after_tables = after_data.get("tables", {})
            
            # Get all table names
            all_tables = set(before_tables.keys()) | set(after_tables.keys())
            
            for table_name in sorted(all_tables):
                before_rows = before_tables.get(table_name, [])
                after_rows = after_tables.get(table_name, [])
                
                # Ensure they are lists
                if not isinstance(before_rows, list):
                    before_rows = []
                if not isinstance(after_rows, list):
                    after_rows = []
                
                rows_before = len(before_rows)
                rows_after = len(after_rows)
                
                # Check if table is ignored (high-volume tables like api_logs)
                if table_name in ignore_tables:
                    if rows_before != rows_after:
                        diff["changes_by_table"][table_name] = {
                            "rows_before": rows_before,
                            "rows_after": rows_after,
                            "note": f"{abs(rows_after - rows_before)} rows {'added' if rows_after > rows_before else 'removed'} (details omitted - high volume table)"
                        }
                        diff["summary"]["tables_with_changes"] += 1
                        if rows_after > rows_before:
                            diff["summary"]["total_rows_added"] += (rows_after - rows_before)
                        else:
                            diff["summary"]["total_rows_deleted"] += (rows_before - rows_after)
                    continue
                
                # Compute row-level diff for non-ignored tables
                table_diff = self._compute_table_diff(before_rows, after_rows, table_name)
                
                if table_diff["has_changes"]:
                    diff["changes_by_table"][table_name] = {
                        "rows_before": rows_before,
                        "rows_after": rows_after,
                        "added": table_diff["added"],
                        "modified": table_diff["modified"],
                        "deleted": table_diff["deleted"]
                    }
                    diff["summary"]["tables_with_changes"] += 1
                    diff["summary"]["total_rows_added"] += len(table_diff["added"])
                    diff["summary"]["total_rows_modified"] += len(table_diff["modified"])
                    diff["summary"]["total_rows_deleted"] += len(table_diff["deleted"])
                else:
                    diff["tables_unchanged"].append(table_name)
            
            self.logger.info(
                f"✅ DB snapshot diff computed: "
                f"{diff['summary']['tables_with_changes']} tables changed, "
                f"{diff['summary']['total_rows_added']} added, "
                f"{diff['summary']['total_rows_modified']} modified, "
                f"{diff['summary']['total_rows_deleted']} deleted"
            )
            
            return diff
            
        except Exception as e:
            self.logger.error(f"❌ Failed to compute DB snapshot diff: {e}", exc_info=True)
            return self._create_error_diff(task_id, prompt, str(e))
    
    def _compute_table_diff(
        self,
        before_rows: List[Dict],
        after_rows: List[Dict],
        table_name: str
    ) -> Dict[str, Any]:
        """
        Compute row-level diff for a single table.
        
        Uses 'id' field as primary key to identify rows.
        Falls back to full row comparison if 'id' is not present.
        
        Args:
            before_rows: List of rows from before snapshot
            after_rows: List of rows from after snapshot
            table_name: Name of the table (for logging)
            
        Returns:
            Dict with added, modified, deleted rows and has_changes flag
        """
        added = []
        modified = []
        deleted = []
        
        # Try to use 'id' field as primary key
        # Check various common ID field names
        id_field = None
        for field_name in ['id', 'uuid', 'pk', f'{table_name}_id']:
            if before_rows and field_name in before_rows[0]:
                id_field = field_name
                break
            if after_rows and field_name in after_rows[0]:
                id_field = field_name
                break
        
        if id_field:
            # Use ID-based comparison
            before_by_id = {row.get(id_field): row for row in before_rows if row.get(id_field) is not None}
            after_by_id = {row.get(id_field): row for row in after_rows if row.get(id_field) is not None}
            
            before_ids = set(before_by_id.keys())
            after_ids = set(after_by_id.keys())
            
            # Find added rows (in after but not in before)
            for row_id in (after_ids - before_ids):
                added.append(after_by_id[row_id])
            
            # Find deleted rows (in before but not in after)
            for row_id in (before_ids - after_ids):
                deleted.append(before_by_id[row_id])
            
            # Find modified rows (in both but different)
            for row_id in (before_ids & after_ids):
                before_row = before_by_id[row_id]
                after_row = after_by_id[row_id]
                if before_row != after_row:
                    modified.append({
                        "id": row_id,
                        "before": before_row,
                        "after": after_row,
                        "changed_fields": self._get_changed_fields(before_row, after_row)
                    })
        else:
            # Fall back to simple count-based comparison
            # Cannot determine which specific rows changed without ID
            if len(after_rows) > len(before_rows):
                # Assume new rows are at the end
                added = after_rows[len(before_rows):]
            elif len(after_rows) < len(before_rows):
                # Assume deleted rows were at the end
                deleted = before_rows[len(after_rows):]
        
        return {
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "has_changes": len(added) > 0 or len(modified) > 0 or len(deleted) > 0
        }
    
    def _get_changed_fields(self, before_row: Dict, after_row: Dict) -> List[str]:
        """
        Get list of fields that changed between two row versions.
        
        Args:
            before_row: Row from before snapshot
            after_row: Row from after snapshot
            
        Returns:
            List of field names that have different values
        """
        changed = []
        all_keys = set(before_row.keys()) | set(after_row.keys())
        
        for key in all_keys:
            before_val = before_row.get(key)
            after_val = after_row.get(key)
            if before_val != after_val:
                changed.append(key)
        
        return changed
    
    def _create_error_diff(
        self,
        task_id: Optional[str],
        prompt: Optional[str],
        error_message: str
    ) -> Dict[str, Any]:
        """
        Create an error diff structure when diff computation fails.
        
        Args:
            task_id: Task identifier
            prompt: Task prompt
            error_message: Error message to include
            
        Returns:
            Diff structure with error information
        """
        return {
            "computed_at": datetime.now().isoformat(),
            "task_id": task_id,
            "prompt": prompt,
            "error": error_message,
            "summary": {
                "tables_with_changes": 0,
                "total_rows_added": 0,
                "total_rows_modified": 0,
                "total_rows_deleted": 0
            },
            "changes_by_table": {},
            "tables_unchanged": []
        }
    
    def save_diff(
        self,
        diff: Dict[str, Any],
        output_dir: Path
    ) -> bool:
        """
        Save computed diff to db_snapshot_diff.json.
        
        Args:
            diff: Computed diff dictionary
            output_dir: Directory to save the diff file
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            diff_path = output_dir / "db_snapshot_diff.json"
            
            with open(diff_path, 'w', encoding='utf-8') as f:
                json.dump(diff, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.info(f"✅ DB snapshot diff saved to: {diff_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save DB snapshot diff: {e}", exc_info=True)
            return False


# Global instance for convenience
db_snapshot_service = DatabaseSnapshotService()
