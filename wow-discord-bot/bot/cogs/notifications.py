import discord
from discord import app_commands
from discord.ext import commands

from db.database import get_session
from db.models import Notification, PatchNote

# WoW class colors (hex → discord.Color)
CLASS_COLORS = {
    "Death Knight":  discord.Color(0xC41E3A),
    "Demon Hunter":  discord.Color(0xA330C9),
    "Druid":         discord.Color(0xFF7C0A),
    "Evoker":        discord.Color(0x33937F),
    "Hunter":        discord.Color(0xAAD372),
    "Mage":          discord.Color(0x3FC7EB),
    "Monk":          discord.Color(0x00FF98),
    "Paladin":       discord.Color(0xF48CBA),
    "Priest":        discord.Color(0xC5C5C5),
    "Rogue":         discord.Color(0xFFF468),
    "Shaman":        discord.Color(0x0070DD),
    "Warlock":       discord.Color(0x8788EE),
    "Warrior":       discord.Color(0xC69B3A),
}

# Spec emoji icons
SPEC_ICONS = {
    # Death Knight
    "Blood": "🩸", "Frost": "❄️", "Unholy": "💀",
    # Demon Hunter
    "Havoc": "🔥", "Vengeance": "🛡️",
    # Druid
    "Balance": "🌙", "Feral": "🐆", "Guardian": "🐻", "Restoration": "🍃",
    # Evoker
    "Augmentation": "✨", "Devastation": "🐲", "Preservation": "💚",
    # Hunter
    "Beast Mastery": "🐾", "Marksmanship": "🏹", "Survival": "🗡️",
    # Mage
    "Arcane": "🔮", "Fire": "🔥",
    # Monk
    "Brewmaster": "🍺", "Mistweaver": "🌿", "Windwalker": "💨",
    # Paladin
    "Holy": "✨", "Protection": "🛡️", "Retribution": "⚡",
    # Priest
    "Discipline": "🕊️", "Shadow": "🌑",
    # Rogue
    "Assassination": "🗡️", "Outlaw": "🏴‍☠️", "Subtlety": "🌑",
    # Shaman
    "Elemental": "⚡", "Enhancement": "🌩️",
    # Warlock
    "Affliction": "🟣", "Demonology": "👿", "Destruction": "🔥",
    # Warrior
    "Arms": "⚔️", "Fury": "🌪️",
}

ROLE_ICONS = {"tank": "🛡️", "healer": "💚", "dps": "⚔️"}

CONTENT_ICONS = {
    "raiding": "🐉", "mythic+": "🔑", "pvp": "⚔️", "casual": "🎮",
}

FACTION_ICONS = {"Alliance": "🔵", "Horde": "🔴"}


def format_content_focus(raw: str) -> str:
    parts = [p.strip() for p in raw.split(",")]
    return "  ".join(CONTENT_ICONS.get(p, "") + " " + p.title() for p in parts if p)


class Notifications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="history",
        description="Show the last 5 patch note alerts you received.",
    )
    async def history(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)

        with get_session() as session:
            from db.models import User
            user = session.query(User).filter_by(discord_id=discord_id).first()
            if not user:
                await interaction.response.send_message(
                    "You are not registered. Use `/register` first.", ephemeral=True
                )
                return

            notifications = (
                session.query(Notification)
                .filter_by(user_id=user.id, sent=True)
                .order_by(Notification.sent_at.desc())
                .limit(5)
                .all()
            )

            if not notifications:
                await interaction.response.send_message(
                    "No patch alerts received yet.", ephemeral=True
                )
                return

            embed = discord.Embed(title="Your Patch Alert History", color=discord.Color.blurple())
            for notif in notifications:
                patch = session.query(PatchNote).get(notif.patch_note_id)
                patch_title = patch.title if patch else "Unknown Patch"
                sent_str = notif.sent_at.strftime("%Y-%m-%d") if notif.sent_at else "Unknown"
                summary_preview = (notif.summary_text or "")[:200] + "..."
                embed.add_field(
                    name=f"{patch_title} ({sent_str})",
                    value=summary_preview,
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="check_patches",
        description="[Admin] Manually trigger a patch note check.",
    )
    @app_commands.default_permissions(administrator=True)
    async def check_patches(self, interaction: discord.Interaction, force: bool = False):
        await interaction.response.defer(thinking=True, ephemeral=True)
        from services import blizzard_api
        from services.scheduler import check_for_patch_notes, force_notify_latest
        from db.database import get_session
        from db.models import PatchNote

        if force:
            await interaction.followup.send(
                "Force-notifying for the latest patch note in DB...", ephemeral=True
            )
            await force_notify_latest()
            return

        try:
            entries = await blizzard_api.get_latest_patch_notes(count=5)
        except Exception as e:
            await interaction.followup.send(f"Scraper error: {e}", ephemeral=True)
            return

        if not entries:
            await interaction.followup.send(
                "Scraper found **0 articles** matching patch/hotfix keywords on Blizzard news page. "
                "The page structure may have changed.",
                ephemeral=True,
            )
            return

        with get_session() as session:
            new_count = 0
            known_count = 0
            lines = []
            for e in entries:
                existing = session.query(PatchNote).filter_by(url=e.url).first()
                if existing:
                    known_count += 1
                    lines.append(f"- [already known] {e.title}")
                else:
                    new_count += 1
                    lines.append(f"- [NEW] {e.title}")

        summary = "\n".join(lines)
        await interaction.followup.send(
            f"Found **{len(entries)}** article(s) ({new_count} new, {known_count} already known):\n{summary}",
            ephemeral=True,
        )

        if new_count > 0:
            await check_for_patch_notes()

    @app_commands.command(
        name="check_updates",
        description="[Admin] Send each registered user a personalized patch update DM.",
    )
    @app_commands.default_permissions(administrator=True)
    async def check_updates(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        from db.models import User
        from services.scheduler import _notify_users
        from db.models import PatchNote

        with get_session() as session:
            users = session.query(User).all()
            user_count = len(users)
            patch = session.query(PatchNote).order_by(PatchNote.posted_at.desc()).first()
            patch_id = patch.id if patch else None
            raw_content = patch.raw_content or "" if patch else ""
            wowhead_content = patch.wowhead_content or "" if patch else ""

        if not user_count:
            await interaction.followup.send("No registered users found.", ephemeral=True)
            return

        if patch_id is None:
            await interaction.followup.send(
                "No patch notes found in DB. Run `/check_patches` first.", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"Sending personalized updates to **{user_count}** user(s) via DM...", ephemeral=True
        )
        await _notify_users(patch_id, raw_content, wowhead_content)

    @app_commands.command(
        name="compare_stats",
        description="[Admin] Compara stat priority de pe Icy Veins vs Wowhead si trimite DM cu discrepante.",
    )
    @app_commands.default_permissions(administrator=True)
    async def compare_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        from db.models import User
        from services.scrapers.icy_veins import fetch_stat_priority as iv_fetch
        from services.scrapers.wowhead import fetch_stat_priority as wh_fetch

        with get_session() as session:
            users = session.query(User).all()
            snapshots = [
                {
                    "discord_id": u.discord_id,
                    "wow_class": u.wow_class or "",
                    "spec": u.spec or "",
                    "role": u.role or "dps",
                }
                for u in users
            ]

        if not snapshots:
            await interaction.followup.send("Niciun user inregistrat.", ephemeral=True)
            return

        sent = 0
        failed = 0

        for u in snapshots:
            spec = u["spec"]
            wow_class = u["wow_class"]
            role = u["role"]

            iv_stats = await iv_fetch(spec, wow_class)
            wh_builds = await wh_fetch(spec, wow_class, role)

            if not iv_stats and not wh_builds:
                failed += 1
                continue

            # Wowhead returneaza mai multe build-uri (hero talents); luam primul
            wh_primary = wh_builds[0] if wh_builds else None
            wh_stats = wh_primary["stats"] if wh_primary else []
            wh_label = wh_primary["label"] if wh_primary else "Wowhead"
            wh_url = wh_primary["url"] if wh_primary else ""

            iv_normalized = [s.lower().strip() for s in iv_stats]
            wh_normalized = [s.lower().strip() for s in wh_stats]

            # --- Analiza discrepante ---
            discrepancies = []

            only_iv = [s for s in iv_stats if s.lower() not in wh_normalized]
            only_wh = [s for s in wh_stats if s.lower() not in iv_normalized]

            if only_iv:
                discrepancies.append(f"Doar pe **Icy Veins**: {', '.join(only_iv)}")
            if only_wh:
                discrepancies.append(f"Doar pe **Wowhead**: {', '.join(only_wh)}")

            # Verifica ordinea pentru statele comune
            common_iv = [s for s in iv_normalized if s in wh_normalized]
            common_wh = [s for s in wh_normalized if s in iv_normalized]
            if common_iv != common_wh:
                order_diff = []
                for i, (a, b) in enumerate(zip(common_iv, common_wh), 1):
                    if a != b:
                        order_diff.append(f"Pozitia {i}: IV=`{a.title()}` vs WH=`{b.title()}`")
                if order_diff:
                    discrepancies.append("Ordine diferita:\n" + "\n".join(order_diff))

            # --- Build embed ---
            spec_icon = SPEC_ICONS.get(spec, "🎮")
            class_color = CLASS_COLORS.get(wow_class, discord.Color(0xF5A623))

            iv_str = "\n".join(f"{i}. {s}" for i, s in enumerate(iv_stats, 1)) if iv_stats else "—"
            wh_str = "\n".join(f"{i}. {s}" for i, s in enumerate(wh_stats, 1)) if wh_stats else "—"

            if discrepancies:
                status_line = "⚠️ **Exista discrepante intre surse!**"
                embed_color = discord.Color.orange()
            else:
                status_line = "✅ Ambele surse sunt de acord."
                embed_color = discord.Color.green()

            embed = discord.Embed(
                title=f"{spec_icon} {spec} {wow_class} — Comparatie Stat Priority",
                description=status_line,
                color=embed_color,
            )
            embed.add_field(
                name="❄️ Icy Veins",
                value=f"```\n{iv_str}\n```",
                inline=True,
            )
            embed.add_field(
                name=f"📘 Wowhead ({wh_label})" if wh_primary else "📘 Wowhead",
                value=f"```\n{wh_str}\n```",
                inline=True,
            )
            if discrepancies:
                embed.add_field(
                    name="⚠️ Discrepante detectate",
                    value="\n".join(discrepancies),
                    inline=False,
                )
                if wh_url:
                    embed.add_field(
                        name="Verifica manual",
                        value=f"[Wowhead Stat Priority]({wh_url})",
                        inline=False,
                    )

            embed.set_footer(text="Surse: Icy Veins + Wowhead • PvE Build")

            try:
                discord_user = await self.bot.fetch_user(int(u["discord_id"]))
                await discord_user.send(
                    content=f"Comparatie stat priority pentru **{spec} {wow_class}**:",
                    embed=embed,
                )
                sent += 1
            except Exception:
                failed += 1

        await interaction.followup.send(
            f"Comparatie trimisa la **{sent}** useri. Erori: {failed}.", ephemeral=True
        )

    @app_commands.command(
        name="send_stat_priority",
        description="[Admin] Trimite fiecarui user prioritatea de stats pentru spec-ul lui via DM.",
    )
    @app_commands.default_permissions(administrator=True)
    async def send_stat_priority(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        from db.models import User
        from services.scrapers.icy_veins import fetch_stat_priority

        with get_session() as session:
            users = session.query(User).all()
            snapshots = [
                {
                    "discord_id": u.discord_id,
                    "wow_class": u.wow_class or "",
                    "spec": u.spec or "",
                    "content_focus": u.content_focus or "",
                }
                for u in users
            ]

        if not snapshots:
            await interaction.followup.send("Niciun user inregistrat.", ephemeral=True)
            return

        sent = 0
        failed = 0
        for u in snapshots:
            spec = u["spec"]
            wow_class = u["wow_class"]

            stats = await fetch_stat_priority(spec, wow_class)
            if not stats:
                failed += 1
                continue

            spec_icon = SPEC_ICONS.get(spec, "🎮")
            class_color = CLASS_COLORS.get(wow_class, discord.Color(0xF5A623))

            numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(stats, 1))

            embed = discord.Embed(
                title=f"{spec_icon} {spec} {wow_class} — Stat Priority",
                description=f"```\n{numbered}\n```",
                color=class_color,
                url=f"https://www.icy-veins.com/wow/{spec.lower().replace(' ', '-')}-{wow_class.lower().replace(' ', '-')}-pve-dps-stat-priority",
            )
            embed.set_footer(text="Sursa: Icy Veins • PvE Build")

            try:
                discord_user = await self.bot.fetch_user(int(u["discord_id"]))
                await discord_user.send(
                    content=f"Salut! Iata prioritatea de stats pentru **{spec} {wow_class}** in PvE:",
                    embed=embed,
                )
                sent += 1
            except Exception as e:
                failed += 1

        await interaction.followup.send(
            f"Trimis la **{sent}** useri. Erori: {failed}.", ephemeral=True
        )

    @app_commands.command(
        name="check_registered",
        description="[Admin] Show all registered users and their characters on the patch channel.",
    )
    @app_commands.default_permissions(administrator=True)
    async def check_registered(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        from db.models import User
        from config import settings

        with get_session() as session:
            users = session.query(User).order_by(User.registered_at).all()
            if not users:
                await interaction.followup.send("No registered users.", ephemeral=True)
                return

            snapshots = [
                {
                    "discord_id": u.discord_id,
                    "discord_username": u.discord_username,
                    "character_name": u.character_name,
                    "realm": u.realm,
                    "wow_class": u.wow_class or "?",
                    "spec": u.spec or "?",
                    "role": u.role or "?",
                    "content_focus": u.content_focus or "?",
                    "armory_ilvl": u.armory_ilvl,
                    "faction": u.faction or "?",
                }
                for u in users
            ]

        channel = self.bot.get_channel(settings.discord_patch_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(settings.discord_patch_channel_id)
            except Exception as e:
                await interaction.followup.send(f"Cannot find patch channel: {e}", ephemeral=True)
                return

        # Header message
        await channel.send(f"## 🗂️  Registered Players — {len(snapshots)} total")

        for i, u in enumerate(snapshots):
            spec = u["spec"]
            wow_class = u["wow_class"]
            spec_icon = SPEC_ICONS.get(spec, "🎮")
            role_icon = ROLE_ICONS.get(u["role"], "❓")
            faction_icon = FACTION_ICONS.get(u["faction"], "⚪")
            ilvl_str = f" • **{u['armory_ilvl']} ilvl**" if u["armory_ilvl"] else ""
            content_str = format_content_focus(u["content_focus"])
            class_color = CLASS_COLORS.get(wow_class, discord.Color(0xF5A623))

            embed = discord.Embed(color=class_color)
            embed.set_author(name=f"{u['discord_username']}", icon_url=None)
            embed.description = f"<@{u['discord_id']}>"

            embed.add_field(
                name="⚔️  Class & Spec",
                value=f"{spec_icon} **{spec} {wow_class}**",
                inline=True,
            )
            embed.add_field(
                name="🏳️  Faction",
                value=f"{faction_icon} {u['faction']}",
                inline=True,
            )
            if u["armory_ilvl"]:
                embed.add_field(
                    name="🎯  Item Level",
                    value=f"**{u['armory_ilvl']}**",
                    inline=True,
                )

            embed.add_field(
                name="🛡️  Role",
                value=f"{role_icon} {u['role'].capitalize()}",
                inline=True,
            )
            embed.add_field(
                name="🎮  Content Focus",
                value=content_str,
                inline=True,
            )
            embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer

            embed.add_field(
                name="🏰  Character",
                value=f"`{u['character_name']}-{u['realm']}`",
                inline=False,
            )

            embed.set_footer(text=f"Player {i + 1} of {len(snapshots)}  •  WoWy Patch Bot")
            await channel.send(embed=embed)

        await interaction.followup.send("Dump trimis pe canal.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
