# app.py
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker
from models import Base, Envelope
from map import upsert_envelope
from docusign_client import get_docusign_client, fetch_envelopes
import json
import hmac
import hashlib
import os

app = Flask(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Database configuration
database_url = os.getenv("DATABASE_URL", "mysql+pymysql://user:pass@localhost/docusign_db?charset=utf8mb4")
engine = create_engine(database_url, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

@app.get("/envelopes")
def list_envelopes():
    status = request.args.get("status")         # raw DocuSign status OR your app_status
    app_status = request.args.get("app_status")
    deal = request.args.get("deal")
    q = select(Envelope)
    clauses = []
    if status: clauses.append(Envelope.status == status.lower())
    if app_status: clauses.append(Envelope.app_status == app_status)
    if deal: clauses.append(Envelope.deal_name == deal)
    if clauses: q = q.where(and_(*clauses))
    with Session() as s:
        rows = s.execute(q.order_by(Envelope.updated_at.desc()).limit(200)).scalars().all()
        return jsonify([{
            "envelopeId": e.id,
            "subject": e.subject,
            "deal_name": e.deal_name,
            "status": e.status,
            "app_status": e.app_status,
            "sender_email": e.sender_email,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
        } for e in rows])

@app.get("/envelopes/<envelope_id>")
def get_envelope(envelope_id):
    """Get detailed information about a specific envelope."""
    with Session() as session:
        envelope = session.get(Envelope, envelope_id)
        if not envelope:
            return jsonify({"error": "Envelope not found"}), 404
        
        return jsonify({
            "envelopeId": envelope.id,
            "subject": envelope.subject,
            "deal_name": envelope.deal_name,
            "status": envelope.status,
            "app_status": envelope.app_status,
            "sender_email": envelope.sender_email,
            "created_at": envelope.created_at.isoformat() if envelope.created_at else None,
            "sent_at": envelope.sent_at.isoformat() if envelope.sent_at else None,
            "delivered_at": envelope.delivered_at.isoformat() if envelope.delivered_at else None,
            "completed_at": envelope.completed_at.isoformat() if envelope.completed_at else None,
            "updated_at": envelope.updated_at.isoformat() if envelope.updated_at else None,
            "recipients": [{
                "name": r.name,
                "email": r.email,
                "role": r.role,
                "routing_order": r.routing_order,
                "status": r.recipient_status,
            } for r in envelope.recipients]
        })

@app.get("/envelopes/stats")
def envelope_stats():
    """Get envelope statistics."""
    with Session() as session:
        from sqlalchemy import func
        
        # Count by status
        status_counts = session.execute(
            select(Envelope.status, func.count().label('count'))
            .group_by(Envelope.status)
        ).all()
        
        # Count by app_status
        app_status_counts = session.execute(
            select(Envelope.app_status, func.count().label('count'))
            .group_by(Envelope.app_status)
        ).all()
        
        # Total count
        total = session.execute(select(func.count(Envelope.id))).scalar()
        
        return jsonify({
            "total_envelopes": total,
            "by_status": {row.status: row.count for row in status_counts},
            "by_app_status": {row.app_status: row.count for row in app_status_counts}
        })

@app.post("/docusign/webhook")
def docusign_webhook():
    """Handle DocuSign Connect webhook notifications."""
    # Verify the webhook signature if HMAC key is configured
    hmac_key = os.getenv("DOCUSIGN_WEBHOOK_HMAC_KEY")
    if hmac_key:
        signature = request.headers.get("X-DocuSign-Signature-1")
        if not signature or not verify_webhook_signature(request.data, signature, hmac_key):
            return jsonify({"error": "Invalid signature"}), 401
    
    try:
        # Parse the XML payload from DocuSign Connect
        envelope_data = parse_docusign_xml(request.data)
        
        # Store/update the envelope in the database
        with Session() as session:
            upsert_envelope(session, envelope_data)
            session.commit()
        
        return jsonify({"status": "success"}), 200
    
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"error": "Processing failed"}), 500

def verify_webhook_signature(payload: bytes, signature: str, key: str) -> bool:
    """Verify DocuSign webhook HMAC signature."""
    expected = hmac.new(
        key.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

def parse_docusign_xml(xml_data: bytes) -> dict:
    """Parse DocuSign Connect XML payload into envelope data dict."""
    import xml.etree.ElementTree as ET
    
    root = ET.fromstring(xml_data)
    
    # Extract envelope data from XML
    envelope_status = root.find('.//EnvelopeStatus')
    if envelope_status is None:
        raise ValueError("No EnvelopeStatus found in XML")
    
    envelope_data = {
        "envelopeId": envelope_status.findtext('EnvelopeID'),
        "emailSubject": envelope_status.findtext('Subject'),
        "status": envelope_status.findtext('Status'),
        "createdDateTime": envelope_status.findtext('Created'),
        "sentDateTime": envelope_status.findtext('Sent'),
        "deliveredDateTime": envelope_status.findtext('Delivered'),
        "completedDateTime": envelope_status.findtext('Completed'),
    }
    
    # Extract sender info
    sender_elem = envelope_status.find('Sender')
    if sender_elem is not None:
        envelope_data["sender"] = {
            "email": sender_elem.findtext('Email')
        }
    
    # Extract custom fields
    custom_fields = envelope_status.find('CustomFields')
    if custom_fields is not None:
        text_custom_fields = []
        for field in custom_fields.findall('CustomField'):
            text_custom_fields.append({
                "name": field.findtext('Name'),
                "value": field.findtext('Value')
            })
        envelope_data["customFields"] = {"textCustomFields": text_custom_fields}
    
    # Extract recipients
    recipients_elem = envelope_status.find('Recipients')
    if recipients_elem is not None:
        signers = []
        for recipient in recipients_elem.findall('Recipient'):
            signers.append({
                "email": recipient.findtext('Email'),
                "name": recipient.findtext('UserName'),
                "status": recipient.findtext('Status'),
                "routingOrder": recipient.findtext('RoutingOrder'),
                "roleName": recipient.findtext('RoleName')
            })
        envelope_data["recipients"] = {"signers": signers}
    
    return envelope_data

@app.post("/sync/envelopes")
def sync_envelopes():
    """Pull envelopes from DocuSign API and store them in the database."""
    days_back = request.json.get("days_back", 30) if request.is_json else 30
    
    try:
        # Get DocuSign client
        api_client, account_id, _ = get_docusign_client()
        
        # Fetch envelopes from DocuSign
        envelopes = fetch_envelopes(api_client, account_id, days_back)
        
        # Store envelopes in database
        with Session() as session:
            for envelope_data in envelopes:
                upsert_envelope(session, envelope_data)
            session.commit()
        
        return jsonify({
            "status": "success",
            "synced_count": len(envelopes),
            "message": f"Synced {len(envelopes)} envelopes from the last {days_back} days"
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
