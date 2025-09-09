# Consent URL for first-time setup:
# https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=574290d2-a290-4487-adeb-7e3fea38b8bc&redirect_uri=https://www.paulsoncrm.com

# requirements: pyjwt, requests, docusign-esign, python-dotenv
import os, base64
from datetime import datetime, timedelta
import dotenv

from docusign_esign import ApiClient
from docusign_esign.apis import EnvelopesApi
from docusign_esign.client.api_exception import ApiException
from docusign_esign.models import (
    EnvelopeDefinition,
    Document,
    Signer,
    SignHere,
    Tabs,
    Recipients,
)

def _load_private_key_bytes(value: str) -> bytes:
    """
    Accept either:
      - raw PEM content in the env var (contains 'BEGIN ... PRIVATE KEY')
      - a filesystem path to the PEM file
    Return key bytes suitable for request_jwt_user_token.
    """
    if not value:
        raise RuntimeError("RSA key not provided (env RSA_KEY).")
    if "BEGIN" in value and "PRIVATE KEY" in value:
        return value.encode("utf-8")
    # otherwise, treat as a path
    if not os.path.exists(value):
        raise RuntimeError(f"RSA_KEY path not found: {value}")
    with open(value, "rb") as f:
        return f.read()

def docusign_jwt_login(
    client_id: str,
    impersonated_user_id: str,
    private_key: str,                   # PEM string OR path (we handle both)
    demo: bool = True,
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

    private_key_bytes = _load_private_key_bytes(private_key)

    # 1) Request OAuth access token via JWT (no browser once consent is given)
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
        # Common causes: consent_required, wrong key, wrong host
        raise RuntimeError(f"JWT token request failed: {e}") from e

    access_token = token.access_token

    # 2) Discover default account & base_uri, set api_client.host
    user_info = api_client.get_user_info(access_token)
    default_acct = next(a for a in user_info.accounts if a.is_default)
    account_id = default_acct.account_id
    api_client.host = default_acct.base_uri + "/restapi"

    # 3) Attach bearer token for SDK calls
    api_client.set_default_header("Authorization", f"Bearer {access_token}")

    return api_client, account_id, access_token

def make_demo_envelope_definition(signer_email: str, signer_name: str) -> EnvelopeDefinition:
    """
    Creates a minimal HTML document with an anchor tag **SIGN_HERE**,
    and places a SignHere tab at that anchor for the signer.
    The envelope is set to send immediately (status='sent').
    """
    # Minimal HTML content with an anchor for the signature tab
    html = f"""
    <!DOCTYPE html>
    <html>
        <head><meta charset="UTF-8"><title>Demo Doc</title></head>
        <body style="font-family: Helvetica, Arial, sans-serif;">
            <h2>Hello {signer_name},</h2>
            <p>This is a test envelope sent from the DocuSign Demo environment.</p>
            <p>Please sign at the anchor below:</p>
            <p>**SIGN_HERE**</p>
        </body>
    </html>
    """.strip()

    doc_base64 = base64.b64encode(html.encode("utf-8")).decode("ascii")

    # Create DocuSign Document object
    document = Document(
        document_base64=doc_base64,
        name="Demo HTML Document",
        file_extension="html",
        document_id="1",
    )

    # Create the Signer (recipientId must be a string)
    signer = Signer(
        email=signer_email,
        name=signer_name,
        recipient_id="1",
        routing_order="1",
    )

    # Place a SignHere tab using anchor string
    sign_here = SignHere(
        anchor_string="**SIGN_HERE**",
        anchor_units="pixels",
        anchor_x_offset="0",
        anchor_y_offset="0",
    )

    signer.tabs = Tabs(sign_here_tabs=[sign_here])

    # Add recipients to the envelope
    recipients = Recipients(signers=[signer])

    # Create the envelope definition and set to 'sent' to send immediately
    envelope_definition = EnvelopeDefinition(
        email_subject="Demo Envelope: Please sign",
        documents=[document],
        recipients=recipients,
        status="sent",
    )
    return envelope_definition

def create_and_send_envelope(api_client: ApiClient, account_id: str, signer_email: str, signer_name: str) -> str:
    """
    Creates and sends a demo envelope; returns the envelope_id.
    """
    envelopes_api = EnvelopesApi(api_client)
    env_def = make_demo_envelope_definition(signer_email, signer_name)
    try:
        results = envelopes_api.create_envelope(account_id=account_id, envelope_definition=env_def)
        envelope_id = results.envelope_id
        print(f"Envelope sent! envelope_id={envelope_id}")
        return envelope_id
    except ApiException as e:
        raise RuntimeError(f"create_envelope failed: {e}") from e

def fetch_envelope_status(api_client: ApiClient, account_id: str, envelope_id: str) -> None:
    """
    Reads the envelope back and prints its status & timestamps.
    """
    envelopes_api = EnvelopesApi(api_client)
    try:
        env = envelopes_api.get_envelope(account_id=account_id, envelope_id=envelope_id)
        print("Envelope Status Readback")
        print(f"  envelope_id: {env.envelope_id}")
        print(f"  status     : {env.status}")
        print(f"  created    : {env.created_date_time}")
        print(f"  sent       : {env.sent_date_time}")
        print(f"  completed  : {env.completed_date_time}")
    except ApiException as e:
        raise RuntimeError(f"get_envelope failed: {e}") from e

def list_recent_envelopes(api_client: ApiClient, account_id: str, days_back: int = 30) -> None:
    """
    Lists envelopes changed since from_date.
    """
    envelopes_api = EnvelopesApi(api_client)
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        results = envelopes_api.list_status_changes(account_id, from_date=from_date)
        count = len(results.envelopes or [])
        print(f"Found {count} envelope(s) changed since {from_date}")
        for e in (results.envelopes or []):
            print(f"- {e.envelope_id} | {e.status} | {e.email_subject} | created {e.created_date_time}")
    except ApiException as e:
        raise RuntimeError(f"list_status_changes failed: {e}") from e

if __name__ == "__main__":
    dotenv.load_dotenv()

    CLIENT_ID = os.getenv("INTEGRATION_KEY")
    USER_ID = os.getenv("USER_ID")
    RSA_KEY = os.getenv("RSA_KEY")          # PEM content OR a file path
    DEMO = True

    SIGNER_EMAIL = os.getenv("SIGNER_EMAIL") or os.getenv("USER_EMAIL")
    SIGNER_NAME  = os.getenv("SIGNER_NAME")  or "Demo Signer"

    if not CLIENT_ID or not USER_ID or not RSA_KEY:
        raise SystemExit("Please set INTEGRATION_KEY, USER_ID, and RSA_KEY env vars.")

    if not SIGNER_EMAIL:
        raise SystemExit("Please set SIGNER_EMAIL (or USER_EMAIL) and SIGNER_NAME env vars for the signer.")

    # 1) Login via JWT, set host/base_uri automatically
    api_client, account_id, access_token = docusign_jwt_login(
        client_id=CLIENT_ID,
        impersonated_user_id=USER_ID,
        private_key=RSA_KEY,
        demo=DEMO,
    )
    print(f"Logged in. account_id={account_id}")

    # 2) Create & send a tiny demo envelope
    envelope_id = create_and_send_envelope(api_client, account_id, SIGNER_EMAIL, SIGNER_NAME)

    # 3) Read it back
    fetch_envelope_status(api_client, account_id, envelope_id)

    # 4) Also show it in the “recent envelopes” list
    list_recent_envelopes(api_client, account_id, days_back=7)
