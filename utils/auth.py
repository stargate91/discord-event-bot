import discord
import database

async def is_admin(interaction: discord.Interaction):
    """
    Centralized check to see if a user has administrative powers.
    1. Server administrator permission check.
    2. Check for specially authorized roles from database.
    3. Check if current channel is in the allowed admin channels list (if set).
    """
    # 1. Server-wide Administrator always has access
    if interaction.user.guild_permissions.administrator:
        return True

    guild_id = interaction.guild_id
    if not guild_id:
        return False

    # Fetch guild settings for auth
    # admin_role_ids: "id1, id2, id3"
    # admin_channel_ids: "idA, idB"
    settings = await database.get_all_guild_settings(guild_id)
    
    admin_roles_str = settings.get("admin_role_ids", "")
    admin_channels_str = settings.get("admin_channel_ids", "")

    # 2. Check Roles
    if admin_roles_str:
        allowed_roles = [r.strip() for r in admin_roles_str.split(",") if r.strip().isdigit()]
        user_role_ids = [str(r.id) for r in interaction.user.roles]
        
        if any(role_id in allowed_roles for role_id in user_role_ids):
            # Check for channel restriction if roles match but channel is restricted
            if admin_channels_str:
                allowed_channels = [c.strip() for c in admin_channels_str.split(",") if c.strip().isdigit()]
                if str(interaction.channel_id) in allowed_channels:
                    return True
                else:
                    return False # Roles match but wrong channel
            return True

    # 3. If no specific roles/channels set, fallback to config.json (initial setup)
    # This part is for bootstrapping before the DB settings are configured
    try:
        from utils.jsonc import load_jsonc
        config = load_jsonc('config.json')
        config_role = str(config.get("admin_role_id"))
        config_channel = str(config.get("admin_channel_id"))

        if config_role and any(str(r.id) == config_role for r in interaction.user.roles):
             if config_channel and config_channel != "None":
                 return str(interaction.channel_id) == config_channel
             return True
    except:
        pass

    return False
