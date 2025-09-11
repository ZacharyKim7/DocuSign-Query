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

    # deal_name from customFields (textCustomFields) or from your app’s metadata
    deal_name = None
    cf = item.get("customFields") or {}
    for t in (cf.get("textCustomFields") or []):
        if t.get("name","").lower() in {"deal","deal_name","dealname"}:
            deal_name = t.get("value"); break
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
