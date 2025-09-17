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
    
    # Configuration: Map custom field names to their deal name meanings
    # Update these mappings based on your DocuSign template configuration
    DEAL_NAME_FIELD_MAPPINGS = {
        # Traditional deal name fields
        "deal": "direct_value",
        "deal_name": "direct_value", 
        "dealname": "direct_value",
        
        # Custom field that might contain Initial Value for deal name
        "custom field": "direct_value",
        
        # Field that contains deal categorization
        "envelopetypes": "category_value",
        
        # Add more mappings here as you discover them
        # "your_field_name": "direct_value",
    }
    
    for t in (cf.get("textCustomFields") or []):
        field_name = t.get("name","").lower()
        field_value = t.get("value","").strip()
        
        # Check if this field is configured for deal name mapping
        if field_name in DEAL_NAME_FIELD_MAPPINGS and field_value:
            mapping_type = DEAL_NAME_FIELD_MAPPINGS[field_name]
            
            if mapping_type == "direct_value":
                # Use the field value directly as deal name
                deal_name = field_value
                break
            elif mapping_type == "category_value":
                # Use as categorization (like envelopeTypes)
                deal_name = field_value
                break
    
    # If no custom field deal name found, try to extract from subject line
    if not deal_name:
        subject = item.get("emailSubject", "") or ""
        # Look for common patterns in subjects like "Company Name" followed by specific indicators
        import re
        
        # Pattern to extract deal names from subjects
        patterns = [
            # Direct company matches
            r'(Angiex|Vision|Morgan Mutual|AXOS|STRATA)',
            
            # Company names with underscores (like STRATA_Trust)
            r'([A-Z][A-Z_a-z\s]{3,25}?)(?:_(?:Trust|IRA|Distribution))',
            
            # Company names followed by common document types
            r'([A-Z][a-zA-Z\s]{2,20})(?:\s+(?:Subscription|Consent|Investment|Account|Distribution|Agreement|NAF))',
            
            # Extract from "Complete with Docusign: Company Name"
            r'Complete with Docusign:\s*([A-Z][a-zA-Z\s]{2,20}?)(?:\s*(?:Subscription|Consent|Agreement))',
            
            # Extract from "Name: Company Action" format
            r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:\s*([A-Z][a-zA-Z\s]{2,20}?)(?:\s*(?:Subscription|Consent|Account|Distribution|Investment|Form|Agreement))',
            
            # Extract from "FINAL APPROVAL: Company / Name" format  
            r'FINAL APPROVAL:\s*([A-Z][a-zA-Z\s]{2,20}?)(?:\s*/)',
            
            # Extract from "Please DocuSign: Company Name"
            r'Please DocuSign:\s*([A-Z][a-zA-Z\s]{2,20}?)(?:\s*(?:Account|Form))',
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
