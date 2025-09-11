#!/usr/bin/env python3
"""
Simple integration test for the DocuSign Flask API
"""
import requests
import json
import sys
import os
from dotenv import load_dotenv

def test_api_endpoints(base_url="http://localhost:5000"):
    """Test the Flask API endpoints."""
    print("Testing DocuSign Flask API Integration...")
    
    # Test 1: Get envelopes (should return empty initially)
    print("\n1. Testing GET /envelopes")
    try:
        response = requests.get(f"{base_url}/envelopes")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Found {len(data)} envelopes")
        else:
            print(f"   Error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("   Error: Cannot connect to Flask server. Make sure it's running on port 5000.")
        return False
    
    # Test 2: Get stats
    print("\n2. Testing GET /envelopes/stats")
    try:
        response = requests.get(f"{base_url}/envelopes/stats")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Total envelopes: {data.get('total_envelopes', 0)}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Sync envelopes (requires DocuSign credentials)
    print("\n3. Testing POST /sync/envelopes")
    try:
        response = requests.post(f"{base_url}/sync/envelopes", 
                               json={"days_back": 7})
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Sync result: {data.get('message', 'Success')}")
            print(f"   Synced count: {data.get('synced_count', 0)}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 4: Test webhook endpoint (mock request)
    print("\n4. Testing POST /docusign/webhook")
    mock_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <DocuSignEnvelopeInformation>
        <EnvelopeStatus>
            <EnvelopeID>test-envelope-id</EnvelopeID>
            <Subject>Test Envelope</Subject>
            <Status>sent</Status>
            <Created>2024-01-01T12:00:00Z</Created>
            <Sent>2024-01-01T12:01:00Z</Sent>
            <Recipients>
                <Recipient>
                    <Email>test@example.com</Email>
                    <UserName>Test User</UserName>
                    <Status>sent</Status>
                    <RoutingOrder>1</RoutingOrder>
                </Recipient>
            </Recipients>
        </EnvelopeStatus>
    </DocuSignEnvelopeInformation>"""
    
    try:
        response = requests.post(f"{base_url}/docusign/webhook", 
                               data=mock_xml,
                               headers={"Content-Type": "application/xml"})
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   Webhook processed successfully")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n✅ Integration test completed!")
    return True

if __name__ == "__main__":
    # Load environment to check if we have DocuSign credentials
    load_dotenv()
    
    if not all([os.getenv("INTEGRATION_KEY"), os.getenv("USER_ID"), os.getenv("RSA_KEY")]):
        print("⚠️  Warning: DocuSign credentials not found in environment.")
        print("   The /sync/envelopes endpoint will fail without proper credentials.")
        print("   Please check your .env file.\n")
    
    success = test_api_endpoints()
    sys.exit(0 if success else 1)