# map.py
from sqlalchemy.orm import Session
from models import Envelope, Recipient
from datetime import datetime

def iso2dt(s):
    return datetime.fromisoformat(s.replace("Z","+00:00")) if s else None

def upsert_envelope(session: Session, item: dict):
    env_id = item["envelopeId"]
    env = session.get(Envelope, env_id) or Envelope(id=env_id)
    env.subject = item.get("emailSubject")
    env.sender_email = (item.get("sender") or {}).get("email")
    env.status = (item.get("status") or "").lower()
    env.created_at = iso2dt(item.get("createdDateTime"))
    env.sent_at = iso2dt(item.get("sentDateTime"))
    env.delivered_at = iso2dt(item.get("deliveredDateTime"))
    env.completed_at = iso2dt(item.get("completedDateTime"))

    # deal_name from customFields (textCustomFields) or from your app's metadata
    deal_name = None
    cf = item.get("customFields") or {}
    for t in (cf.get("textCustomFields") or []):
        field_name = t.get("name","").lower()
        field_value = t.get("value","").strip()
        
        # Check for traditional deal name fields
        if field_name in {"deal","deal_name","dealname"} and field_value:
            deal_name = field_value
            break
        
        # Check for envelopeTypes field as potential deal categorization
        if field_name == "envelopetypes" and field_value:
            deal_name = field_value
            break
            
        # Check for custom field with actual content
        if field_name == "custom field" and field_value:
            deal_name = field_value
            break
    
    # If no custom field deal name found, try to extract from subject line
    if not deal_name:
        subject = item.get("emailSubject", "") or ""
        # Look for common patterns in subjects like "Company Name" followed by specific indicators
        import re
        
        # Pattern to extract deal names from subjects like "Angiex Subscription", "Angiex Consent", etc.
        patterns = [
            r'(Angiex)',  # Direct company name match
            r'Complete with Docusign:\s*([^-:]+?)(?:\s*-|\s*:)',  # Extract from "Complete with Docusign: Company Name -"
            r':\s*([A-Z][a-zA-Z\s]+?)(?:\s*-|\s*Subscription|\s*Consent|\s*Form)',  # Extract company from various formats
        ]
        
        for pattern in patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                potential_deal = match.group(1).strip()
                if len(potential_deal) > 2 and not potential_deal.lower() in {'complete', 'docusign', 'with'}:
                    deal_name = potential_deal
                    break
    
    env.deal_name = deal_name

    # recipients
    recs = (item.get("recipients") or {}).get("signers") or []
    env.recipients.clear()
    for r in recs:
        env.recipients.append(Recipient(
            name=r.get("name"),
            email=r.get("email"),
            role=r.get("roleName"),
            routing_order=int(r.get("routingOrder") or 9999),
            recipient_status=(r.get("status") or "").lower(),
            raw=r
        ))

    env.app_status = derive_app_status(env.status, recs)
    env.updated_at = datetime.utcnow()
    session.merge(env)

def derive_app_status(env_status: str, recipients: list) -> str:
    """Derive application-specific status from DocuSign envelope status and recipients."""
    if env_status == "voided":
        return "Cancelled"
    elif env_status == "declined":
        return "Declined"
    elif env_status == "completed":
        return "Completed"
    elif env_status in ("sent", "delivered"):
        # Check if any recipients have signed
        signed_count = sum(1 for r in recipients if r.get("status", "").lower() == "completed")
        total_signers = len(recipients)
        if signed_count == 0:
            return "Awaiting Customer"
        elif signed_count < total_signers:
            return "Partially Signed"
        else:
            return "Awaiting Processing"
    else:
        return "Draft"
