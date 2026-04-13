from enum import IntEnum
from utils.config import config

class SubscriptionTier(IntEnum):
    STANDARD = 0
    PREMIUM = 1
    MASTER = 2

async def get_guild_tier(guild_id: int) -> SubscriptionTier:
    """Determine the subscription tier of a guild."""
    gid = int(guild_id)
    
    # 1. Check if it's a Master/Owner guild (highest priority)
    if gid in config.master_guild_ids:
        return SubscriptionTier.MASTER
    
    # 2. Check if it's a Premium guild
    if gid in config.premium_guild_ids:
        return SubscriptionTier.PREMIUM
        
    # 3. Future: check database for paid subscriptions
    # db_tier = await database.get_guild_tier(gid)
    # if db_tier: return SubscriptionTier(db_tier)
    
    return SubscriptionTier.STANDARD

async def is_premium(guild_id: int) -> bool:
    """Helper to check if a guild has at least Premium access."""
    tier = await get_guild_tier(guild_id)
    return tier >= SubscriptionTier.PREMIUM

async def is_master_guild(guild_id: int) -> bool:
    """Helper to check if a guild is a Master/Bot-Owner guild."""
    tier = await get_guild_tier(guild_id)
    return tier == SubscriptionTier.MASTER
