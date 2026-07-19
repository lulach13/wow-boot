import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    discord_id = Column(String, unique=True, nullable=False)
    discord_username = Column(String, nullable=False)
    character_name = Column(String, nullable=False)
    realm = Column(String, nullable=False)
    wow_class = Column(String)
    spec = Column(String)
    role = Column(String)           # tank / healer / dps
    content_focus = Column(String)  # mythic+ / raiding / pvp
    armory_ilvl = Column(Integer)
    faction = Column(String)
    registered_at = Column(DateTime, default=datetime.utcnow)

    notifications = relationship("Notification", back_populates="user")


class PatchNote(Base):
    __tablename__ = "patch_notes"

    id = Column(Integer, primary_key=True)
    version = Column(String, nullable=False)
    title = Column(String)
    url = Column(String)
    posted_at = Column(DateTime)
    raw_content = Column(Text)
    wowhead_content = Column(Text)
    icy_veins_content = Column(Text)
    processed = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow)

    notifications = relationship("Notification", back_populates="patch_note")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    patch_note_id = Column(Integer, ForeignKey("patch_notes.id"), nullable=False)
    summary_text = Column(Text)
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime)

    user = relationship("User", back_populates="notifications")
    patch_note = relationship("PatchNote", back_populates="notifications")
