import socket

import store

# Fixed display order, and short field names so face keys never need
# URL-escaping ("z+" would encode as "z%2B" in a form field name).
FACE_ORDER = ("z+", "z-", "x+", "x-", "y+", "y-")
FIELD = {"z+": "zp", "z-": "zn", "x+": "xp", "x-": "xn", "y+": "yp", "y-": "yn"}

PRESENCE_OPTIONS = (("auto", "Online"), ("away", "Away"))

READ_TIMEOUT = 2
MAX_REQUEST = 8192
BLANK_NETWORK_SLOTS = 2

# Browsers open several sockets at once — the page, favicon, and speculative
# preconnects that may never send a byte. A backlog of 1 drops the real
# request while we wait on an empty one, so queue a few and drain a few.
BACKLOG = 5
MAX_CONNECTIONS_PER_POLL = 4

# Plain string, not an f-string: MicroPython's f-string support is limited,
# and CSS braces would need doubling. Built by concatenation below instead.
CSS = """
body{font-family:system-ui,sans-serif;max-width:40rem;margin:1.5rem auto;padding:0 1rem}
input[type=text],input[type=password]{width:100%;padding:.4rem;box-sizing:border-box}
table{width:100%;border-collapse:collapse}td,th{padding:.2rem;text-align:left}
fieldset{margin-bottom:1rem;border:1px solid #ccc;border-radius:6px}
button{padding:.5rem 1rem;margin-right:.5rem}
.ok{background:#e6f4ea;padding:.5rem;border-radius:4px}
.warn{background:#fdf1e3;padding:.5rem;border-radius:4px}
.hint{color:#666;font-size:.85rem}
"""


def start(port: int = 80):
    """Listening socket, non-blocking so poll() never stalls the main loop."""
    addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(BACKLOG)
    s.setblocking(False)
    return s


def poll(server, settings: dict, config_mode: bool = False) -> bool:
    """
    Handle pending requests, if any. Returns True if settings changed.

    Non-blocking accept: with no client waiting this raises and we return
    immediately, so face detection keeps ticking.
    """
    changed = False

    for _ in range(MAX_CONNECTIONS_PER_POLL):
        try:
            client, _addr = server.accept()
        except OSError:
            break

        try:
            if _handle(client, settings, config_mode):
                changed = True
        except Exception as e:
            print("Web request failed:", e)
        finally:
            try:
                client.close()
            except Exception:
                pass

    return changed


def _handle(client, settings: dict, config_mode: bool) -> bool:
    """Serve one connection. Returns True if settings changed."""
    method, path, body = _read_request(client)

    # A preconnect that never sent a request. Nothing to answer.
    if not method:
        return False

    if path == "/favicon.ico":
        _send(client, "HTTP/1.0 404 Not Found\r\nConnection: close\r\n\r\n")
        return False

    if method == "POST" and path == "/save":
        changed = _apply(settings, _parse_form(body))
        store.save(settings)
        _respond(client, _page(settings, config_mode, "Saved."))
        return changed

    if method == "POST" and path == "/reboot":
        _respond(client, _page(settings, config_mode, "Rebooting..."))
        client.close()
        import machine

        machine.reset()

    _respond(client, _page(settings, config_mode))
    return False


def _read_request(client):
    client.settimeout(READ_TIMEOUT)

    buf = b""
    try:
        while b"\r\n\r\n" not in buf and len(buf) < MAX_REQUEST:
            chunk = client.recv(512)
            if not chunk:
                break
            buf += chunk
    except OSError:
        # Timed out with nothing useful — treat as an empty connection
        # rather than an error worth logging.
        pass

    head, _, rest = buf.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    request_line = lines[0].split(b" ")
    if len(request_line) < 2:
        return "", "", ""
    method, path = request_line[:2]

    length = 0
    for line in lines[1:]:
        name, sep, value = line.partition(b":")
        if sep and name.strip().lower() == b"content-length":
            length = int(value.strip())

    body = rest
    while len(body) < length and len(body) < MAX_REQUEST:
        chunk = client.recv(512)
        if not chunk:
            break
        body += chunk

    return method.decode(), path.decode(), body.decode()


# --- form handling ---------------------------------------------------------


def _unquote(s: str) -> str:
    s = s.replace("+", " ")
    out = bytearray()
    i = 0
    while i < len(s):
        # Need two full hex digits — a truncated "%2" is a literal, not \x02
        if s[i] == "%" and i + 2 < len(s):
            try:
                out.append(int(s[i + 1 : i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.extend(s[i].encode())
        i += 1
    return bytes(out).decode()


def _parse_form(body: str) -> dict:
    form = {}
    for pair in body.split("&"):
        if pair:
            key, _, value = pair.partition("=")
            form[_unquote(key)] = _unquote(value)
    return form


def _apply_networks(settings: dict, form: dict) -> bool:
    """Rebuild the network list from numbered form rows. Blank SSID removes."""
    # A form that doesn't carry network rows at all (a partial POST from a
    # script) must leave the saved list alone rather than emptying it.
    if "net_ssid_0" not in form:
        return False

    existing = {n["ssid"]: n.get("password", "") for n in settings.get("networks", [])}

    networks = []
    index = 0
    while True:
        ssid = form.get("net_ssid_" + str(index))
        if ssid is None:
            break
        ssid = ssid.strip()
        if ssid:
            password = form.get("net_pw_" + str(index), "").strip()
            # Blank password on a known network means "keep what we have"
            if not password:
                password = existing.get(ssid, "")
            networks.append({"ssid": ssid, "password": password})
        index += 1

    if networks != settings.get("networks"):
        settings["networks"] = networks
        return True
    return False


def _apply_faces(settings: dict, form: dict) -> bool:
    """
    Update the face table.

    Guarded by a hidden "faces" marker: unticked checkboxes aren't submitted
    at all, so without it we couldn't tell "unticked" from "not on this form".
    """
    if "faces" not in form:
        return False

    changed = False
    for face in FACE_ORDER:
        entry = settings["faces"].setdefault(face, {})
        suffix = FIELD[face]

        for name, key in (
            ("text_" + suffix, "status_text"),
            ("emoji_" + suffix, "status_emoji"),
            ("pres_" + suffix, "presence"),
        ):
            if name in form:
                value = form[name].strip()
                if value != entry.get(key, ""):
                    entry[key] = value
                    changed = True

        muted = ("dnd_" + suffix) in form
        if muted != bool(entry.get("dnd", False)):
            entry["dnd"] = muted
            changed = True

    return changed


def _apply(settings: dict, form: dict) -> bool:
    """Merge submitted fields into `settings`. Blank secrets keep the old value."""
    changed = _apply_networks(settings, form)

    if _apply_faces(settings, form):
        changed = True

    # Blank means "leave it alone" — the form never shows the current value,
    # so an empty box must not wipe a working credential.
    token = form.get("token", "").strip()
    if token:
        settings["slack_token"] = token
        changed = True

    return changed


# --- rendering -------------------------------------------------------------


def _esc(s) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _send(client, data):
    """
    send() may write only part of a large buffer and return the count, which
    silently truncates a 3KB page past lwIP's send buffer. Always send it all.
    """
    if isinstance(data, str):
        data = data.encode()
    try:
        client.sendall(data)
    except AttributeError:
        sent = 0
        while sent < len(data):
            sent += client.send(data[sent:])


def _respond(client, html: str):
    # Content-Length lets the browser render without waiting for the close.
    body = html.encode()
    _send(
        client,
        "HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: "
        + str(len(body))
        + "\r\nConnection: close\r\n\r\n",
    )
    _send(client, body)


def _field(name: str, value: str = "", kind: str = "text", placeholder: str = "") -> str:
    html = '<input name="' + name + '" type="' + kind + '"'
    if value:
        html += ' value="' + _esc(value) + '"'
    if placeholder:
        html += ' placeholder="' + placeholder + '"'
    return html + ">"


def _select(name: str, value: str, options) -> str:
    html = '<select name="' + name + '">'
    for option, label in options:
        selected = " selected" if value == option else ""
        html += '<option value="' + option + '"' + selected + ">" + label + "</option>"
    return html + "</select>"


def _checkbox(name: str, checked: bool) -> str:
    return '<input type="checkbox" name="' + name + '" value="1"' + (" checked" if checked else "") + ">"


def _page(settings: dict, config_mode: bool = False, status: str = "") -> str:
    """Build the config page by concatenation — no f-strings, no .format()."""
    token_state = "configured" if store.has_token(settings) else "not configured"
    keep = "leave blank to keep current"

    parts = [
        "<!DOCTYPE html><html><head>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Status Cube</title><style>", CSS, "</style></head><body>",
        "<h1>Status Cube</h1>",
    ]

    if status:
        parts.append('<p class="ok">' + _esc(status) + "</p>")
    if config_mode:
        parts.append('<p class="warn">Setup mode &mdash; not connected to WiFi, so Slack updates are paused.</p>')

    parts.append('<form method="POST" action="/save">')

    parts.append("<fieldset><legend>WiFi networks</legend>")
    parts.append('<p class="hint">Tried strongest-signal first. Clear an SSID to forget it.</p>')
    parts.append("<table><tr><th>Network</th><th>Password</th></tr>")
    networks = settings.get("networks", [])
    for index in range(len(networks) + BLANK_NETWORK_SLOTS):
        saved = networks[index] if index < len(networks) else {}
        suffix = str(index)
        parts.append("<tr><td>" + _field("net_ssid_" + suffix, saved.get("ssid", "")) + "</td>")
        parts.append("<td>" + _field("net_pw_" + suffix, "", "password", keep if saved else "") + "</td></tr>")
    parts.append("</table></fieldset>")

    parts.append("<fieldset><legend>Slack</legend>")
    parts.append('<p>User token <span class="hint">(' + token_state + ", starts xoxp-)</span><br>")
    parts.append(_field("token", "", "password", keep) + "</p>")
    parts.append("</fieldset>")

    parts.append("<fieldset><legend>Faces</legend>")
    parts.append('<input type="hidden" name="faces" value="1">')
    parts.append('<p class="hint">Mute pauses Slack notifications while that face is up.</p>')
    parts.append("<table><tr><th>Face</th><th>Status text</th><th>Emoji</th><th>Presence</th><th>Mute</th></tr>")
    for face in FACE_ORDER:
        entry = settings["faces"].get(face, {})
        suffix = FIELD[face]
        parts.append("<tr><td><code>" + face + "</code></td>")
        parts.append("<td>" + _field("text_" + suffix, entry.get("status_text", "")) + "</td>")
        parts.append("<td>" + _field("emoji_" + suffix, entry.get("status_emoji", "")) + "</td>")
        parts.append("<td>" + _select("pres_" + suffix, entry.get("presence", "auto"), PRESENCE_OPTIONS) + "</td>")
        parts.append("<td>" + _checkbox("dnd_" + suffix, entry.get("dnd", False)) + "</td></tr>")
    parts.append("</table></fieldset>")

    parts.append('<button type="submit">Save</button></form>')
    parts.append('<form method="POST" action="/reboot"><button type="submit">Reboot</button> ')
    parts.append('<span class="hint">needed after changing WiFi</span></form>')
    parts.append("</body></html>")

    return "".join(parts)
