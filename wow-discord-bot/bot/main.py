import logging
import discord
from discord.ext import commands

from config import settings
from db.database import init_db
from services.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Show full LLM prompts and responses
logging.getLogger("services.llm").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

COGS = [
    "bot.cogs.registration",
    "bot.cogs.notifications",
    "bot.cogs.knowledge_base",
]


class WoWBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        for cog in COGS:
            await self.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        guild = discord.Object(id=settings.discord_guild_id)
        # Clear any stale guild-only commands first, then resync
        self.tree.clear_commands(guild=guild)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} slash command(s) to guild {settings.discord_guild_id}.")
        for cmd in synced:
            logger.info(f"  /{cmd.name}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        init_db()
        start_scheduler(self)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="WoW Midnight patch notes",
            )
        )


def main():
    bot = WoWBot()
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
