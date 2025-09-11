# docusign_client.py
import os
from datetime import datetime, timedelta, timezone
from docusign_esign import ApiClient
from docusign_esign.apis import EnvelopesApi
from docusign_esign.client.api_exception import ApiException

def _load_private_key_bytes(value: str) -> bytes:
    """Accept either raw PEM content or filesystem path."""
    if not value:
        raise RuntimeError("RSA key not provided (env RSA_KEY).")
    if "BEGIN" in value and "PRIVATE KEY" in value:
        return value.encode("utf-8")
    if not os.path.exists(value):
        raise RuntimeError(f"RSA_KEY path not found: {value}")
    with open(value, "rb") as f:
        return f.read()

def docusign_jwt_login(
    client_id: str,
    impersonated_user_id: str,
    private_key: str,
    demo: bool = True,
    scopes = ("signature", "impersonation"),
    token_lifetime_sec: int = 3600
):
    """Returns: (api_client, account_id, access_token)"""
    auth_server = "account-d.docusign.com" if demo else "account.docusign.com"
    
    api_client = ApiClient()
    api_client.set_oauth_host_name(auth_server)
    
    private_key_bytes = _load_private_key_bytes(private_key)
    
    try:
        token = api_client.request_jwt_user_token(
            client_id,
            impersonated_user_id,
            auth_server,
            private_key_bytes,
            token_lifetime_sec,
            list(scopes),
        )
    except ApiException as e:
        raise RuntimeError(f"JWT token request failed: {e}") from e
    
    access_token = token.access_token
    
    # Discover default account & base_uri, set api_client.host
    user_info = api_client.get_user_info(access_token)
    default_acct = next(a for a in user_info.accounts if a.is_default)
    account_id = default_acct.account_id
    api_client.host = default_acct.base_uri + "/restapi"
    
    # Attach bearer token for SDK calls
    api_client.set_default_header("Authorization", f"Bearer {access_token}")
    
    return api_client, account_id, access_token

def fetch_envelopes(api_client: ApiClient, account_id: str, days_back: int = 30) -> list:
    """Fetch envelopes from DocuSign API with detailed information."""
    envelopes_api = EnvelopesApi(api_client)
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    try:
        # Get list of envelopes
        results = envelopes_api.list_status_changes(
            account_id, 
            from_date=from_date,
            include="recipients,custom_fields"
        )
        
        envelope_list = []
        for envelope in (results.envelopes or []):
            # Get detailed envelope information
            detailed_envelope = envelopes_api.get_envelope(
                account_id=account_id, 
                envelope_id=envelope.envelope_id,
                include="recipients,custom_fields"
            )
            
            # Convert to dict format compatible with upsert_envelope
            envelope_data = {
                "envelopeId": detailed_envelope.envelope_id,
                "emailSubject": detailed_envelope.email_subject,
                "status": detailed_envelope.status,
                "createdDateTime": detailed_envelope.created_date_time,
                "sentDateTime": detailed_envelope.sent_date_time,
                "deliveredDateTime": detailed_envelope.delivered_date_time,
                "completedDateTime": detailed_envelope.completed_date_time,
                "sender": {"email": getattr(detailed_envelope.sender, 'email', None)},
                "customFields": {
                    "textCustomFields": [
                        {"name": cf.name, "value": cf.value}
                        for cf in (detailed_envelope.custom_fields.text_custom_fields or [])
                    ] if detailed_envelope.custom_fields else []
                },
                "recipients": {
                    "signers": [
                        {
                            "email": r.email,
                            "name": r.name,
                            "status": r.status,
                            "routingOrder": str(r.routing_order),
                            "roleName": r.role_name
                        }
                        for r in (detailed_envelope.recipients.signers or [])
                    ] if detailed_envelope.recipients else []
                }
            }
            envelope_list.append(envelope_data)
        
        return envelope_list
    
    except ApiException as e:
        raise RuntimeError(f"fetch_envelopes failed: {e}") from e

def get_docusign_client():
    """Initialize DocuSign client from environment variables."""
    client_id = os.getenv("INTEGRATION_KEY")
    user_id = os.getenv("USER_ID") 
    rsa_key = os.getenv("RSA_KEY")
    demo = os.getenv("DOCUSIGN_DEMO", "true").lower() == "true"
    
    if not all([client_id, user_id, rsa_key]):
        raise RuntimeError("Missing DocuSign credentials in environment")
    
    return docusign_jwt_login(client_id, user_id, rsa_key, demo=demo)