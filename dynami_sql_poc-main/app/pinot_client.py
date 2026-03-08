import requests
from requests.auth import HTTPBasicAuth

# Hard-coded values for testing
PINOT_BROKER = "https://pinot-broker.mycorp:8099"  # Replace with your Pinot broker URL
PINOT_USER = "your_username"  # Replace with your username
PINOT_PASS = "your_password"  # Replace with your password
PINOT_PATH = "/query/sql"

def test_pinot_auth():
    # Create a session with basic auth
    session = requests.Session()
    session.auth = HTTPBasicAuth(PINOT_USER, PINOT_PASS)
    session.headers.update({"Content-Type": "application/json"})
    session.timeout = (5, 30)  # connect, read timeouts

    # Simple query to test authentication
    test_query = "SELECT 1"
    url = f"{PINOT_BROKER.rstrip('/')}{PINOT_PATH}"

    try:
        response = session.post(url, json={"sql": test_query}, verify=True)
        response.raise_for_status()
        print("Authentication successful!")
        print("Response:", response.json())
        return True
    except requests.exceptions.HTTPError as e:
        print(f"Authentication failed: HTTP Error - {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Authentication failed: {e}")
        return False

if __name__ == "__main__":
    test_pinot_auth()