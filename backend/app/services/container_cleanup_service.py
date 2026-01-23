#!/usr/bin/env python3
"""
Container Cleanup Service - Handles cleanup of CUA containers and orphaned resources
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List

from app.services.cua_container_manager import cua_container_manager
from app.core.config import settings


class ContainerCleanupService:
    """Service for cleaning up CUA containers and managing resource cleanup"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cleanup_interval = settings.CONTAINER_CLEANUP_INTERVAL
        self.max_container_age = settings.MAX_CONTAINER_AGE
        self.is_running = False
        self.cleanup_task = None
        
    async def start_cleanup_service(self):
        """Start the background cleanup service"""
        if self.is_running:
            self.logger.warning("⚠️ Cleanup service is already running")
            return
        
        self.is_running = True
        self.logger.info("🧹 Starting container cleanup service...")
        
        # Start background cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        self.logger.info("✅ Container cleanup service started")
    
    async def stop_cleanup_service(self):
        """Stop the background cleanup service"""
        if not self.is_running:
            self.logger.warning("⚠️ Cleanup service is not running")
            return
        
        self.is_running = False
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("🛑 Container cleanup service stopped")
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while self.is_running:
            try:
                await self._perform_cleanup()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ Error in cleanup loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def _perform_cleanup(self):
        """Perform cleanup of old containers and orphaned resources"""
        try:
            self.logger.info("🧹 Performing scheduled cleanup...")
            
            # Get health status of all containers
            health_status = await cua_container_manager.health_check()
            
            # Clean up unhealthy containers
            unhealthy_containers = [
                container for container in health_status['container_details']
                if not container['healthy']
            ]
            
            if unhealthy_containers:
                self.logger.info(f"🧹 Found {len(unhealthy_containers)} unhealthy containers to clean up")
                
                for container in unhealthy_containers:
                    task_id = container['task_id']
                    self.logger.info(f"🧹 Cleaning up unhealthy container for task: {task_id}")
                    
                    success = await cua_container_manager.cleanup_container(task_id)
                    if success:
                        self.logger.info(f"✅ Cleaned up unhealthy container for task: {task_id}")
                    else:
                        self.logger.warning(f"⚠️ Failed to clean up container for task: {task_id}")
            
            # Clean up old containers
            await self._cleanup_old_containers()
            
            # Clean up orphaned session data
            await self._cleanup_orphaned_session_data()
            
            # Log cleanup summary
            active_count = cua_container_manager.get_active_containers_count()
            self.logger.info(f"🧹 Cleanup completed. Active containers: {active_count}")
            
        except Exception as e:
            self.logger.error(f"❌ Error during cleanup: {e}")
    
    async def _cleanup_orphaned_session_data(self):
        """Clean up orphaned session data from containers that no longer exist"""
        try:
            import os
            import shutil
            from pathlib import Path
            
            # Get list of active container names
            active_containers = cua_container_manager.get_active_containers()
            active_container_names = {info['container_name'] for info in active_containers.values()}
            
            # Find all session directories
            session_base_dirs = [
                "/tmp/streamlit_sessions_",
                "/tmp/streamlit_config_",
                "/tmp/anthropic_config_"
            ]
            
            for base_dir in session_base_dirs:
                if os.path.exists("/tmp"):
                    for item in os.listdir("/tmp"):
                        if item.startswith(base_dir.split("/")[-1]):
                            # Extract container name from directory name
                            container_name = item.replace(base_dir.split("/")[-1], "")
                            
                            # If container is not active, clean up its session data
                            if container_name not in active_container_names:
                                session_dir = f"/tmp/{item}"
                                try:
                                    if os.path.exists(session_dir):
                                        shutil.rmtree(session_dir, ignore_errors=True)
                                        self.logger.info(f"🧹 Cleaned up orphaned session directory: {session_dir}")
                                except Exception as e:
                                    self.logger.warning(f"⚠️ Could not clean up orphaned session directory {session_dir}: {e}")
                                    
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up orphaned session data: {e}")
    
    async def _cleanup_old_containers(self):
        """Clean up containers that are older than max_container_age"""
        try:
            current_time = datetime.now()
            max_age = timedelta(seconds=self.max_container_age)
            
            containers_to_cleanup = []
            
            for task_id, container_info in cua_container_manager.active_containers.items():
                created_at = datetime.fromisoformat(container_info['created_at'])
                age = current_time - created_at
                
                if age > max_age:
                    containers_to_cleanup.append(task_id)
            
            if containers_to_cleanup:
                self.logger.info(f"🧹 Found {len(containers_to_cleanup)} old containers to clean up")
                
                for task_id in containers_to_cleanup:
                    self.logger.info(f"🧹 Cleaning up old container for task: {task_id}")
                    
                    success = await cua_container_manager.cleanup_container(task_id)
                    if success:
                        self.logger.info(f"✅ Cleaned up old container for task: {task_id}")
                    else:
                        self.logger.warning(f"⚠️ Failed to clean up old container for task: {task_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up old containers: {e}")
    
    async def force_cleanup_all(self) -> int:
        """Force cleanup of all active containers"""
        self.logger.info("🧹 Force cleaning up all active containers...")
        
        cleanup_count = await cua_container_manager.cleanup_all_containers()
        
        self.logger.info(f"✅ Force cleanup completed. Cleaned up {cleanup_count} containers")
        return cleanup_count
    
    async def cleanup_orphaned_containers(self) -> int:
        """Clean up containers that are not tracked by the manager"""
        try:
            self.logger.info("🧹 Checking for orphaned containers...")
            
            # Get all containers with our prefix
            import docker
            client = docker.from_env()
            
            our_containers = client.containers.list(
                all=True,
                filters={'name': 'cua-task-'}
            )
            
            tracked_task_ids = set(cua_container_manager.active_containers.keys())
            orphaned_count = 0
            
            for container in our_containers:
                # Extract task_id from container name
                container_name = container.name
                if 'cua-task-' in container_name:
                    # Parse task_id from container name (format: cua-task-{task_id}_{timestamp}_{random_id})
                    parts = container_name.split('-', 2)
                    if len(parts) >= 3:
                        # Split by underscore to get task_id, timestamp, and random_id
                        name_parts = parts[2].split('_')
                        if len(name_parts) >= 1:
                            task_id_part = name_parts[0]  # Get task_id before timestamp
                            
                            # Check if this container is tracked
                            if task_id_part not in tracked_task_ids:
                                self.logger.info(f"🧹 Found orphaned container: {container_name}")
                                
                                try:
                                    if container.status == 'running':
                                        container.stop(timeout=30)
                                    container.remove(force=True)
                                    orphaned_count += 1
                                    self.logger.info(f"✅ Cleaned up orphaned container: {container_name}")
                                except Exception as e:
                                    self.logger.error(f"❌ Failed to clean up orphaned container {container_name}: {e}")
            
            self.logger.info(f"🧹 Orphaned container cleanup completed. Cleaned up {orphaned_count} containers")
            return orphaned_count
            
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up orphaned containers: {e}")
            return 0
    
    def get_cleanup_stats(self) -> Dict:
        """Get cleanup service statistics"""
        return {
            'is_running': self.is_running,
            'cleanup_interval': self.cleanup_interval,
            'max_container_age': self.max_container_age,
            'active_containers': cua_container_manager.get_active_containers_count(),
            'container_details': cua_container_manager.list_active_containers()
        }


# Global instance
container_cleanup_service = ContainerCleanupService()
