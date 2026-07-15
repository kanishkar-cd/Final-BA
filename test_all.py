import httpx
import os

BASE_URL = "http://127.0.0.1:8000"

def print_banner(title):
    print("=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)

def test_base_health():
    print_banner("1. GET /health")
    url = f"{BASE_URL}/health"
    try:
        response = httpx.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def test_mcp_health():
    print_banner("2. GET /api/mcp/health")
    url = f"{BASE_URL}/api/mcp/health"
    try:
        response = httpx.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def test_document_import():
    print_banner("3. POST /api/documents/import")
    url = f"{BASE_URL}/api/documents/import"
    file_path = "backend/sample_brd.txt"
    if not os.path.exists(file_path):
        file_path = "sample_brd.txt"
        
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found!")
        return
        
    print(f"Uploading: {file_path}")
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "text/plain")}
            response = httpx.post(url, files=files)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Extracted Text Preview:")
            text = response.json().get("extracted_text", "")
            lines = text.strip().split("\n")
            for line in lines[:8]:
                print(f"  {line}")
            if len(lines) > 8:
                print("  ...")
        else:
            print(f"Error Response: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def test_workflow_start():
    print_banner("4. POST /api/workflow/start")
    url = f"{BASE_URL}/api/workflow/start"
    payload = {
        "workflow_id": "WF-TEST-RUN",
        "file_path": "sample_brd.txt",
        "confidence_threshold": 0.8,
        "max_retry_attempts": 3
    }
    print(f"Request Payload: {payload}")
    try:
        response = httpx.post(url, json=payload, timeout=120.0)
        print(f"Status Code: {response.status_code}")
        try:
            print(f"Response JSON: {response.json()}")
        except Exception:
            print(f"Raw Response: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

if __name__ == "__main__":
    test_base_health()
    test_mcp_health()
    test_document_import()
    test_workflow_start()
