import os
import hashlib
import subprocess
from typing import Set, List
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, exclude_patterns: List[str]):
        self.exclude_patterns = exclude_patterns
        self.manifest_file = '.grid_sync_manifest'
    
    def generate_file_hash(self, filepath: str) -> str:
        """Generate MD5 hash for file"""
        md5 = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5.update(chunk)
            return md5.hexdigest()
        except:
            return ""
    
    def generate_local_manifest(self) -> dict:
        """Generate manifest of local files"""
        manifest = {}
        for root, dirs, files in os.walk('.'):
            # Skip excluded patterns
            dirs[:] = [d for d in dirs if not self._should_exclude(f"{root}/{d}")]
            
            for file in files:
                filepath = os.path.join(root, file)
                if not self._should_exclude(filepath):
                    manifest[filepath] = self.generate_file_hash(filepath)
        
        return manifest
    
    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded"""
        for pattern in self.exclude_patterns:
            if pattern in path:
                return True
        return False
    
    def get_changed_files(self, remote_manifest: dict, local_manifest: dict) -> List[str]:
        """Get list of changed files"""
        changed = []
        for filepath, local_hash in local_manifest.items():
            remote_hash = remote_manifest.get(filepath, "")
            if local_hash != remote_hash:
                changed.append(filepath)
        return changed
    
    def smart_sync(self, host: str, remote_path: str) -> None:
        """Sync only changed files"""
        # Generate local manifest
        local_manifest = self.generate_local_manifest()
        
        # Get remote manifest
        try:
            remote_manifest_cmd = f"cat {remote_path}/.grid_sync_manifest 2>/dev/null"
            result = subprocess.run(
                f'ssh {host} "{remote_manifest_cmd}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            remote_manifest = json.loads(result.stdout) if result.stdout else {}
        except:
            remote_manifest = {}
        
        # Find changed files
        changed_files = self.get_changed_files(remote_manifest, local_manifest)
        
        if not changed_files:
            logger.info("No files changed, skipping sync")
            return
        
        logger.info(f"Syncing {len(changed_files)} changed files to {host}:{remote_path}")
        
        # Create list file
        with open('/tmp/grid_sync_list', 'w') as f:
            for file in changed_files:
                f.write(f"{file}\n")
        
        # Rsync only changed files
        cmd = (
            f"rsync -azP --files-from=/tmp/grid_sync_list . "
            f"{host}:{remote_path}/"
        )
        
        subprocess.run(cmd, shell=True, check=True)
        
        # Update remote manifest
        manifest_path = f"{remote_path}/.grid_sync_manifest"
        manifest_json = json.dumps(local_manifest)
        update_cmd = f'echo \'{manifest_json}\' > {manifest_path}'
        subprocess.run(f'ssh {host} "{update_cmd}"', shell=True)
        
        logger.info("Sync complete")
