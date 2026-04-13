import asyncio
import sys
import time

# Mock classes to simulate the bot and DB environment needed for reminder parsing
class MockBot:
    def get_channel(self, cid):
        return MockChannel()
    async def fetch_user(self, uid):
        return MockUser(uid)
    def get_user(self, uid):
        return MockUser(uid)

class MockChannel:
    async def send(self, content=None, embed=None):
        print(f"CHANNEL SENT: {content} | embed: {embed}")

class MockUser:
    def __init__(self, uid):
        self.id = uid
    async def send(self, embed=None):
        print(f"DM SENT to {self.id} | embed: {embed}")

async def test_scheduler():
    sys.path.insert(0, ".") # To import from cogs and utils

    from utils.offset_parse import parse_offset
    from utils.emoji_utils import slugify
    from utils.lobby_utils import positive_status_ids
    from cogs.event_ui import get_active_set

    # Simulate properties
    event_id = "test_event"
    guild_id = "test_guild"
    now = time.time()
    start_ts = now + 50 # Starts in 50 seconds. 1m reminder means 60 seconds before.
    # So rem_ts = start_ts - 60 = now - 10. now >= rem_ts is TRUE.

    rsvps = [
        {"user_id": 111, "status": "accepted"},
        {"user_id": 222, "status": "coming"},
        {"user_id": 333, "status": "tank"},
        {"user_id": 444, "status": "wait_tank"}
    ]

    due = [
        {"slot_idx": 0, "offset_str": "1m", "method": "both", "target": "coming", "sent": 0, "custom_message": None}
    ]

    db_event = {
        "event_id": event_id,
        "guild_id": guild_id,
        "title": "Test Title",
        "channel_id": 999,
        "reminder_type": "none",
        "icon_set": "standard" # standard has 'accepted', 'tentative', 'declined' presumably
    }

    # Simulate participants
    participants = [r for r in rsvps if not str(r["status"]).startswith("wait_")]
    print(f"Participants calculated: {participants}")

    global_rem_type = (db_event.get("reminder_type") or "none").lower()
    shared_custom_msg = None

    active_set = get_active_set(db_event.get("icon_set", "standard"))
    pos_ids = set([s.lower() for s in positive_status_ids(active_set)])
    pos_ids.add("accepted")
    print(f"pos_ids: {pos_ids}")

    label_to_id = {}
    for opt in active_set.get("options", []):
        oid = opt["id"].lower()
        label_to_id[oid] = oid
        if opt.get("label"): label_to_id[slugify(opt["label"])] = oid
        if opt.get("list_label"): label_to_id[slugify(opt["list_label"])] = oid

    bot = MockBot()

    for r in due:
        target_raw = (r.get("target") or "coming")
        target_key = slugify(target_raw)
        print(f"target_key: {target_key}")

        is_coming_alias = target_key in ["coming", "positive", "accepted"]
        is_not_coming_alias = target_key in ["not_coming", "negative", "declined"]
        
        target_users = []
        if target_key == "all":
            target_users = participants
        elif is_coming_alias:
            target_users = [p for p in participants if p["status"].lower() in pos_ids]
        elif is_not_coming_alias:
            target_users = [p for p in participants if p["status"].lower() not in pos_ids]
        elif target_key in label_to_id:
            resolved_id = label_to_id[target_key]
            target_users = [p for p in participants if p["status"].lower() == resolved_id]
        elif target_key in [p["status"].lower() for p in participants]:
            target_users = [p for p in participants if p["status"].lower() == target_key]
        else:
            print(f"Target '{target_key}' not resolved. Trying role fallback.")

        print(f"Target users calculated: {target_users}")

        local_type = (r.get("method") or global_rem_type or "ping").lower()
        print(f"local_type: {local_type}")

        if local_type == "none":
            print("local_type is none, skipping")
            continue

        if local_type not in ["ping", "dm", "both"]:
            local_type = "ping"

        send_ping = local_type in ["ping", "both"]
        send_dm = local_type in ["dm", "both"]

        print(f"send_ping: {send_ping}, send_dm: {send_dm}")

        if send_ping:
            print("Would simulate PING")
        if send_dm:
            print("Would simulate DM")

if __name__ == "__main__":
    asyncio.run(test_scheduler())
