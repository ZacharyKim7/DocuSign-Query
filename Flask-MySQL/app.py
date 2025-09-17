# app.py
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL
from models import Base, Envelope, SyncLog
from map import upsert_envelope
from docusign_client import get_docusign_client, fetch_envelopes, fetch_envelopes_since
from docusign_esign.apis import EnvelopesApi
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# config.py or wherever you build the URL
# Database configuration
database_url = os.getenv("DATABASE_URL", "mysql+pymysql://user:pass@localhost/docusign_db?charset=utf8mb4")
engine = create_engine(database_url, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

@app.route('/')
def index():
    return render_template('index.html')

@app.get("/envelopes")
def list_envelopes():
    status = request.args.get("status")         # raw DocuSign status OR your app_status
    app_status = request.args.get("app_status")
    deal = request.args.get("deal")
    search = request.args.get("search")         # New: full-text search across deal_name and subject
    date_field = request.args.get("date_field")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    
    q = select(Envelope)
    clauses = []
    
    if status: clauses.append(Envelope.status == status.lower())
    if app_status: clauses.append(Envelope.app_status == app_status)
    if deal: clauses.append(Envelope.deal_name == deal)
    if search:
        # Search across both deal_name and subject for maximum flexibility
        from sqlalchemy import or_, func
        search_term = f"%{search}%"
        clauses.append(or_(
            Envelope.deal_name.ilike(search_term),
            Envelope.subject.ilike(search_term),
            Envelope.sender_email.ilike(search_term)
        ))
    
    # Date filtering
    if date_field and (start_date or end_date):
        # Get the appropriate date column
        date_column = getattr(Envelope, date_field, None)
        if date_column is not None:
            if start_date:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                clauses.append(date_column >= start_datetime)
            if end_date:
                # End date should include the entire day, so add 1 day and use <
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
                clauses.append(date_column < end_datetime)
    
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
            "recipients": [{
                "name": r.name,
                "email": r.email,
                "role": r.role,
                "routing_order": r.routing_order,
                "status": r.recipient_status,
            } for r in e.recipients] if e.recipients else []
        } for e in rows])

@app.get("/envelopes/custom-fields")
def inspect_custom_fields():
    """Inspect custom field names from recent envelopes to help identify deal name field."""
    try:
        # Get DocuSign client
        api_client, account_id, _ = get_docusign_client()
        
        with Session() as session:
            # Get a sample of recent envelopes (last 10) to inspect custom fields
            recent_envelopes = session.execute(
                select(Envelope)
                .order_by(Envelope.updated_at.desc())
                .limit(10)
            ).scalars().all()
            
            if not recent_envelopes:
                return jsonify({"message": "No envelopes found to inspect"})
            
            custom_fields_found = {}
            envelope_samples = []
            
            # Fetch detailed envelope data from DocuSign API to see custom fields
            envelopes_api = EnvelopesApi(api_client)
            
            for envelope in recent_envelopes[:5]:  # Just check first 5 to avoid rate limits
                try:
                    detailed_envelope = envelopes_api.get_envelope(
                        account_id=account_id,
                        envelope_id=envelope.id,
                        include="custom_fields"
                    )
                    
                    envelope_info = {
                        "envelope_id": envelope.id,
                        "subject": envelope.subject,
                        "current_deal_name": envelope.deal_name,
                        "custom_fields": []
                    }
                    
                    if detailed_envelope.custom_fields and detailed_envelope.custom_fields.text_custom_fields:
                        for cf in detailed_envelope.custom_fields.text_custom_fields:
                            field_name = cf.name
                            field_value = cf.value
                            
                            envelope_info["custom_fields"].append({
                                "name": field_name,
                                "value": field_value
                            })
                            
                            # Track all unique custom field names we've seen
                            if field_name not in custom_fields_found:
                                custom_fields_found[field_name] = []
                            custom_fields_found[field_name].append({
                                "envelope_id": envelope.id,
                                "value": field_value
                            })
                    
                    envelope_samples.append(envelope_info)
                    
                except Exception as e:
                    envelope_samples.append({
                        "envelope_id": envelope.id,
                        "error": f"Could not fetch custom fields: {str(e)}"
                    })
            
            return jsonify({
                "summary": {
                    "total_unique_custom_fields": len(custom_fields_found),
                    "custom_field_names": list(custom_fields_found.keys()),
                    "currently_mapping_to_deal_name": ["deal", "deal_name", "dealname"]
                },
                "custom_fields_analysis": custom_fields_found,
                "envelope_samples": envelope_samples
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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


@app.post("/sync/envelopes")
def sync_envelopes():
    """Pull envelopes from DocuSign API and store them in the database."""
    request_data = request.json if request.is_json else {}
    days_back = request_data.get("days_back")
    force_full_sync = request_data.get("force_full_sync", False)
    
    try:
        # Get DocuSign client
        api_client, account_id, _ = get_docusign_client()
        
        with Session() as session:
            # Determine sync date
            if force_full_sync or days_back:
                # Full sync or specific days back
                if days_back:
                    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
                    message_suffix = f"from the last {days_back} days"
                else:
                    from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
                    message_suffix = "from the last 30 days (full sync)"
                envelopes = fetch_envelopes_since(api_client, account_id, from_date)
            else:
                # Incremental sync based on last sync date
                last_sync = session.execute(
                    select(SyncLog)
                    .where(SyncLog.sync_type == "envelope_sync")
                    .where(SyncLog.sync_status == "success")
                    .order_by(SyncLog.last_sync_date.desc())
                    .limit(1)
                ).scalar_one_or_none()
                
                if last_sync:
                    from_date = last_sync.last_sync_date.strftime("%Y-%m-%d")
                    message_suffix = f"since {from_date} (incremental sync)"
                else:
                    # First time sync - get last 30 days
                    from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
                    message_suffix = "from the last 30 days (initial sync)"
                
                envelopes = fetch_envelopes_since(api_client, account_id, from_date)
            
            # Store envelopes in database
            for envelope_data in envelopes:
                upsert_envelope(session, envelope_data)
            
            # Record sync log
            sync_date = datetime.now(timezone.utc)
            sync_log = SyncLog(
                sync_type="envelope_sync",
                last_sync_date=sync_date,
                envelopes_synced=len(envelopes),
                sync_status="success"
            )
            session.add(sync_log)
            session.commit()
        
        return jsonify({
            "status": "success",
            "synced_count": len(envelopes),
            "message": f"Synced {len(envelopes)} envelopes {message_suffix}",
            "sync_date": sync_date.isoformat()
        }), 200
    
    except Exception as e:
        # Record failed sync
        try:
            with Session() as session:
                sync_log = SyncLog(
                    sync_type="envelope_sync",
                    last_sync_date=datetime.now(timezone.utc),
                    envelopes_synced=0,
                    sync_status="error",
                    error_message=str(e)[:500]
                )
                session.add(sync_log)
                session.commit()
        except:
            pass  # Don't fail the response if we can't log the error
        
        return jsonify({"error": str(e)}), 500

@app.post("/envelopes/deals/refresh-deal-names")
def refresh_deal_names():
    """Re-sync existing envelopes to refresh deal name extraction with new logic."""
    try:
        # Get DocuSign client
        api_client, account_id, _ = get_docusign_client()
        
        with Session() as session:
            # Get recent envelopes that don't have deal names
            envelopes_to_update = session.execute(
                select(Envelope)
                .where(Envelope.deal_name.is_(None))
                .order_by(Envelope.updated_at.desc())
                .limit(20)
            ).scalars().all()
            
            if not envelopes_to_update:
                return jsonify({"message": "No envelopes found without deal names"})
            
            updated_count = 0
            results = []
            
            # Fetch detailed envelope data and re-process with new deal name logic
            envelopes_api = EnvelopesApi(api_client)
            
            for envelope in envelopes_to_update:
                try:
                    detailed_envelope = envelopes_api.get_envelope(
                        account_id=account_id,
                        envelope_id=envelope.id,
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
                    
                    # Use updated mapping logic
                    upsert_envelope(session, envelope_data)
                    
                    # Get the updated envelope to see the new deal name
                    updated_envelope = session.get(Envelope, envelope.id)
                    
                    results.append({
                        "envelope_id": envelope.id,
                        "subject": envelope.subject,
                        "old_deal_name": None,
                        "new_deal_name": updated_envelope.deal_name,
                        "extracted_from": "subject_line" if updated_envelope.deal_name else "none"
                    })
                    
                    if updated_envelope.deal_name:
                        updated_count += 1
                        
                except Exception as e:
                    results.append({
                        "envelope_id": envelope.id,
                        "error": f"Could not update: {str(e)}"
                    })
            
            session.commit()
            
            return jsonify({
                "message": f"Updated {updated_count} envelopes with deal names",
                "results": results
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/sync/status")
def sync_status():
    """Get sync status and history."""
    with Session() as session:
        # Get last sync
        last_sync = session.execute(
            select(SyncLog)
            .where(SyncLog.sync_type == "envelope_sync")
            .order_by(SyncLog.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        # Get recent sync history
        recent_syncs = session.execute(
            select(SyncLog)
            .where(SyncLog.sync_type == "envelope_sync")
            .order_by(SyncLog.created_at.desc())
            .limit(10)
        ).scalars().all()
        
        return jsonify({
            "last_sync": {
                "date": last_sync.last_sync_date.isoformat() if last_sync else None,
                "status": last_sync.sync_status if last_sync else None,
                "envelopes_synced": last_sync.envelopes_synced if last_sync else 0,
                "error_message": last_sync.error_message if last_sync else None
            } if last_sync else None,
            "recent_syncs": [{
                "date": sync.last_sync_date.isoformat(),
                "status": sync.sync_status,
                "envelopes_synced": sync.envelopes_synced,
                "created_at": sync.created_at.isoformat(),
                "error_message": sync.error_message
            } for sync in recent_syncs]
        })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

