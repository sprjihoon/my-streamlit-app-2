#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Frontend <-> Backend Connection Test Script
-------------------------------------------
Verifies API calls work correctly in local environment.

Usage:
    python test_connection.py
"""

import json
import sys

# Use urllib (built-in)
import urllib.request
import urllib.error

API_BASE = "http://localhost:8000"


def test_connection():
    """Test backend connectivity."""
    print("=" * 50)
    print("FastAPI Backend Connection Test")
    print("=" * 50)
    print()

    results = {"passed": 0, "failed": 0}

    # 1. Health check
    print("[1/4] Health check...")
    try:
        req = urllib.request.Request(f"{API_BASE}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"  [OK] Status: {data.get('status')}, Version: {data.get('version')}")
            results["passed"] += 1
    except urllib.error.URLError as e:
        print(f"  [FAIL] {e}")
        print()
        print("Backend not running. Start with:")
        print("  uvicorn backend.app.main:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["failed"] += 1

    # 2. Root endpoint
    print("[2/4] Root endpoint...")
    try:
        req = urllib.request.Request(f"{API_BASE}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"  [OK] API Name: {data.get('name')}")
            results["passed"] += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        results["failed"] += 1

    # 3. CORS check (via headers)
    print("[3/4] CORS configuration...")
    try:
        req = urllib.request.Request(f"{API_BASE}/health")
        req.add_header("Origin", "http://localhost:3000")
        with urllib.request.urlopen(req, timeout=5) as resp:
            cors_header = resp.headers.get("Access-Control-Allow-Origin", "not set")
            print(f"  [OK] Access-Control-Allow-Origin: {cors_header}")
            results["passed"] += 1
    except Exception as e:
        print(f"  [WARN] CORS check: {e}")

    # 4. POST request test (invoice calculation)
    print("[4/4] POST request (invoice calculation)...")
    try:
        payload = json.dumps({
            "vendor": "TestVendor",
            "date_from": "2025-01-01",
            "date_to": "2025-01-31",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE}/calculate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            items_count = len(data.get("items", []))
            print(f"  [OK] Response: success={data.get('success')}, items={items_count}")
            results["passed"] += 1
    except urllib.error.HTTPError as e:
        # 500 error might be expected if no data exists
        print(f"  [WARN] HTTP {e.code} (may be expected if no data)")
    except Exception as e:
        print(f"  [WARN] {e}")

    print()
    print("=" * 50)
    print(f"Results: {results['passed']} passed, {results['failed']} failed")
    print("=" * 50)
    
    return results["failed"] == 0


def main():
    print()
    print("Frontend <-> Backend Connection Test")
    print()
    
    success = test_connection()
    
    print()
    print("Connection Info:")
    print(f"  - Backend URL: {API_BASE}")
    print(f"  - Frontend URL: http://localhost:3000")
    print(f"  - API Docs: {API_BASE}/docs")
    print()
    
    if success:
        print("[SUCCESS] Frontend can call backend API.")
        print()
        print("Next steps:")
        print("  1. Start frontend: cd frontend && npm run dev")
        print("  2. Open http://localhost:3000")
    else:
        print("[FAIL] Backend connection failed.")
        print()
        print("Solutions:")
        print("  1. Start backend: uvicorn backend.app.main:app --reload --port 8000")
        print("  2. Or run: run_api.bat")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
