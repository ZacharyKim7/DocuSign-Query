# app.py
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL
from models import Base, Envelope, SyncLog
from map import upsert_envelope
from docusign_client import get_docusign_client, fetch_envelopes, fetch_envelopes_since
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

