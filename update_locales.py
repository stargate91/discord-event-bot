import json
import io

def update_locale(file_path, new_keys):
    with io.open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.update(new_keys)
    sorted_data = {k: data[k] for k in sorted(data.keys())}
    with io.open(file_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=2)

hu_keys = {
  'MASTER_STATS_TITLE': '📊 Nexus Globális Statisztikák',
  'MASTER_STATS_GUILDS': '🌐 Szerverek',
  'MASTER_STATS_EVENTS': '📅 Aktív Események',
  'MASTER_STATS_RSVPS': '📝 Összes Jelentkezés',
  'MASTER_STATS_VERSION': '🤖 Bot Verzió',
  'MASTER_STATS_PYTHON': '⚙️ Python Verzió',
  'MASTER_STATS_LATENCY': '🛰️ Késleltetés',
  'MASTER_STATS_FOOTER': 'Nexus Event Bot - Tulajdonosi Konzol',
  'MASTER_STATS_ERR': '❌ Hiba a statisztikák lekérésekor: {e}',
  'MASTER_EMOJI_TITLE': '🌍 Globális Emoji Kezelő',
  'MASTER_EMOJI_DESC': 'A minden szerveren elérhető központi ikonkészletek kezelése.',
  'MASTER_EMOJI_ERR': '❌ Hiba a Globális Emoji Varázsló megnyitásakor: {e}',
  'MASTER_PRESENCE_CFG_TITLE': '⚙️ Jelenlét Beállítások',
  'MASTER_PRESENCE_CFG_TIME': 'Forgási idő (másodperc)',
  'MASTER_PRESENCE_CFG_MODE': 'Mód (random vagy sequential)',
  'MASTER_PRESENCE_TXT_LBL': 'Státusz Szöveg',
  'MASTER_PRESENCE_TXT_PH': 'pl. {event_count} esemény',
  'MASTER_PRESENCE_TYPE_LBL': 'Típus (playing/watching/listening/competing)',
  'MASTER_PRESENCE_EDIT_TITLE': '✏️ Státusz Szerkesztése',
  'MASTER_PRESENCE_ADD_TITLE': '➕ Új Státusz',
  'MASTER_PRESENCE_TITLE': '🎮 Jelenlét (Presence) Vezérlő',
  'MASTER_PRESENCE_DESC': 'Állítsd be a bot státuszát, rotációs idejét és a megjelenített információkat.\nHasználható placeholderek: `{event_count}`, `{guild_count}`, `{rsvp_count}`',
  'MASTER_PRESENCE_CFG': '⚙️ Beállítások',
  'MASTER_PRESENCE_CFG_VAL': '**Forgás:** {time} másodperc\n**Mód:** {mode}',
  'MASTER_PRESENCE_ACTIVE': '📝 Aktív Státuszok',
  'MASTER_PRESENCE_NONE': '*Nincs beállítva státusz. Kattints a Hozzáadás gombra.*',
  'MASTER_PRESENCE_BTN_ADD': '➕ Új Státusz',
  'MASTER_PRESENCE_BTN_CFG': '⚙️ Beállítások',
  'MASTER_PRESENCE_SEL_PH': 'Szerkesztés/Törlés kiválasztása...',
  'MASTER_PRESENCE_EDIT_MODE': 'Szerkesztő Mód',
  'MASTER_PRESENCE_EDIT_DESC': 'Kiválasztva: **{type}**: {text}',
  'MASTER_PRESENCE_BTN_EDIT': '✏️ Szerkesztés',
  'MASTER_PRESENCE_BTN_DEL': '🗑️ Törlés',
  'MASTER_PRESENCE_BTN_BACK': '◀️ Vissza',
  'SYNC_START': '🔄 Szinkronizáció indítása...',
  'SYNC_GLOBAL_OK': '✅ {count} parancs sikeresen szinkronizálva globálisan.',
  'SYNC_COPY_OK': '✅ A globális parancsok átmásolva és szinkronizálva erre a szerverre (Összesen: {count}).',
  'SYNC_GUILD_OK': '✅ {count} parancs sikeresen szinkronizálva erre a szerverre.',
  'SYNC_FAILED': '❌ A szinkronizáció sikertelen: `{e}`',
  'SYNC_CLEAR_START': '🗑️ Minden parancs regisztráció törlése folyamatban...',
  'SYNC_CLEAR_OK': '✅ A parancsuk fája törölve. Használd a `!sync` parancsot az újra-regisztrációhoz.',
  'SYNC_CLEAR_FAILED': '❌ A törlés sikertelen: `{e}`'
}

en_keys = {
  'MASTER_STATS_TITLE': '📊 Nexus Global Statistics',
  'MASTER_STATS_GUILDS': '🌐 Guilds',
  'MASTER_STATS_EVENTS': '📅 Active Events',
  'MASTER_STATS_RSVPS': '📝 Total RSVPs',
  'MASTER_STATS_VERSION': '🤖 Bot Version',
  'MASTER_STATS_PYTHON': '⚙️ Python Version',
  'MASTER_STATS_LATENCY': '🛰️ Latency',
  'MASTER_STATS_FOOTER': 'Nexus Event Bot - Owner Console',
  'MASTER_STATS_ERR': '❌ Error retrieving stats: {e}',
  'MASTER_EMOJI_TITLE': '🌍 Global Emoji Management',
  'MASTER_EMOJI_DESC': 'Managing the central icon sets available to all servers.',
  'MASTER_EMOJI_ERR': '❌ Error opening Global Emoji Wizard: {e}',
  'MASTER_PRESENCE_CFG_TITLE': '⚙️ Presence Configuration',
  'MASTER_PRESENCE_CFG_TIME': 'Rotation time (seconds)',
  'MASTER_PRESENCE_CFG_MODE': 'Mode (random or sequential)',
  'MASTER_PRESENCE_TXT_LBL': 'Status Text',
  'MASTER_PRESENCE_TXT_PH': 'e.g., {event_count} events',
  'MASTER_PRESENCE_TYPE_LBL': 'Type (playing/watching/listening/competing)',
  'MASTER_PRESENCE_EDIT_TITLE': '✏️ Edit Status',
  'MASTER_PRESENCE_ADD_TITLE': '➕ New Status',
  'MASTER_PRESENCE_TITLE': '🎮 Presence Controller',
  'MASTER_PRESENCE_DESC': 'Configure the bot\'s status, rotation time, and displayed information.\nAvailable placeholders: `{event_count}`, `{guild_count}`, `{rsvp_count}`',
  'MASTER_PRESENCE_CFG': '⚙️ Settings',
  'MASTER_PRESENCE_CFG_VAL': '**Rotation:** {time} seconds\n**Mode:** {mode}',
  'MASTER_PRESENCE_ACTIVE': '📝 Active Statuses',
  'MASTER_PRESENCE_NONE': '*No status configured. Click the Add button.*',
  'MASTER_PRESENCE_BTN_ADD': '➕ Add Status',
  'MASTER_PRESENCE_BTN_CFG': '⚙️ Settings',
  'MASTER_PRESENCE_SEL_PH': 'Select for Edit/Delete...',
  'MASTER_PRESENCE_EDIT_MODE': 'Editor Mode',
  'MASTER_PRESENCE_EDIT_DESC': 'Selected: **{type}**: {text}',
  'MASTER_PRESENCE_BTN_EDIT': '✏️ Edit',
  'MASTER_PRESENCE_BTN_DEL': '🗑️ Delete',
  'MASTER_PRESENCE_BTN_BACK': '◀️ Back',
  'SYNC_START': '🔄 Starting synchronization...',
  'SYNC_GLOBAL_OK': '✅ Synced {count} commands globally.',
  'SYNC_COPY_OK': '✅ Global commands copied and synced to this guild ({count} total).',
  'SYNC_GUILD_OK': '✅ Synced {count} commands to this guild.',
  'SYNC_FAILED': '❌ Sync failed: `{e}`',
  'SYNC_CLEAR_START': '🗑️ Clearing all command registrations...',
  'SYNC_CLEAR_OK': '✅ Command tree cleared. Use `!sync` to re-register.',
  'SYNC_CLEAR_FAILED': '❌ Clear failed: `{e}`'
}

update_locale('locales/hu.json', hu_keys)
update_locale('locales/en.json', en_keys)
