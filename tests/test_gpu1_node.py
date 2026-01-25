# test_gpu1_node.py
import ray

ray.init(address="auto")

@ray.remote(resources={"node:gpu1": 1})
def test_node_with_wrapper():
    import subprocess
    import os
    
    # Test 1: Direct node call (will likely fail)
    try:
        direct = subprocess.check_output(['node', '--version'], text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        direct = f"FAILED: {e}"
    
    # Test 2: Using wrapper
    try:
        wrapped = subprocess.check_output(
            ['/home/ob/bin/node-wrapper.sh', 'node', '--version'], 
            text=True, 
            stderr=subprocess.STDOUT
        )
    except Exception as e:
        wrapped = f"FAILED: {e}"
    
    return {
        'hostname': subprocess.check_output(['hostname'], text=True).strip(),
        'direct_node': direct,
        'wrapped_node': wrapped,
        'PATH': os.environ.get('PATH', ''),
        'USER': os.environ.get('USER', '')
    }

result = ray.get(test_node_with_wrapper.remote())
print("\n=== Node.js Test on gpu1 ===")
for key, value in result.items():
    print(f"{key}: {value}")

ray.shutdown()
