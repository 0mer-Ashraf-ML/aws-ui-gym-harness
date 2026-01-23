#!/usr/bin/env python3
"""
Summary Manager - Database operations for execution and batch summaries
Handles database updates with proper locking and error handling
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any

from sqlalchemy import text

from app.core.database_utils import get_db_session


class SummaryManager:
    """
    Manages database operations for execution and batch summaries
    """
    
    def __init__(self, logger=None):
        """Initialize the summary manager"""
        self.logger = logger or logging.getLogger(__name__)
        
    def update_execution_summary(self, execution_id: str, summary: str) -> bool:
        """
        Update execution summary in database
        
        Args:
            execution_id: Execution UUID
            summary: Generated summary text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_session() as db:
                query = """
                    SELECT uuid
                    FROM executions
                    WHERE uuid = :execution_id
                    FOR UPDATE
                """
                result = db.execute(text(query), {"execution_id": execution_id})
                row = result.fetchone()

                if not row:
                    self.logger.error(f"Execution {execution_id} not found")
                    return False

                update_query = """
                    UPDATE executions
                    SET eval_insights = :summary, updated_at = NOW()
                    WHERE uuid = :execution_id
                """
                db.execute(
                    text(update_query),
                    {"summary": summary, "execution_id": execution_id},
                )

                self.logger.info(f"✅ Updated execution summary for {execution_id}")
                return True

        except Exception as e:
            self.logger.error(f"❌ Error updating execution summary for {execution_id}: {e}")
            return False
    
    def update_batch_summary(self, batch_id: str, model_summaries: Dict[str, str]) -> bool:
        """
        Update batch summary in database
        
        Args:
            batch_id: Batch UUID
            model_summaries: Dict mapping model names to summaries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_session() as db:
                query = """
                    SELECT uuid, eval_insights
                    FROM batches
                    WHERE uuid = :batch_id
                    FOR UPDATE
                """
                result = db.execute(text(query), {"batch_id": batch_id})
                row = result.fetchone()

                if not row:
                    self.logger.error(f"Batch {batch_id} not found")
                    return False

                existing_insights: Dict[str, Any] = {}
                raw_insights = getattr(row, "eval_insights", None)
                if raw_insights:
                    try:
                        existing_insights = (
                            json.loads(raw_insights)
                            if isinstance(raw_insights, str)
                            else dict(raw_insights)
                        )
                    except (json.JSONDecodeError, TypeError):
                        self.logger.warning(
                            "Failed to parse existing batch insights for %s, starting fresh",
                            batch_id,
                        )
                        existing_insights = {}

                existing_insights.update(model_summaries)

                update_query = """
                    UPDATE batches
                    SET eval_insights = :insights, updated_at = NOW()
                    WHERE uuid = :batch_id
                """
                db.execute(
                    text(update_query),
                    {
                        "insights": json.dumps(existing_insights),
                        "batch_id": batch_id,
                    },
                )

                self.logger.info(
                    "✅ Updated batch summary for %s with %d models",
                    batch_id,
                    len(model_summaries),
                )
                return True

        except Exception as e:
            self.logger.error(f"❌ Error updating batch summary for {batch_id}: {e}")
            return False
    
    def get_execution_insights(self, execution_id: str) -> List[str]:
        """
        Get all iteration insights for an execution
        
        Args:
            execution_id: Execution UUID
            
        Returns:
            List of eval_insights strings from iterations
        """
        try:
            with get_db_session() as db:
                query = """
                    SELECT eval_insights
                    FROM iterations
                    WHERE execution_id = :execution_id
                    AND eval_insights IS NOT NULL
                    AND eval_insights != ''
                    ORDER BY iteration_number
                """
                rows = db.execute(text(query), {"execution_id": execution_id}).fetchall()

                insights = [row.eval_insights for row in rows if row.eval_insights]
                self.logger.info(
                    "Retrieved %d iteration insights for execution %s",
                    len(insights),
                    execution_id,
                )
                return insights

        except Exception as e:
            self.logger.error(f"❌ Error getting execution insights for {execution_id}: {e}")
            return []
    
    def get_batch_execution_insights(self, batch_id: Optional[str]) -> Dict[str, List[str]]:
        """
        Get execution insights grouped by model for a batch
        
        Args:
            batch_id: Batch UUID
            
        Returns:
            Dict mapping model names to lists of execution summaries
        """
        if not batch_id or batch_id == "None":
            self.logger.warning(f"Invalid batch_id provided: {batch_id}")
            return {}
        
        try:
            with get_db_session() as db:
                query = """
                    SELECT e.model, e.eval_insights
                    FROM executions e
                    WHERE e.batch_id = :batch_id
                    AND e.eval_insights IS NOT NULL
                    AND e.eval_insights != ''
                    ORDER BY e.model, e.created_at
                """
                rows = db.execute(text(query), {"batch_id": batch_id}).fetchall()

                model_executions: Dict[str, List[str]] = {}
                for row in rows:
                    model_executions.setdefault(row.model, []).append(row.eval_insights)

                self.logger.info(
                    "Retrieved execution insights for %d models in batch %s",
                    len(model_executions),
                    batch_id,
                )
                return model_executions

        except Exception as e:
            self.logger.error(f"❌ Error getting batch execution insights for {batch_id}: {e}")
            return {}
    
    def get_execution_info(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get execution info including batch_id and model
        
        Args:
            execution_id: Execution UUID
            
        Returns:
            Dict with batch_id and model, or None if not found
        """
        try:
            with get_db_session() as db:
                query = """
                    SELECT batch_id, model
                    FROM executions
                    WHERE uuid = :execution_id
                """
                row = db.execute(text(query), {"execution_id": execution_id}).fetchone()

                if row:
                    return {
                        "batch_id": str(row.batch_id) if row.batch_id else None,
                        "model": row.model
                    }

                self.logger.warning(f"Execution {execution_id} not found")
                return None

        except Exception as e:
            self.logger.error(f"❌ Error getting execution info for {execution_id}: {e}")
            return None


# Global instance
summary_manager = SummaryManager()
