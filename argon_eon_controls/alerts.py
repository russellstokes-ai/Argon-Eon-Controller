"""Edge-triggered Home Assistant alerts.

A standing condition (fan fault, emergency temperature, ...) raises one persistent
notification when it appears, is dismissed when it clears, and raises again if it
returns. An occurrence (a logged event such as a vanished disk) raises once while it
is in the recent-event window and is never auto-dismissed.
"""
import hashlib

def notification_id(message): return 'eon_'+hashlib.sha256(message.encode()).hexdigest()[:12]

def sync(notified,standing,occurrences,notify,dismiss):
 """notified: dict message->'standing'|'occurrence', owned by the caller.
 A failing notify/dismiss leaves state untouched for that message so it is retried next cycle."""
 for message in list(standing)+list(occurrences):
  if message not in notified:
   notify(message); notified[message]='standing' if message in standing else 'occurrence'
 for message in [m for m in notified if m not in standing and m not in occurrences]:
  if notified[message]=='standing': dismiss(message)
  del notified[message]
