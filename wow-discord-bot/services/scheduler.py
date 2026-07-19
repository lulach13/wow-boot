import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db.database import get_session
from db.models import PatchNote
from services import blizzard_api
from services.scrapers import wowhead, icy_veins
from services import llm

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Will be set by bot/main.py after the Discord client is ready
_discord_bot = None


def set_discord_bot(bot):
    global _discord_bot
    _discord_bot = bot


async def force_notify_latest():
    """Force re-notify for the most recent patch note already in DB."""
    with get_session() as session:
        patch = session.query(PatchNote).order_by(PatchNote.posted_at.desc()).first()
        if not patch:
            logger.warning("No patch notes in DB to force-notify.")
            return
        patch_id = patch.id
        raw_content = patch.raw_content or ""
        wowhead_content = patch.wowhead_content or ""

    logger.info(f"Force-notifying for patch: {patch_id}")
    await _notify_users(patch_id, raw_content, wowhead_content)


async def check_for_patch_notes():
    """
    Poll Blizzard for new patch notes. If new ones are found, scrape
    community sites, run LLM analysis, and trigger Discord notifications.
    """
    logger.info("Checking for new patch notes...")

    try:
        entries = await blizzard_api.get_latest_patch_notes(count=3)
    except Exception as e:
        logger.error(f"Failed to fetch patch notes: {e}")
        return

    for entry in entries:
        with get_session() as session:
            existing = session.query(PatchNote).filter_by(url=entry.url).first()
            if existing:
                continue  # Already processed

            logger.info(f"New patch note detected: {entry.title}")

            # Fetch full content
            try:
                raw_content = await blizzard_api.fetch_patch_note_content(entry.url)
            except Exception as e:
                logger.error(f"Failed to fetch patch content: {e}")
                raw_content = entry.title

            # Scrape community sites
            try:
                wowhead_content = await wowhead.fetch_patch_coverage(entry.title, entry.url)
            except Exception as e:
                logger.warning(f"Wowhead scrape failed: {e}")
                wowhead_content = ""

            # Store patch note
            patch = PatchNote(
                version=entry.title,
                title=entry.title,
                url=entry.url,
                posted_at=datetime.utcnow(),
                raw_content=raw_content,
                wowhead_content=wowhead_content,
                processed=False,
            )
            session.add(patch)
            session.flush()
            patch_id = patch.id

        # Notify users (outside the session to avoid long-held transactions)
        if _discord_bot:
            await _notify_users(patch_id, raw_content, wowhead_content)


async def _notify_users(patch_id: int, raw_content: str, wowhead_content: str):
    from db.models import User, Notification
    from discord import Embed, Color

    with get_session() as session:
        users = session.query(User).all()
        user_snapshots = [
            {
                "id": u.id,
                "discord_id": u.discord_id,
                "wow_class": u.wow_class,
                "spec": u.spec,
                "role": u.role,
                "content_focus": u.content_focus,
            }
            for u in users
        ]
        patch = session.query(PatchNote).get(patch_id)
        patch_title = patch.title if patch else "New Patch"
        patch_url = patch.url if patch else ""

    for user_data in user_snapshots:
        # Fetch Icy Veins updates for this specific spec/class
        try:
            iv_content = await icy_veins.fetch_class_updates(
                user_data["spec"], user_data["wow_class"]
            )
        except Exception:
            iv_content = ""

        # Run LLM analysis
        try:
            summary = await llm.analyze_patch_notes(
                patch_text=raw_content,
                wowhead_text=wowhead_content,
                icy_veins_text=iv_content,
                wow_class=user_data["wow_class"] or "Unknown",
                spec=user_data["spec"] or "Unknown",
                role=user_data["role"] or "dps",
                content_focus=user_data["content_focus"] or "general",
            )
        except Exception as e:
            logger.error(f"LLM analysis failed for user {user_data['discord_id']}: {e}")
            summary = "Could not generate analysis. Please check the patch notes manually."

        # Send DM to user
        try:
            discord_user = await _discord_bot.fetch_user(int(user_data["discord_id"]))
            embed = Embed(
                title=f"🗞️ WoW Patch Update: {patch_title}",
                url=patch_url,
                color=Color.blue(),
            )
            embed.add_field(
                name=f"{user_data['spec']} {user_data['wow_class']} Analysis",
                value=summary[:1024],
                inline=False,
            )
            embed.set_footer(text="Sources: Blizzard • Wowhead • Icy Veins")
            await discord_user.send(
                content=f"Hey! New patch notes dropped — here's what changed for your **{user_data['spec']} {user_data['wow_class']}**:",
                embed=embed,
            )
        except Exception as e:
            logger.error(f"Failed to DM user {user_data['discord_id']}: {e}")
            continue

        # Record notification
        with get_session() as session:
            notif = Notification(
                user_id=user_data["id"],
                patch_note_id=patch_id,
                summary_text=summary,
                sent=True,
                sent_at=datetime.utcnow(),
            )
            session.add(notif)


def start_scheduler(bot):
    set_discord_bot(bot)
    scheduler.add_job(
        check_for_patch_notes,
        "interval",
        minutes=settings.patch_check_interval_minutes,
        id="patch_check",
        replace_existing=True,
    )

    from services.knowledge_base.scheduler import schedule_kb_ingestion
    schedule_kb_ingestion(scheduler)

    scheduler.start()
    logger.info(
        f"Scheduler started. Checking every {settings.patch_check_interval_minutes} minutes."
    )
