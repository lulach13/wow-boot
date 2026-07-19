import discord
from discord import app_commands
from discord.ext import commands

from db.database import get_session
from db.models import User

CLASS_SPECS: dict[str, list[str]] = {
    "Death Knight": ["Blood", "Frost", "Unholy"],
    "Demon Hunter": ["Havoc", "Vengeance"],
    "Druid": ["Balance", "Feral", "Guardian", "Restoration"],
    "Evoker": ["Augmentation", "Devastation", "Preservation"],
    "Hunter": ["Beast Mastery", "Marksmanship", "Survival"],
    "Mage": ["Arcane", "Fire", "Frost"],
    "Monk": ["Brewmaster", "Mistweaver", "Windwalker"],
    "Paladin": ["Holy", "Protection", "Retribution"],
    "Priest": ["Discipline", "Holy", "Shadow"],
    "Rogue": ["Assassination", "Outlaw", "Subtlety"],
    "Shaman": ["Elemental", "Enhancement", "Restoration"],
    "Warlock": ["Affliction", "Demonology", "Destruction"],
    "Warrior": ["Arms", "Fury", "Protection"],
}

# Each spec has exactly one role in WoW
SPEC_TO_ROLE: dict[str, str] = {
    # Tanks
    "Blood": "tank", "Vengeance": "tank", "Guardian": "tank",
    "Brewmaster": "tank",
    # Paladin Protection & Warrior Protection
    # Healers
    "Restoration": "healer", "Preservation": "healer",
    "Mistweaver": "healer", "Discipline": "healer",
    # Holy is shared by Paladin and Priest — both healers
    "Holy": "healer",
    # Protection is shared by Paladin and Warrior — both tanks
    "Protection": "tank",
}

def get_role(spec: str) -> str:
    return SPEC_TO_ROLE.get(spec, "dps")


# ── Already Registered View ───────────────────────────────────────────────────

class AlreadyRegisteredView(discord.ui.View):
    def __init__(self, character_name: str, realm: str):
        super().__init__(timeout=60)
        self.character_name = character_name
        self.realm = realm

    @discord.ui.button(label="Update Registration", style=discord.ButtonStyle.primary)
    async def update(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"Updating {self.character_name} — {self.realm}",
            description="Step 1: Select your **Class**",
            color=discord.Color.blurple(),
        )
        self.stop()
        await interaction.response.edit_message(embed=embed, view=Step1View(self.character_name, self.realm))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="Registration unchanged.", embed=None, view=None
        )


# ── Step 2 View: Spec + Content Focus ────────────────────────────────────────

class Step2View(discord.ui.View):
    def __init__(self, character_name: str, realm: str, wow_class: str):
        super().__init__(timeout=120)
        self.character_name = character_name
        self.realm = realm
        self.wow_class = wow_class
        self.selected_spec: str | None = None
        self.selected_content: list[str] = []

        # Spec select
        spec_select = discord.ui.Select(
            placeholder="Select your Spec",
            options=[discord.SelectOption(label=s, value=s) for s in CLASS_SPECS[wow_class]],
            custom_id="spec_select",
            row=0,
        )
        spec_select.callback = self.spec_callback
        self.add_item(spec_select)

        # Content focus multiselect
        content_select = discord.ui.Select(
            placeholder="Select your Content Focus",
            options=[
                discord.SelectOption(label="Raiding", value="raiding", emoji="🐉"),
                discord.SelectOption(label="Mythic+", value="mythic+", emoji="🔑"),
                discord.SelectOption(label="PvP", value="pvp", emoji="⚔️"),
                discord.SelectOption(label="Casual", value="casual", emoji="🎮"),
            ],
            min_values=1,
            max_values=4,
            custom_id="content_select",
            row=1,
        )
        content_select.callback = self.content_callback
        self.add_item(content_select)

        confirm_btn = discord.ui.Button(
            label="Confirm Registration",
            style=discord.ButtonStyle.green,
            custom_id="confirm_btn",
            row=2,
        )
        confirm_btn.callback = self.confirm_callback
        self.add_item(confirm_btn)

    async def spec_callback(self, interaction: discord.Interaction):
        self.selected_spec = interaction.data["values"][0]
        await interaction.response.defer()

    async def content_callback(self, interaction: discord.Interaction):
        self.selected_content = interaction.data["values"]
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_spec:
            await interaction.response.send_message("Please select a Spec first.", ephemeral=True)
            return
        if not self.selected_content:
            await interaction.response.send_message("Please select at least one Content Focus.", ephemeral=True)
            return

        role = get_role(self.selected_spec)
        content_str = ", ".join(self.selected_content)
        discord_id = str(interaction.user.id)

        with get_session() as session:
            existing = session.query(User).filter_by(discord_id=discord_id).first()
            if existing:
                existing.character_name = self.character_name
                existing.realm = self.realm
                existing.wow_class = self.wow_class
                existing.spec = self.selected_spec
                existing.role = role
                existing.content_focus = content_str
                existing.armory_ilvl = None
                existing.faction = None
            else:
                session.add(User(
                    discord_id=discord_id,
                    discord_username=str(interaction.user),
                    character_name=self.character_name,
                    realm=self.realm,
                    wow_class=self.wow_class,
                    spec=self.selected_spec,
                    role=role,
                    content_focus=content_str,
                ))

        embed = discord.Embed(title="✅ Character Registered!", color=discord.Color.green())
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="Character", value=f"{self.character_name} — {self.realm}", inline=True)
        embed.add_field(name="Class / Spec", value=f"{self.selected_spec} {self.wow_class}", inline=True)
        embed.add_field(name="Role", value=role.capitalize(), inline=True)
        embed.add_field(name="Content Focus", value=content_str.title(), inline=True)
        embed.set_footer(text="You will receive personalized patch note alerts in the server channel.")

        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)


# ── Step 1 View: Class select ─────────────────────────────────────────────────

class Step1View(discord.ui.View):
    def __init__(self, character_name: str, realm: str):
        super().__init__(timeout=120)
        self.character_name = character_name
        self.realm = realm

        class_select = discord.ui.Select(
            placeholder="Select your Class",
            options=[discord.SelectOption(label=cls, value=cls) for cls in CLASS_SPECS.keys()],
            custom_id="class_select",
            row=0,
        )
        class_select.callback = self.class_callback
        self.add_item(class_select)

    async def class_callback(self, interaction: discord.Interaction):
        wow_class = interaction.data["values"][0]
        embed = discord.Embed(
            title=f"Registering {self.character_name} — {self.realm}",
            description=f"Class: **{wow_class}**\nNow select your spec and content focus.",
            color=discord.Color.blurple(),
        )
        self.stop()
        await interaction.response.edit_message(embed=embed, view=Step2View(self.character_name, self.realm, wow_class))


# ── Cog ──────────────────────────────────────────────────────────────���───────

class Registration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="register",
        description="Register your WoW character to receive personalized patch note alerts.",
    )
    @app_commands.describe(
        character_name="Your character's name",
        realm="Your realm/server (e.g. Silvermoon, Magtheridon)",
    )
    async def register(self, interaction: discord.Interaction, character_name: str, realm: str):
        discord_id = str(interaction.user.id)

        with get_session() as session:
            existing = session.query(User).filter_by(discord_id=discord_id).first()
            if existing:
                embed = discord.Embed(
                    title="Already Registered",
                    description="You already have a character registered. Do you want to update it?",
                    color=discord.Color.orange(),
                )
                embed.add_field(name="Current Character", value=f"{existing.character_name} — {existing.realm}", inline=True)
                embed.add_field(name="Class / Spec", value=f"{existing.spec} {existing.wow_class}", inline=True)
                embed.add_field(name="Role", value=(existing.role or "—").capitalize(), inline=True)
                embed.add_field(name="Content Focus", value=(existing.content_focus or "—").title(), inline=True)
                await interaction.response.send_message(
                    embed=embed,
                    view=AlreadyRegisteredView(character_name, realm),
                    ephemeral=True,
                )
                return

        embed = discord.Embed(
            title=f"Registering {character_name} — {realm}",
            description="Step 1: Select your **Class**",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=Step1View(character_name, realm), ephemeral=True)

    @app_commands.command(name="profile", description="Show your registered WoW character.")
    async def profile(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        with get_session() as session:
            user = session.query(User).filter_by(discord_id=discord_id).first()
            if not user:
                await interaction.response.send_message(
                    "You are not registered. Use `/register` to set up your character.", ephemeral=True
                )
                return
            embed = discord.Embed(title="Your WoW Profile", color=discord.Color.blurple())
            embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
            embed.add_field(name="Character", value=f"{user.character_name} — {user.realm}", inline=True)
            embed.add_field(name="Class / Spec", value=f"{user.spec} {user.wow_class}", inline=True)
            embed.add_field(name="Role", value=(user.role or "—").capitalize(), inline=True)
            embed.add_field(name="Content Focus", value=(user.content_focus or "—").title(), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unregister", description="Remove your registration and stop receiving alerts.")
    async def unregister(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        with get_session() as session:
            user = session.query(User).filter_by(discord_id=discord_id).first()
            if not user:
                await interaction.response.send_message("You are not registered.", ephemeral=True)
                return
            session.delete(user)
        await interaction.response.send_message(
            "Your registration has been removed. You will no longer receive patch alerts.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Registration(bot))
