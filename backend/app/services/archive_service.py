"""
Archive streaming service for generating ZIP files on-the-fly without duplicate storage
"""

import logging
from pathlib import Path
from typing import Generator, List, Dict, Any

from zipstream import ZipStream

from app.core.config import settings

logger = logging.getLogger(__name__)


class ArchiveService:
    """Service for generating streaming ZIP archives"""

    def __init__(self):
        self.results_dir = Path(settings.RESULTS_DIR).resolve()
        # Ensure results directory exists
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def _validate_path(self, path: Path) -> bool:
        """
        Validate that a path is within the results directory
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is safe, False otherwise
        """
        try:
            path.resolve().relative_to(self.results_dir)
            return True
        except ValueError:
            logger.error(f"Security check failed: Path {path} is outside results directory")
            return False

    def _estimate_size(self, directory: Path) -> int:
        """
        Estimate total size of files in a directory
        
        Args:
            directory: Directory to estimate size for
            
        Returns:
            Estimated size in bytes
        """
        total_size = 0
        if directory.exists() and directory.is_dir():
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    try:
                        total_size += file_path.stat().st_size
                    except (OSError, PermissionError):
                        # Skip files we can't access
                        continue
        return total_size

    def _add_files_to_zipstream(
        self,
        zs: ZipStream,
        directory: Path,
        base_path: Path,
        arcname_prefix: str = ""
    ) -> None:
        """
        Add all files from a directory to a ZipStream instance
        
        Args:
            zs: ZipStream instance to add files to
            directory: Directory to collect files from
            base_path: Base path for calculating relative paths
            arcname_prefix: Prefix to add to archive names
        """
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue

            # Calculate relative path
            relative_path = file_path.relative_to(base_path)
            # Use as_posix() to ensure forward slashes for ZIP compatibility (cross-platform)
            relative_path_str = relative_path.as_posix()
            arcname = f"{arcname_prefix}/{relative_path_str}" if arcname_prefix else relative_path_str

            # Add file to ZIP stream with custom arcname
            # zipstream-ng add_path signature: add_path(file_path, arcname=None)
            zs.add_path(str(file_path), arcname)

    def stream_iteration_zip(
        self,
        execution_dir: Path,
        task_identifier: str,
        iteration_number: int
    ) -> Generator[bytes, None, None]:
        """
        Stream a ZIP archive containing all files for a specific iteration
        
        Args:
            execution_dir: Execution directory path
            task_identifier: Task identifier
            iteration_number: Iteration number
            
        Yields:
            Bytes of the ZIP file
        """
        iteration_key = f"iteration_{iteration_number}"
        iteration_dir = execution_dir / task_identifier / iteration_key

        if not iteration_dir.exists():
            raise ValueError(f"Iteration directory not found: {iteration_dir}")

        if not self._validate_path(iteration_dir):
            raise ValueError(f"Iteration directory is outside results directory: {iteration_dir}")

        logger.info(f"Streaming iteration ZIP: {iteration_dir}")

        # Create ZIP stream and add files
        # Archive structure: task_identifier/iteration_N/file_path
        zs = ZipStream()
        self._add_files_to_zipstream(
            zs,
            iteration_dir,
            iteration_dir,
            arcname_prefix=f"{task_identifier}/{iteration_key}"
        )

        # Stream the ZIP
        yield from zs

    def stream_execution_zip(self, execution_dir: Path) -> Generator[bytes, None, None]:
        """
        Stream a ZIP archive containing all files for an execution
        
        Args:
            execution_dir: Execution directory path
            
        Yields:
            Bytes of the ZIP file
        """
        if not execution_dir.exists():
            raise ValueError(f"Execution directory not found: {execution_dir}")

        if not self._validate_path(execution_dir):
            raise ValueError(f"Execution directory is outside results directory: {execution_dir}")

        logger.info(f"Streaming execution ZIP: {execution_dir}")

        # Create ZIP stream and add files
        zs = ZipStream()
        self._add_files_to_zipstream(zs, execution_dir, execution_dir)

        # Stream the ZIP
        yield from zs

    def stream_batch_zip_from_executions(
        self,
        executions: List[Any]
    ) -> Generator[bytes, None, None]:
        """
        Stream a ZIP archive containing all files for all executions in a batch
        
        Args:
            executions: List of execution records
            
        Yields:
            Bytes of the ZIP file
        """
        if not executions:
            raise ValueError("No executions provided")

        logger.info(f"Streaming batch ZIP for {len(executions)} executions")

        # Create ZIP stream and add files from all executions
        zs = ZipStream()
        for execution in executions:
            if not execution.execution_folder_name:
                logger.warning(f"Execution {execution.uuid} has no execution_folder_name, skipping")
                continue

            execution_dir = self.results_dir / execution.execution_folder_name

            if not execution_dir.exists():
                logger.warning(f"Execution directory not found: {execution_dir}, skipping")
                continue

            if not self._validate_path(execution_dir):
                logger.error(f"Execution directory is outside results directory: {execution_dir}, skipping")
                continue

            # Add files with execution folder name as prefix
            # Archive structure: execution_folder_name/file_path
            self._add_files_to_zipstream(
                zs,
                execution_dir,
                execution_dir,
                arcname_prefix=execution.execution_folder_name
            )

        # Stream the ZIP
        yield from zs


# Create singleton instance
archive_service = ArchiveService()

