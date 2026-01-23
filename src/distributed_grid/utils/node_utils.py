"""Node mapping utilities for consistent node identification across Ray cluster."""

import ray
import socket
from typing import Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


def resolve_hostname_to_ip(hostname: str) -> Optional[str]:
    """
    Resolve hostname to IP address.
    
    Args:
        hostname: Hostname to resolve
        
    Returns:
        IP address if resolvable, None otherwise.
    """
    try:
        ip = socket.gethostbyname(hostname)
        # Handle cases where local hostname resolves to loopback (127.x.x.x)
        # but Ray identifies the head node by its external IP
        if ip.startswith("127."):
            # Try to get the external IP of the current host
            try:
                # This is a common trick to get the IP address used for routing
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                external_ip = s.getsockname()[0]
                s.close()
                return external_ip
            except Exception:
                pass
        return ip
    except socket.gaierror:
        return None


def get_host_to_ray_node_mapping() -> Dict[str, str]:
    """
    Get mapping from host addresses to Ray node IDs.
    
    Returns:
        Dict mapping host addresses (both hostnames and IPs) to Ray node identification strings
        for alive nodes only. Note: Ray uses IP addresses for 'node:IP' resource constraints.
    """
    ray_nodes = ray.nodes()
    host_to_ray_id = {}
    
    for rn in ray_nodes:
        if rn.get("Alive", False):
            node_ip = rn.get("NodeManagerAddress", "")
            if node_ip:
                # Use IP address as the identification string because Ray 
                # identifies nodes by IP in resources (e.g., 'node:192.168.1.101')
                host_to_ray_id[node_ip] = node_ip
                
    return host_to_ray_id


def get_ray_node_id_for_host(host: str) -> Optional[str]:
    """
    Get Ray node ID for a given host address.
    
    Args:
        host: Host address (IP or hostname)
        
    Returns:
        Ray node ID if found, None otherwise.
    """
    mapping = get_host_to_ray_node_mapping()
    
    # Try direct match first
    if host in mapping:
        return mapping[host]
    
    # Try resolving hostname to IP and matching
    ip = resolve_hostname_to_ip(host)
    if ip and ip in mapping:
        return mapping[ip]
        
    return None


def validate_node_mapping(cluster_config) -> bool:
    """
    Validate that all nodes in cluster config have corresponding Ray nodes.
    
    Args:
        cluster_config: Cluster configuration with nodes
        
    Returns:
        True if all nodes found, False otherwise.
    """
    mapping = get_host_to_ray_node_mapping()
    missing_nodes = []
    
    for node in cluster_config.nodes:
        # Try both hostname and resolved IP
        found = node.host in mapping
        if not found:
            ip = resolve_hostname_to_ip(node.host)
            found = ip and ip in mapping
        
        if not found:
            missing_nodes.append(node.host)
    
    if missing_nodes:
        logger.warning("Nodes not found in Ray cluster", nodes=missing_nodes)
        return False
        
    return True
