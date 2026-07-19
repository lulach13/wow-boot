import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class KnowledgeBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="update_knowledge_base",
        description="[Admin] Re-index Icy Veins and Wowhead guides for all registered specs.",
    )
    @app_commands.default_permissions(administrator=True)
    async def update_knowledge_base(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        from services.knowledge_base.ingestion import ingest_all_registered_specs
        from services.knowledge_base.vector_store import get_vector_store

        try:
            result = await ingest_all_registered_specs()
        except Exception as e:
            logger.error(f"/update_knowledge_base failed: {e}")
            await interaction.followup.send(f"Ingestion failed: {e}", ephemeral=True)
            return

        stats = get_vector_store().get_collection_stats()
        await interaction.followup.send(
            f"Indexed **{result['chunks']}** chunks across **{result['specs']}** spec(s). "
            f"Total in DB: **{stats['total_chunks']}** chunks.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(KnowledgeBase(bot))
