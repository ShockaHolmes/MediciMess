#!/usr/bin/env python3
"""
find_api_server.py

Standalone script to detect and print the first reachable Medici API server from a list of candidates.
"""
import requests
import sys

def find_reachable_server(candidates, test_path="/openapi.json", timeout=2):
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

if __name__ == "__main__":
    # Example: python find_api_server.py http://127.0.0.1:8000 http://192.168.1.42:8000
    if len(sys.argv) < 2:
        print("Usage: python find_api_server.py <server_url_1> [<server_url_2> ...]")
        sys.exit(1)
    candidates = sys.argv[1:]
    found = find_reachable_server(candidates)
    if found:
        print(f"Reachable API server found: {found}")
        sys.exit(0)
    else:
        print("No reachable API server found.")
        sys.exit(2)
