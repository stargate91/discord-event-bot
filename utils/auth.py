import discord
import database

async def is_admin(ctx_or_int):
    """
    Centralized check to see if a user has administrative powers.
    Supports both discord.Interaction and commands.Context.
    """
    import discord
    from discord.ext import commands

    # Normalize user, guild, and channel access
    if isinstance(ctx_or_int, discord.Interaction):
        user = ctx_or_int.user
        guild_id = ctx_or_int.guild_id
        channel_id = ctx_or_int.channel_id
    elif isinstance(ctx_or_int, commands.Context):
        user = ctx_or_int.author
        guild_id = ctx_or_int.guild.id if ctx_or_int.guild else None
        channel_id = ctx_or_int.channel.id
    else:
        return False

    # 1. Server-wide Administrator always has access
    if hasattr(user, "guild_permissions") and user.guild_permissions.administrator:
        return True

    if not guild_id:
        return False

    # Fetch guild settings for auth
    settings = await database.get_all_guild_settings(guild_id)
    
    admin_roles_str = settings.get("admin_role_ids", "")
    admin_channels_str = settings.get("admin_channel_ids", "")

    # 2. Check Roles
    if admin_roles_str:
        allowed_roles = [r.strip() for r in admin_roles_str.split(",") if r.strip().isdigit()]
        user_role_ids = [str(r.id) for r in user.roles]
        
        if any(role_id in allowed_roles for role_id in user_role_ids):
            # Check for channel restriction if roles match but channel is restricted
            if admin_channels_str:
                allowed_channels = [c.strip() for c in admin_channels_str.split(",") if c.strip().isdigit()]
                if str(channel_id) in allowed_channels:
                    return True
                else:
                    return False
            return True

    # 3. Fallback to config.json (initial setup)
    try:
        from utils.jsonc import load_jsonc
        config = load_jsonc('config.json')
        config_role = str(config.get("admin_role_id"))
        config_channel = str(config.get("admin_channel_id"))

        if config_role and any(str(r.id) == config_role for r in user.roles):
             if config_channel and config_channel != "None":
                 return str(channel_id) == config_channel
             return True
    except:
        pass

    return False
