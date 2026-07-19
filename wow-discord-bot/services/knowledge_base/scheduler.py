import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


async def _run_daily_ingestion():
    from services.knowledge_base.ingestion import ingest_all_registered_specs

    logger.info("Daily knowledge base ingestion starting...")
    try:
        result = await ingest_all_registered_specs()
        logger.info(
            f"Daily ingestion complete: {result['chunks']} chunks across {result['specs']} spec(s)."
        )
    except Exception as e:
        logger.error(f"Daily knowledge base ingestion failed: {e}")


def schedule_kb_ingestion(scheduler: AsyncIOScheduler):
    scheduler.add_job(
        _run_daily_ingestion,
        "cron",
        hour=3,
        minute=0,
        id="kb_daily_ingestion",
        replace_existing=True,
    )
    logger.info("Knowledge base ingestion scheduled at 03:00 daily.")
