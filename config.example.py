# WiFi credentials
WIFI_SSID = "your_wifi_ssid"
WIFI_PASSWORD = "your_wifi_password"

# Slack API token — needs these user token scopes:
#   users.profile:write  status text and emoji
#   users:write          online / away presence
#   dnd:write            snoozing notifications
# Create at https://api.slack.com/apps → OAuth & Permissions
SLACK_TOKEN = "xoxp-your-token-here"

# Map each cube face to a Slack state.
# Face is determined by which axis of the accelerometer reads ~1g.
# Keys: "x+", "x-", "y+", "y-", "z+", "z-"
#   status_text / status_emoji: what shows next to your name
#   presence: "auto" (online) or "away"
#   dnd: True snoozes notifications while this face is up
FACE_STATUSES = {
    "z+": {"status_text": "Available",      "status_emoji": ":large_green_circle:", "presence": "auto", "dnd": False},
    "z-": {"status_text": "Do Not Disturb", "status_emoji": ":no_entry:",           "presence": "auto", "dnd": True},
    "x+": {"status_text": "In a Meeting",   "status_emoji": ":calendar:",           "presence": "auto", "dnd": True},
    "x-": {"status_text": "Lunch",          "status_emoji": ":fork_and_knife:",     "presence": "away", "dnd": False},
    "y+": {"status_text": "Focusing",       "status_emoji": ":headphones:",         "presence": "auto", "dnd": True},
    "y-": {"status_text": "Away",           "status_emoji": ":palm_tree:",          "presence": "away", "dnd": False},
}

# How long to snooze notifications for on a "dnd" face. Refreshed each time
# that face comes up, and cancelled as soon as you roll to a non-dnd face.
DND_SNOOZE_MINUTES = 120

# Seconds to hold a face before triggering a status change (debounce)
DEBOUNCE_SECONDS = 2

# An axis must exceed this (in g) to count as a settled face
GRAVITY_THRESHOLD = 0.7

# Shake the cube to open or close the setup network — no button needed, so
# the enclosure can stay sealed. Total acceleration must exceed
# SHAKE_THRESHOLD_G this many times within the window.
SHAKE_THRESHOLD_G = 1.8
SHAKE_COUNT = 3
SHAKE_WINDOW_SECONDS = 2

# I2C — the MPU9250 sits on I2C1, GP6/GP7. Confirmed by bus scan:
# 0x68 = MPU9250 (WHO_AM_I 0x71), 0x5C = LPS22HB pressure sensor.
# 400 kHz proved unreliable on this board; 100 kHz reads cleanly.
I2C_BUS = 1
I2C_SDA_PIN = 6
I2C_SCL_PIN = 7
I2C_FREQ = 100_000
