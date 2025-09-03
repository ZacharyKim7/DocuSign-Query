# requirements: pyjwt, requests, docusign-esign
import dotenv, os, time, jwt, requests
from datetime import datetime, timedelta
from docusign_esign import ApiClient
from docusign_esign.apis import EnvelopesApi
from docusign_esign.client.api_exception import ApiException

def docusign_jwt_login(
    client_id: str,                 # Integration Key (GUID)
    impersonated_user_id: str,      # GUID of the user you'll act as
    private_key: str,          # path to your RSA private key file
    demo: bool = True,              # True = sandbox, False = production
    scopes = ("signature", "impersonation"),
    token_lifetime_sec: int = 3600
):
    """
    Returns: (api_client, account_id, access_token)
    api_client.host is set to the correct .../restapi base for subsequent calls.
    """
    auth_server = "account-d.docusign.com" if demo else "account.docusign.com"

    api_client = ApiClient()
    api_client.set_oauth_host_name(auth_server)

    # 1) Request OAuth access token via JWT (no browser once consent is given)
    try:
        token = api_client.request_jwt_user_token(
            client_id,
            impersonated_user_id,
            auth_server,           # OAuth host (no scheme)
            private_key,
            token_lifetime_sec,
            list(scopes)
        )
    except ApiException as e:
        # Common causes: missing consent (error: consent_required), bad key format, wrong auth_server
        raise RuntimeError(f"JWT token request failed: {e}") from e

    access_token = token.access_token

    # 2) Discover the user's default account + base_uri, then set API host
    user_info = api_client.get_user_info(access_token)
    default_acct = next(a for a in user_info.accounts if a.is_default)
    account_id = default_acct.account_id
    api_client.host = default_acct.base_uri + "/restapi"

    # Attach the bearer token so subsequent SDK calls use it
    api_client.set_default_header("Authorization", f"Bearer {access_token}")

    return api_client, account_id, access_token

# --- Example usage ---
if __name__ == "__main__":
    dotenv.load_dotenv()
    CLIENT_ID = os.getenv("INTEGRATION_KEY")
    USER_ID = os.getenv("USER_ID")              # GUID of the user to impersonate
    RSA_KEY = os.getenv("RSA_KEY")

    api_client, account_id, access_token = docusign_jwt_login(
        client_id=CLIENT_ID,
        impersonated_user_id=USER_ID,
        private_key=RSA_KEY,
        demo=True
    )

    # Make an API call (e.g., list recent envelopes)
    envelopes_api = EnvelopesApi(api_client)
    
    # FIXED: Add from_date parameter (30 days ago)
    from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Option 1: Using from_date parameter
    results = envelopes_api.list_status_changes(
        account_id, 
        from_date=from_date
    )
    
    # Option 2: You can also add other filters like status
    # results = envelopes_api.list_status_changes(
    #     account_id,
    #     from_date=from_date,
    #     status='completed,sent,delivered'  # filter by status
    # )
    
    # Option 3: If you want to specify specific envelope IDs instead
    # envelope_ids = "your-envelope-id-1,your-envelope-id-2"
    # results = envelopes_api.list_status_changes(
    #     account_id,
    #     envelope_ids=envelope_ids
    # )
    
    print(f"Found {len(results.envelopes or [])} envelopes")
    
    # Print some envelope details
    if results.envelopes:
        for envelope in results.envelopes:
            print(f"Envelope ID: {envelope.envelope_id}")
            print(f"Status: {envelope.status}")
            print(f"Subject: {envelope.email_subject}")
            print(f"Created: {envelope.created_date_time}")
            print("---")


# Consent URL for first-time setup:
# https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=574290d2-a290-4487-adeb-7e3fea38b8bc&redirect_uri=https://www.paulsoncrm.com