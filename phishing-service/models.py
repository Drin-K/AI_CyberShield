# models.py
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, func
from db import Base

class DNSAlert(Base):
    __tablename__ = "dns_alerts"
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, index=True, nullable=False, unique=True)
    score = Column(Float, default=0.0)
    reasons = Column(Text)
    features = Column(Text)
    client_id = Column(String)
    observed_at = Column(DateTime)
    inserted_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime)
    raw = Column(Text)
    report_count = Column(Integer, default=1)
