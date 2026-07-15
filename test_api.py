import httpx
import os

BASE_URL = "http://127.0.0.1:8000"

def test_health():
    print("Testing health endpoint...")
    url = f"{BASE_URL}/health"
    response = httpx.get(url)
    print(f"GET {url} - Status Code: {response.status_code}")
    print(f"Response: {response.json()}\n")
    assert response.status_code == 200

def test_document_import():
    print("Testing document import endpoint...")
    url = f"{BASE_URL}/api/documents/import"
    
    file_path = "sample_brd.txt"
    if not os.path.exists(file_path):
        # fallback path
        file_path = "backend/sample_brd.txt"
        
    print(f"Uploading file: {file_path}")
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "text/plain")}
        response = httpx.post(url, files=files)
        
    print(f"POST {url} - Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Response JSON keys:", response.json().keys())
        print("Extracted Text preview:")
        print("-" * 40)
        print(response.json().get("extracted_text", "")[:200] + "...")
        print("-" * 40)
    else:
        print(f"Error Response: {response.text}")
    print()

if __name__ == "__main__":
    test_health()
    test_document_import()
