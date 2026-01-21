import paramiko
import threading
import time
from typing import Tuple, Optional
from functools import lru_cache
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class SSHConnection:
    def __init__(self, host: str, timeout: int = 10):
        self.host = host
        self.timeout = timeout
        self.client = None
        self.last_used = time.time()
        self.command_count = 0
        self._connect()
    
    def _connect(self):
        """Establish SSH connection"""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host, timeout=self.timeout)
        logger.info(f"Connected to {self.host}")
    
    def execute(self, command: str, timeout: int = 30) -> Tuple[str, str]:
        """Execute command on remote host"""
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            self.command_count += 1
            self.last_used = time.time()
            return stdout.read().decode().strip(), stderr.read().decode().strip()
        except Exception as e:
            logger.error(f"Command failed on {self.host}: {e}")
            raise
    
    def close(self):
        """Close SSH connection"""
        if self.client:
            self.client.close()
            logger.info(f"Closed connection to {self.host}")
    
    def is_alive(self) -> bool:
        """Check if connection is still alive"""
        try:
            self.client.exec_command("echo 'ping'")
            return True
        except:
            return False

class SSHPool:
    def __init__(self, max_size: int = 10, timeout: int = 10):
        self.pool: Dict[str, SSHConnection] = {}
        self.lock = threading.RLock()
        self.max_size = max_size
        self.timeout = timeout
    
    def get_connection(self, host: str) -> SSHConnection:
        """Get or create connection from pool"""
        with self.lock:
            if host not in self.pool:
                if len(self.pool) >= self.max_size:
                    # Evict least recently used
                    lru_host = min(self.pool, key=lambda h: self.pool[h].last_used)
                    self.pool[lru_host].close()
                    del self.pool[lru_host]
                
                self.pool[host] = SSHConnection(host, self.timeout)
            
            conn = self.pool[host]
            if not conn.is_alive():
                conn.close()
                self.pool[host] = SSHConnection(host, self.timeout)
            
            return self.pool[host]
    
    def execute(self, host: str, command: str, timeout: int = 30) -> Tuple[str, str]:
        """Execute command on host with automatic reconnection"""
        conn = self.get_connection(host)
        return conn.execute(command, timeout)
    
    def execute_all(self, hosts: list, command: str) -> Dict[str, Tuple[str, str]]:
        """Execute command on all hosts in parallel"""
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as executor:
            futures = {
                executor.submit(self.execute, host, command): host 
                for host in hosts
            }
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    results[host] = future.result()
                except Exception as e:
                    logger.error(f"Failed on {host}: {e}")
                    results[host] = ("", str(e))
        return results
    
    def close_all(self):
        """Close all connections"""
        with self.lock:
            for host, conn in self.pool.items():
                conn.close()
            self.pool.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close_all()

# Global pool instance
_pool: Optional[SSHPool] = None

def get_pool(max_size: int = 10) -> SSHPool:
    global _pool
    if _pool is None:
        _pool = SSHPool(max_size)
    return _pool
