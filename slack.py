import requests
import json

API = "https://slack.com/api/"


def _post(token: str, method: str, payload: dict, as_json: bool = True) -> bool:
    """
    Call one Slack Web API method. Returns True on success.

    Some older methods only accept form encoding, so profile.set (which needs
    a nested object) goes as JSON and the rest go as form fields.
    """
    if as_json:
        content_type = "application/json; charset=utf-8"
        body = json.dumps(payload)
    else:
        content_type = "application/x-www-form-urlencoded"
        body = "&".join(str(k) + "=" + str(v) for k, v in payload.items())

    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": content_type,
    }

    try:
        resp = requests.post(API + method, headers=headers, data=body)
        result = resp.json()
        resp.close()
        if not result.get("ok"):
            print("  Slack error (" + method + "):", result.get("error"))
            return False
        return True
    except Exception as e:
        print("  Slack request failed (" + method + "):", e)
        return False


def set_status(token: str, text: str, emoji: str) -> bool:
    """Status text and emoji. Needs users.profile:write."""
    payload = {
        "profile": {
            "status_text": text,
            "status_emoji": emoji,
            "status_expiration": 0,
        }
    }
    return _post(token, "users.profile.set", payload)


def set_presence(token: str, presence: str) -> bool:
    """"auto" (online) or "away". Needs users:write."""
    return _post(token, "users.setPresence", {"presence": presence}, as_json=False)


def snooze(token: str, minutes: int) -> bool:
    """Pause notifications for `minutes`. Needs dnd:write."""
    return _post(token, "dnd.setSnooze", {"num_minutes": minutes}, as_json=False)


def end_snooze(token: str) -> bool:
    """Resume notifications. Needs dnd:write."""
    return _post(token, "dnd.endSnooze", {}, as_json=False)
