import discord
from discord.ext import commands
import database

async def is_admin(ctx_or_int):
    """
    Centralized check to see if a user has administrative powers.
    Supports both discord.Interaction and commands.Context.
    Enforces channel restrictions strictly if set.
    """
    # Normalize user, guild, and channel access
    if isinstance(ctx_or_int, discord.Interaction):
        user = ctx_or_int.user
        guild_id = ctx_or_int.guild_id
        channel_id = ctx_or_int.channel_id
        bot = ctx_or_int.client
    elif isinstance(ctx_or_int, commands.Context):
        user = ctx_or_int.author
        guild_id = ctx_or_int.guild.id if ctx_or_int.guild else None
        channel_id = ctx_or_int.channel.id
        bot = ctx_or_int.bot
    else:
        # Fallback for generic objects with enough context
        try:
            user = ctx_or_int.author
            guild_id = ctx_or_int.guild.id if ctx_or_int.guild else None
            channel_id = ctx_or_int.channel.id
            bot = ctx_or_int.bot
        except:
            return False

    # 0. Bot Owner always has access and bypasses all restrictions
    if await bot.is_owner(user):
        return True

    if not guild_id:
        return False

    # Fetch guild settings for auth
    settings = await database.get_all_guild_settings(guild_id)
    
    admin_roles_str = settings.get("admin_role_ids", "")
    admin_channels_str = settings.get("admin_channel_ids", "")

    # 1. STRICT CHANNEL CHECK
    # If a restriction is set, NO ONE (except Owner) can use it elsewhere.
    if admin_channels_str:
        allowed_channels = [c.strip() for c in admin_channels_str.split(",") if c.strip().isdigit()]
        if str(channel_id) not in allowed_channels:
            return False

    # 2. Server-wide Administrator has access (if channel check passed)
    if hasattr(user, "guild_permissions") and user.guild_permissions.administrator:
        return True

    # 3. Check Explicit Roles
    if admin_roles_str:
        allowed_roles = [r.strip() for r in admin_roles_str.split(",") if r.strip().isdigit()]
        user_role_ids = [str(r.id) for r in user.roles]
        if any(role_id in allowed_roles for role_id in user_role_ids):
            return True

    # 4. Fallback to config.json for initial setup (if no roles/channels configured in DB)
    if not admin_roles_str:
        try:
            from utils.jsonc import load_jsonc
            config = load_jsonc('config.json')
            config_role = str(config.get("admin_role_id"))
            if config_role and any(str(r.id) == config_role for r in user.roles):
                 return True
        except:
            pass

    return False
