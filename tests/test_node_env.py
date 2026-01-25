# test_node_env.py
import ray

ray.init(address="auto")

@ray.remote(resources={"node:gpu1": 1})  # Target specific node
def check_node_on_gpu1():
    import subprocess
    import os
    
    results = {}
    try:
        results['which_node'] = subprocess.check_output(['which', 'node'], text=True).strip()
    except subprocess.CalledProcessError as e:
        results['which_node'] = f"Error: {e}"
    
    try:
        results['node_version'] = subprocess.check_output(['node', '--version'], text=True).strip()
    except subprocess.CalledProcessError as e:
        results['node_version'] = f"Error: {e}"
    
    results['PATH'] = os.environ.get('PATH', '')
    results['USER'] = os.environ.get('USER', '')
    results['HOME'] = os.environ.get('HOME', '')
    
    try:
        results['hostname'] = subprocess.check_output(['hostname'], text=True).strip()
    except:
        results['hostname'] = 'unknown'
    
    return results

# Run test
result = ray.get(check_node_on_gpu1.remote())
for key, value in result.items():
    print(f"{key}: {value}")

ray.shutdown()
