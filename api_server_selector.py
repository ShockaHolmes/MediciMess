"""
api_server_selector.py

Utility to select the first reachable Medici API server from a list of candidates, for integration into your project.
"""
import requests

def find_reachable_api_server(candidates, test_path="/openapi.json", timeout=2):
    """
    Try each server in candidates, return the first reachable base URL.
    """
    for base_url in candidates:
        try:
            url = base_url.rstrip("/") + test_path
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return base_url
        except Exception:
            continue
    return None

# Example usage in your project:
def get_api_base_url():
    # Add your teammate's IP or hostname here
    candidates = [
        "http://127.0.0.1:8000",           # Localhost
        "http://192.168.1.42:8000",        # Example teammate IP (replace as needed)
        # Add more addresses as needed
    ]
    found = find_reachable_api_server(candidates)
    if not found:
        raise RuntimeError("No reachable Medici API server found.")
    return found
