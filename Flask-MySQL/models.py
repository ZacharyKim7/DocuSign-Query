# models.py
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Enum, ForeignKey, JSON, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

EnvelopeStatus = Enum("created","sent","delivered","completed","declined","voided","processing",
                      name="envelope_status")

class Envelope(Base):
    __tablename__ = "envelopes"
    id = Column(String(64), primary_key=True)        # DocuSign envelopeId (GUID string)
    subject = Column(String(255))
    sender_email = Column(String(255))
    deal_name = Column(String(255))                  # from a custom field you choose
    status = Column(EnvelopeStatus, index=True)      # raw DocuSign status
    app_status = Column(String(64), index=True)      # your derived status ("Awaiting Customer", etc.)
    created_at = Column(DateTime)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow)

    recipients = relationship("Recipient", back_populates="envelope", cascade="all, delete-orphan")

Index("idx_envelopes_deal_status", Envelope.deal_name, Envelope.app_status)

class Recipient(Base):
    __tablename__ = "recipients"
    id = Column(Integer, primary_key=True, autoincrement=True)
    envelope_id = Column(String(64), ForeignKey("envelopes.id", ondelete="CASCADE"))
    name = Column(String(255))
    email = Column(String(255), index=True)
    role = Column(String(64))
    routing_order = Column(Integer)
    recipient_status = Column(String(64))            # sent, delivered, completed, declined, etc.
    raw = Column(JSON)                               # optional: full recipient JSON

    envelope = relationship("Envelope", back_populates="recipients")
