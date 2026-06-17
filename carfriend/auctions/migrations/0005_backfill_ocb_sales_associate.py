from django.db import migrations

PREFIX = "Assigned to "
SUFFIX = " to collect offers."


def backfill(apps, schema_editor):
    """Existing OCBs created before the sales_associate field have it NULL. The
    Retail create flow recorded the assignment as an OCBMessage
    'Assigned to <name> to collect offers.' — map that name back to a Sales user."""
    OCBListing = apps.get_model("auctions", "OCBListing")
    User = apps.get_model("accounts", "User")

    name_to_id, ambiguous = {}, set()
    for u in User.objects.filter(role="sales"):
        full = f"{u.first_name} {u.last_name}".strip()
        for key in filter(None, [full, u.username]):
            if key in name_to_id and name_to_id[key] != u.id:
                ambiguous.add(key)
            else:
                name_to_id[key] = u.id
    for k in ambiguous:
        name_to_id.pop(k, None)

    for ocb in OCBListing.objects.filter(sales_associate__isnull=True):
        msg = (ocb.messages.filter(message__startswith=PREFIX, message__endswith=SUFFIX)
               .order_by("-created_at").first())
        if not msg:
            continue
        name = msg.message[len(PREFIX):-len(SUFFIX)].strip()
        uid = name_to_id.get(name)
        if uid:
            ocb.sales_associate_id = uid
            ocb.save(update_fields=["sales_associate"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0004_ocblisting_sales_associate"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
