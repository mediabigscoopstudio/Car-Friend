import json
import urllib.error
import urllib.request

from django.conf import settings
from .models import Notification


def _post_json(url, payload, headers=None):
    """POST JSON via the built-in urllib (the VPS's `requests` install is broken, dying
    with ConnectionResetError(104); urllib works). Returns True on a 2xx response, False on
    any HTTP error / connection failure — mirroring the old `requests` r.ok + try/except."""
    data = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json", "User-Agent": "CarFriend/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            return 200 <= int(status) < 300
    except Exception:
        return False

EVENT_CHANNELS = {
    "task_assigned":  ["inapp", "push"],
    "task_due":       ["inapp", "push", "whatsapp"],
    "auction_start":  ["inapp", "push", "whatsapp", "sms"],
    "bid_update":     ["inapp", "push"],
    "deal_confirmed": ["inapp", "push", "whatsapp", "sms"],
    "doc_pending":    ["inapp", "whatsapp"],
    "insp_assigned":  ["inapp", "push"],
    "insp_decision":  ["inapp", "push"],
    "kyc_result":     ["inapp", "sms"],
    "payment_ok":     ["inapp", "push", "whatsapp"],
}


def notify(recipient, event, title, body="", url="", channels=None):
    from core.models import FeatureToggle

    chans = channels or EVENT_CHANNELS.get(event, ["inapp"])
    n = Notification.objects.create(
        recipient=recipient, event=event, title=title,
        body=body, url=url, channels=chans,
    )
    delivered = {"inapp": True}
    if "push" in chans and recipient.fcm_token:
        delivered["push"] = _send_push(recipient.fcm_token, title, body, url)
    if "whatsapp" in chans and recipient.phone and FeatureToggle.is_on("whatsapp_alerts", True):
        delivered["whatsapp"] = _send_whatsapp(recipient.phone, f"{title}\n{body}")
    if "sms" in chans and recipient.phone:
        delivered["sms"] = _send_sms(recipient.phone, f"{title} {body}".strip())
    n.delivered = delivered
    n.save(update_fields=["delivered"])
    return n


def _send_push(token, title, body, url):
    if not settings.FCM_SERVER_KEY:
        return False
    return _post_json(
        "https://fcm.googleapis.com/fcm/send",
        {"to": token,
         "notification": {"title": title, "body": body},
         "data": {"url": url}},
        headers={"Authorization": f"key={settings.FCM_SERVER_KEY}"},
    )


def _send_whatsapp(phone, text):
    wa = settings.WHATSAPP
    if not wa["TOKEN"]:
        return False
    return _post_json(
        f"https://graph.facebook.com/v19.0/{wa['PHONE_ID']}/messages",
        {"messaging_product": "whatsapp", "to": phone,
         "type": "text", "text": {"body": text}},
        headers={"Authorization": f"Bearer {wa['TOKEN']}"},
    )


def _send_sms(phone, text):
    if not settings.SMS["API_KEY"]:
        return False
    return _post_json(
        "https://api.smsgateway.example/send",
        {"apikey": settings.SMS["API_KEY"],
         "sender": settings.SMS["SENDER"],
         "to": phone, "message": text},
    )
