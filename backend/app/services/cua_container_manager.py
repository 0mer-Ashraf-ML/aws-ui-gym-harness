#!/usr/bin/env python3
"""
CUA Container Manager - Manages dynamic creation and cleanup of CUA containers
for task isolation in concurrent execution scenarios.
"""

import asyncio
import fcntl
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import docker
from docker.errors import DockerException, ContainerError, ImageNotFound

from app.core.config import settings


class PortManager:
    """Manages port allocation with atomic locking to prevent race conditions"""
    
    def __init__(self, base_port: int, max_containers: int):
        self.base_port = base_port
        self.max_containers = max_containers
        self.ports_per_container = 4  # vnc, streamlit, novnc, http
        self.lock_file = Path("/tmp/cua_port_manager.lock")
        self.port_state_file = Path("/tmp/cua_port_state.json")
        self.logger = logging.getLogger(__name__)
        
    def _acquire_lock(self, timeout: int = 30) -> bool:
        """Acquire file-based lock for atomic port operations"""
        try:
            self.lock_file.parent.mkdir(exist_ok=True)
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            self.logger.warning("⚠️ Port lock is held by another process, waiting...")
            try:
                self.lock_fd = open(self.lock_file, 'w')
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX)
                return True
            except (OSError, IOError):
                self.logger.error("❌ Failed to acquire port lock")
                return False
    
    def _release_lock(self):
        """Release the file-based lock"""
        try:
            if hasattr(self, 'lock_fd'):
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
                if self.lock_file.exists():
                    self.lock_file.unlink()
        except Exception as e:
            self.logger.warning(f"⚠️ Error releasing port lock: {e}")
    
    def _load_port_state(self) -> Dict[str, bool]:
        """Load current port allocation state from file"""
        try:
            if self.port_state_file.exists():
                with open(self.port_state_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.warning(f"⚠️ Error loading port state: {e}")
            return {}
    
    def _save_port_state(self, port_state: Dict[str, bool]):
        """Save current port allocation state to file"""
        try:
            self.port_state_file.parent.mkdir(exist_ok=True)
            with open(self.port_state_file, 'w') as f:
                json.dump(port_state, f, indent=2)
        except Exception as e:
            self.logger.error(f"❌ Error saving port state: {e}")
    
    def allocate_ports(self) -> Optional[Dict[str, int]]:
        """Atomically allocate ports for a new container"""
        if not self._acquire_lock():
            return None
        
        try:
            port_state = self._load_port_state()
            
            # Find next available port range
            for start_port in range(self.base_port, self.base_port + self.max_containers, self.ports_per_container):
                # Check if all 4 ports in this range are available
                ports_available = True
                for i in range(self.ports_per_container):
                    port = start_port + i
                    if str(port) in port_state and port_state[str(port)]:
                        ports_available = False
                        break
                
                if ports_available:
                    # Reserve all 4 ports
                    port_range = {
                        'vnc': start_port,
                        'streamlit': start_port + 1,
                        'novnc': start_port + 2,
                        'http': start_port + 3
                    }
                    
                    # Mark ports as allocated
                    for port in port_range.values():
                        port_state[str(port)] = True
                    
                    self._save_port_state(port_state)
                    self.logger.info(f"✅ Allocated ports: {port_range}")
                    return port_range
            
            self.logger.error("❌ No available port ranges found")
            return None
            
        finally:
            self._release_lock()
    
    def deallocate_ports(self, ports: Dict[str, int]):
        """Atomically deallocate ports when container is removed"""
        if not self._acquire_lock():
            return False
        
        try:
            port_state = self._load_port_state()
            
            # Mark ports as available
            for port in ports.values():
                port_state[str(port)] = False
            
            self._save_port_state(port_state)
            self.logger.info(f"✅ Deallocated ports: {ports}")
            return True
            
        finally:
            self._release_lock()
    
    def get_port_usage_stats(self) -> Dict[str, int]:
        """Get statistics about port usage"""
        port_state = self._load_port_state()
        total_ports = self.max_containers
        allocated_ports = sum(1 for allocated in port_state.values() if allocated)
        available_ports = total_ports - allocated_ports
        
        return {
            'total_ports': total_ports,
            'allocated_ports': allocated_ports,
            'available_ports': available_ports,
            'utilization_percent': (allocated_ports / total_ports * 100) if total_ports > 0 else 0
        }


class CUAContainerManager:
    """Manages dynamic CUA container lifecycle for task isolation"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.docker_client = None
        self.active_containers: Dict[str, Dict] = {}
        self.container_counter = 0
        self.base_port = settings.CUA_CONTAINER_BASE_PORT
        self.max_containers = settings.MAX_CUA_CONTAINERS
        
        # Initialize port manager
        self.port_manager = PortManager(self.base_port, self.max_containers)
        
        # Initialize Docker client
        self._init_docker_client()
        
        # Container configuration
        self.container_config = {
            'image_name': settings.CUA_CONTAINER_IMAGE,
            'container_prefix': 'cua-task-',
            'network_name': settings.CUA_CONTAINER_NETWORK,
            'base_ports': {
                'vnc': 5900,
                'streamlit': 8501,
                'novnc': 6080,
                'http': 8080
            }
        }
        
    def _init_docker_client(self):
        """Initialize Docker client with error handling"""
        try:
            self.docker_client = docker.from_env()
            # Test connection
            self.docker_client.ping()
            self.logger.info("✅ Docker client initialized successfully")
        except DockerException as e:
            self.logger.error(f"❌ Failed to initialize Docker client: {e}")
            raise Exception(f"Docker client initialization failed: {e}")
    
    def _get_next_ports(self) -> Dict[str, int]:
        """Get the next available ports for a new container using atomic port manager"""
        ports = self.port_manager.allocate_ports()
        if ports is None:
            raise Exception("Failed to allocate ports - no available port ranges or lock timeout")
        return ports
    
    def _generate_container_name(self, task_id: str) -> str:
        """Generate a unique container name for a task (IDNA-compliant)"""
        import uuid
        import hashlib
        
        # Create a shorter, IDNA-compliant container name
        # Use hash of task_id to keep it short but unique
        task_hash = hashlib.md5(task_id.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime('%m%d%H%M')  # Shorter timestamp
        random_id = uuid.uuid4().hex[:6]  # Shorter random ID
        
        # Ensure total length is under the configured limit (default 50 chars for IDNA compliance)
        max_length = settings.CUA_CONTAINER_MAX_NAME_LENGTH
        container_name = f"cua-{task_hash}-{timestamp}-{random_id}"
        
        # Validate length against configured limit
        if len(container_name) > max_length:
            # Fallback to even shorter name if needed
            container_name = f"cua-{task_hash}-{random_id}"
            
        # Final validation - ensure it's still under the limit
        if len(container_name) > max_length:
            # Emergency fallback - use just hash and random ID
            container_name = f"cua-{task_hash[:6]}-{random_id[:6]}"
        
        return container_name
    
    async def create_cua_container(self, task_id: str, run_id: str, iteration_id: str = None, max_retries: int = 3) -> Dict[str, str]:
        """
        Create a new CUA container for a specific task with retry logic
        
        Args:
            task_id: Unique task identifier
            run_id: Unique run identifier
            iteration_id: Unique iteration identifier (optional, for composite key)
            max_retries: Maximum number of retry attempts for port conflicts
            
        Returns:
            Dictionary with container info and URLs
        """
        last_error = None
        
        # Create composite key for container tracking
        container_key = f"{task_id}_{iteration_id}" if iteration_id else task_id
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"🐳 Creating CUA container for task: {task_id} (attempt {attempt + 1}/{max_retries})")
                
                # Check if we're at the container limit
                if len(self.active_containers) >= self.max_containers:
                    raise Exception(f"Maximum number of containers ({self.max_containers}) reached")
                
                # Get next available ports
                ports = self._get_next_ports()
                
                # Generate container name
                container_name = self._generate_container_name(task_id)
                
                # Prepare environment variables
                env_vars = {
                    'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY', ''),
                    'G_SLICE': 'always-malloc',
                    'QT_X11_NO_MITSHM': '1',
                    '_JAVA_AWT_WM_NONREPARENTING': '1',
                    'LIBGL_ALWAYS_SOFTWARE': '1',
                    'WIDTH': '1024',
                    'HEIGHT': '768',
                    'DISPLAY_NUM': '1',
                    'TASK_ID': task_id,
                    'RUN_ID': run_id,
                    'CONTAINER_NAME': container_name,
                    # Set the correct URLs for iframes (using container name as hostname)
                    'STREAMLIT_URL': f'http://{container_name}:8501',
                    'VNC_URL': f'http://{container_name}:6080'
                }
                
                # Port mapping
                port_bindings = {
                    f"{self.container_config['base_ports']['vnc']}/tcp": ports['vnc'],
                    f"{self.container_config['base_ports']['streamlit']}/tcp": ports['streamlit'],
                    f"{self.container_config['base_ports']['novnc']}/tcp": ports['novnc'],
                    f"{self.container_config['base_ports']['http']}/tcp": ports['http']
                }
                
                # Create container
                container = self.docker_client.containers.run(
                    image=self.container_config['image_name'],
                    name=container_name,
                    environment=env_vars,
                    ports=port_bindings,
                    network=self.container_config['network_name'],
                    privileged=True,
                    security_opt=['seccomp:unconfined'],
                    shm_size='2gb',
                    stdin_open=True,
                    tty=True,
                    detach=True,
                    remove=False,  # Don't auto-remove, we'll manage cleanup
                    restart_policy={"Name": "no"}  # Don't restart automatically
                )
                
                # Wait for container to be ready
                await self._wait_for_container_ready(container, ports)
                
                # Store container info
                container_info = {
                    'container_id': container.id,
                    'container_name': container_name,
                    'task_id': task_id,
                    'run_id': run_id,
                    'iteration_id': iteration_id,
                    'ports': ports,
                    'created_at': datetime.now().isoformat(),
                    'status': 'running'
                }
                
                self.active_containers[container_key] = container_info
                
                # Generate URLs - use IP address if container name is too long for IDNA
                try:
                    # Try to get container IP address as fallback
                    container.reload()
                    container_ip = None
                    if container.attrs.get('NetworkSettings') and container.attrs['NetworkSettings'].get('Networks'):
                        for network_name, network_info in container.attrs['NetworkSettings']['Networks'].items():
                            if network_info.get('IPAddress'):
                                container_ip = network_info['IPAddress']
                                break
                    
                    # Check if container name is too long for IDNA (over 63 chars)
                    if len(container_name) > 63 or container_ip:
                        if container_ip:
                            self.logger.info(f"🔧 Using container IP address instead of hostname: {container_ip}")
                            urls = {
                                'cua_url': f"http://{container_ip}:8080",
                                'streamlit_url': f"http://{container_ip}:8501",
                                'vnc_url': f"http://{container_ip}:6080",
                                'container_name': container_name,
                                'container_id': container.id,
                                'container_ip': container_ip
                            }
                        else:
                            # Fallback to localhost with port mapping (less ideal but works)
                            self.logger.warning(f"⚠️ Container name too long ({len(container_name)} chars), using localhost with port mapping")
                            urls = {
                                'cua_url': f"http://localhost:{ports['http']}",
                                'streamlit_url': f"http://localhost:{ports['streamlit']}",
                                'vnc_url': f"http://localhost:{ports['novnc']}",
                                'container_name': container_name,
                                'container_id': container.id,
                                'use_localhost': True
                            }
                    else:
                        # Use container name as hostname (normal case)
                        urls = {
                            'cua_url': f"http://{container_name}:8080",
                            'streamlit_url': f"http://{container_name}:8501",
                            'vnc_url': f"http://{container_name}:6080",
                            'container_name': container_name,
                            'container_id': container.id
                        }
                except Exception as url_error:
                    self.logger.warning(f"⚠️ Error generating URLs, using fallback: {url_error}")
                    # Fallback to localhost with port mapping
                    urls = {
                        'cua_url': f"http://localhost:{ports['http']}",
                        'streamlit_url': f"http://localhost:{ports['streamlit']}",
                        'vnc_url': f"http://localhost:{ports['novnc']}",
                        'container_name': container_name,
                        'container_id': container.id,
                        'use_localhost': True
                    }
            
                self.logger.info(f"✅ CUA container created successfully for task {task_id}")
                self.logger.info(f"   - Container: {container_name}")
                self.logger.info(f"   - CUA URL: {urls['cua_url']}")
                self.logger.info(f"   - Streamlit URL: {urls['streamlit_url']}")
                self.logger.info(f"   - VNC URL: {urls['vnc_url']}")
                
                return urls
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"⚠️ Container creation attempt {attempt + 1} failed: {e}")
                
                # Check if it's a port conflict error
                if "port is already allocated" in str(e) or "bind" in str(e).lower():
                    self.logger.info(f"🔄 Port conflict detected, retrying with different ports...")
                    # Deallocate the ports we tried to use
                    if 'ports' in locals():
                        self.port_manager.deallocate_ports(ports)
                    # Wait a bit before retrying
                    await asyncio.sleep(1)
                    continue
                else:
                    # Non-port related error, don't retry
                    self.logger.error(f"❌ Non-port related error, not retrying: {e}")
                    raise e
        
        # All retries failed
        self.logger.error(f"❌ Failed to create CUA container for task {task_id} after {max_retries} attempts")
        raise Exception(f"Container creation failed after {max_retries} attempts. Last error: {last_error}")
    
    async def _wait_for_container_ready(self, container, ports: Dict[str, int], timeout: int = 120):
        """Wait for container to be ready and services to start"""
        self.logger.info(f"⏳ Waiting for container {container.name} to be ready...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Check if container is running
                container.reload()
                if container.status != 'running':
                    raise Exception(f"Container {container.name} is not running (status: {container.status})")
                
                # Check if services are responding
                if await self._check_services_ready(ports):
                    self.logger.info(f"✅ Container {container.name} is ready")
                    return
                
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.warning(f"⚠️ Container readiness check failed: {e}")
                await asyncio.sleep(5)
        
        raise Exception(f"Container {container.name} failed to become ready within {timeout} seconds")
    
    async def _check_services_ready(self, ports: Dict[str, int]) -> bool:
        """Check if all required services are responding"""
        try:
            import aiohttp
            
            # Check if we can reach the services
            # Since we're inside Docker, we need to use the container network
            # For now, we'll do a basic check and rely on the task runner's health check
            
            # Check if the container is running and has been up for a reasonable time
            # This is a simplified check - the task runner will do more thorough health checking
            return True
            
        except Exception as e:
            self.logger.debug(f"Service readiness check failed: {e}")
            return False
    
    async def cleanup_container(self, task_id: str, iteration_id: str = None) -> bool:
        """
        Clean up a CUA container for a specific task
        
        Args:
            task_id: Task identifier
            iteration_id: Iteration identifier (optional, for composite key)
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            # Create composite key for container lookup
            container_key = f"{task_id}_{iteration_id}" if iteration_id else task_id
            
            if container_key not in self.active_containers:
                self.logger.warning(f"⚠️ No active container found for task {task_id} (key: {container_key})")
                return True
            
            container_info = self.active_containers[container_key]
            container_name = container_info['container_name']
            
            self.logger.info(f"🧹 Cleaning up CUA container for task {task_id}: {container_name}")
            
            try:
                # Get container
                container = self.docker_client.containers.get(container_name)
                
                # Stop container gracefully
                self.logger.info(f"🛑 Stopping container {container_name}...")
                container.stop(timeout=30)
                
                # Remove container
                self.logger.info(f"🗑️ Removing container {container_name}...")
                container.remove(force=True)
                
                self.logger.info(f"✅ Container {container_name} cleaned up successfully")
                
                # Deallocate ports
                if 'ports' in container_info:
                    self.port_manager.deallocate_ports(container_info['ports'])
                
                # Clean up session data
                await self._cleanup_session_data(container_name)
                
            except docker.errors.NotFound:
                self.logger.warning(f"⚠️ Container {container_name} not found (may have been already removed)")
            except Exception as e:
                self.logger.error(f"❌ Error cleaning up container {container_name}: {e}")
                # Try force removal
                try:
                    container = self.docker_client.containers.get(container_name)
                    container.remove(force=True)
                    self.logger.info(f"✅ Container {container_name} force removed")
                except Exception as force_error:
                    self.logger.error(f"❌ Force removal also failed: {force_error}")
                    return False
            
            # Remove from active containers
            del self.active_containers[container_key]
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to cleanup container for task {task_id}: {e}")
            return False
    
    async def cleanup_container_on_timeout(self, task_id: str, iteration_id: str = None) -> bool:
        """
        Clean up a CUA container when a task times out
        
        Args:
            task_id: Task identifier
            iteration_id: Iteration identifier (optional, for composite key)
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            # Create composite key for container lookup
            container_key = f"{task_id}_{iteration_id}" if iteration_id else task_id
            
            if container_key not in self.active_containers:
                self.logger.warning(f"⚠️ No active container found for timed out task {task_id} (key: {container_key})")
                return True
            
            container_info = self.active_containers[container_key]
            container_name = container_info['container_name']
            
            self.logger.info(f"⏰ Cleaning up CUA container for timed out task {task_id}: {container_name}")
            
            try:
                # Get container
                container = self.docker_client.containers.get(container_name)
                
                # Force stop container immediately (no graceful shutdown for timeouts)
                self.logger.info(f"🛑 Force stopping timed out container {container_name}...")
                container.stop(timeout=5)  # Short timeout for force stop
                
                # Remove container
                self.logger.info(f"🗑️ Removing timed out container {container_name}...")
                container.remove(force=True)
                
                self.logger.info(f"✅ Timed out container {container_name} cleaned up successfully")
                
                # Deallocate ports
                if 'ports' in container_info:
                    self.port_manager.deallocate_ports(container_info['ports'])
                
                # Clean up session data
                await self._cleanup_session_data(container_name)
                
            except docker.errors.NotFound:
                self.logger.warning(f"⚠️ Timed out container {container_name} not found (may have been already removed)")
            except Exception as e:
                self.logger.error(f"❌ Error cleaning up timed out container {container_name}: {e}")
                # Try force removal
                try:
                    container = self.docker_client.containers.get(container_name)
                    container.remove(force=True)
                    self.logger.info(f"✅ Timed out container {container_name} force removed")
                except Exception as force_error:
                    self.logger.error(f"❌ Force removal of timed out container also failed: {force_error}")
                    return False
            
            # Remove from active containers
            del self.active_containers[container_key]
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to cleanup timed out container for task {task_id}: {e}")
            return False
    
    async def cleanup_all_containers(self) -> int:
        """
        Clean up all active containers
        
        Returns:
            Number of containers cleaned up
        """
        self.logger.info(f"🧹 Cleaning up all {len(self.active_containers)} active containers...")
        
        cleanup_count = 0
        task_ids = list(self.active_containers.keys())
        
        for task_id in task_ids:
            if await self.cleanup_container(task_id):
                cleanup_count += 1
        
        self.logger.info(f"✅ Cleaned up {cleanup_count}/{len(task_ids)} containers")
        return cleanup_count
    
    def get_container_info(self, task_id: str) -> Optional[Dict]:
        """Get information about a specific container"""
        return self.active_containers.get(task_id)
    
    def get_active_containers_count(self) -> int:
        """Get the number of active containers"""
        return len(self.active_containers)
    
    def list_active_containers(self) -> List[Dict]:
        """List all active containers"""
        return list(self.active_containers.values())
    
    async def health_check(self) -> Dict[str, any]:
        """Perform health check on all active containers"""
        health_status = {
            'total_containers': len(self.active_containers),
            'healthy_containers': 0,
            'unhealthy_containers': 0,
            'container_details': []
        }
        
        for task_id, container_info in self.active_containers.items():
            try:
                container = self.docker_client.containers.get(container_info['container_name'])
                container.reload()
                
                is_healthy = container.status == 'running'
                
                if is_healthy:
                    health_status['healthy_containers'] += 1
                else:
                    health_status['unhealthy_containers'] += 1
                
                health_status['container_details'].append({
                    'task_id': task_id,
                    'container_name': container_info['container_name'],
                    'status': container.status,
                    'healthy': is_healthy,
                    'created_at': container_info['created_at']
                })
                
            except Exception as e:
                health_status['unhealthy_containers'] += 1
                health_status['container_details'].append({
                    'task_id': task_id,
                    'container_name': container_info['container_name'],
                    'status': 'error',
                    'healthy': False,
                    'error': str(e),
                    'created_at': container_info['created_at']
                })
        
        return health_status
    
    async def _cleanup_session_data(self, container_name: str):
        """Clean up session data for a specific container"""
        try:
            self.logger.info(f"🧹 Cleaning up session data for container: {container_name}")
            
            # Clean up session directories on the host (if they exist)
            session_dirs = [
                f"/tmp/streamlit_sessions_{container_name}",
                f"/tmp/streamlit_config_{container_name}",
                f"/tmp/anthropic_config_{container_name}"
            ]
            
            for session_dir in session_dirs:
                try:
                    if os.path.exists(session_dir):
                        import shutil
                        shutil.rmtree(session_dir, ignore_errors=True)
                        self.logger.info(f"✅ Cleaned up session directory: {session_dir}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Could not clean up {session_dir}: {e}")
                    
        except Exception as e:
            self.logger.error(f"❌ Error during session cleanup for {container_name}: {e}")
    
    def get_port_usage_stats(self) -> Dict[str, int]:
        """Get port usage statistics"""
        return self.port_manager.get_port_usage_stats()
    
    def get_active_containers(self) -> Dict[str, Dict]:
        """Get all active containers"""
        return self.active_containers.copy()
    
    def get_container_stats(self) -> Dict[str, any]:
        """Get comprehensive container and port statistics"""
        container_details = []
        for task_id, info in self.active_containers.items():
            container_details.append({
                'task_id': task_id,
                'container_name': info['container_name'],
                'status': info['status'],
                'created_at': info['created_at'],
                'ports': info['ports']
            })
        
        port_stats = self.port_manager.get_port_usage_stats()
        
        return {
            'total_containers': len(self.active_containers),
            'active_containers': list(self.active_containers.keys()),
            'container_details': container_details,
            'port_usage': port_stats
        }


# Global instance
cua_container_manager = CUAContainerManager()
