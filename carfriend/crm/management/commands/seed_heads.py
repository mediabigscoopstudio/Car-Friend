"""Seed test data for the Retail Head & Sales Head dashboards.

Idempotent (safe to re-run). Creates the two head users, a retail + a sales
associate, a few approved leads sitting in the Retail Head inbox, a couple of
dealers to allocate, and one winner-declined OCB sitting in the Sales Head
inbox. Prints credentials + the teams login URLs at the end.

    python manage.py seed_heads
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import DealerProfile, Role, User
from auctions.models import OCBListing
from crm.models import Lead
from vehicles.models import Vehicle

PASSWORD = "carfriend123"


def _user(username, role, name, *, internal, phone=""):
    u, _ = User.objects.get_or_create(username=username, defaults=dict(
        role=role, is_internal=internal, phone=phone,
        first_name=name.split()[0], last_name=" ".join(name.split()[1:]),
        email=f"{username}@carfriend.in",
    ))
    u.role = role
    u.is_internal = internal
    u.set_password(PASSWORD)
    u.save()
    return u


def _vehicle(seller, plate, make, model, year, price):
    v, _ = Vehicle.objects.get_or_create(plate_number=plate, defaults=dict(
        seller=seller, make=make, model=model, year=year,
        fuel_type=Vehicle.FUEL_PETROL, transmission=Vehicle.TRANSMISSION_MANUAL,
        colour="White", city="Ahmedabad", expected_price=price,
        status=Vehicle.STATUS_APPROVED,
    ))
    return v


class Command(BaseCommand):
    help = "Seed Retail Head / Sales Head test data (idempotent)."

    def handle(self, *args, **kwargs):
        rh = _user("retailhead", Role.RETAIL_HEAD, "Ravi Head", internal=True, phone="9000000010")
        sh = _user("saleshead", Role.SALES_HEAD, "Sana Head", internal=True, phone="9000000011")
        retail = _user("priya", Role.RETAIL, "Priya Sharma", internal=True, phone="9000000002")
        sales = _user("ankit", Role.SALES, "Ankit Verma", internal=True, phone="9000000003")

        # A seller + a few admin-approved, unallocated leads → Retail Head inbox.
        seller = _user("seller_demo", Role.SELLER, "Imran Shaikh", internal=False, phone="9810000001")
        approved_cars = [
            ("GJ01HX1001", "Maruti Suzuki", "Swift", 2022, 550000),
            ("GJ01HX1002", "Hyundai", "Creta", 2023, 1150000),
            ("GJ01HX1003", "Tata", "Nexon", 2022, 850000),
        ]
        for plate, make, model, year, price in approved_cars:
            v = _vehicle(seller, plate, make, model, year, price)
            Lead.objects.get_or_create(vehicle=v, defaults=dict(
                seller=seller, stage=Lead.STAGE_APPROVED))

        # A handful of dealers for the Sales Head to allocate.
        dealers = []
        for i, (uname, name, city) in enumerate([
            ("dealer_a", "Auto Hub", "Ahmedabad"),
            ("dealer_b", "City Motors", "Pune"),
            ("dealer_c", "Prime Cars", "Bengaluru"),
        ]):
            d = _user(uname, Role.DEALER, name, internal=False, phone=f"982000000{i}")
            DealerProfile.objects.get_or_create(user=d, defaults=dict(
                dealership_name=name, city=city, budget_min=300000,
                budget_max=1500000, brand_interest="Hatchback, SUV"))
            dealers.append(d)

        # A winner-declined OCB sitting in the Sales Head inbox.
        ocb_seller = _user("seller_ocb", Role.SELLER, "Sneha Reddy", internal=False, phone="9810000002")
        ov = _vehicle(ocb_seller, "GJ01HX2001", "Honda", "City", 2023, 980000)
        Lead.objects.get_or_create(vehicle=ov, defaults=dict(
            seller=ocb_seller, stage=Lead.STAGE_AUCTION_CLOSED))
        OCBListing.objects.get_or_create(
            vehicle=ov, status=OCBListing.Status.WINNER_DECLINED,
            defaults=dict(ocb_price=950000, assigned_to=retail,
                          offered_to=dealers[0], winner_responded_at=timezone.now()))

        out = self.stdout
        out.write(self.style.SUCCESS("Seeded Retail Head / Sales Head test data."))
        out.write("")
        out.write("Credentials (password for all: %s):" % PASSWORD)
        out.write("  Retail Head : retailhead")
        out.write("  Sales Head  : saleshead")
        out.write("  Retail assoc: priya")
        out.write("  Sales assoc : ankit")
        out.write("")
        out.write("Created: 3 approved leads (Retail Head inbox), 3 dealers, "
                  "1 winner-declined OCB (Sales Head inbox).")
        out.write("")
        out.write("Login on the teams subdomain:")
        out.write("  Retail Head → http://teams.localhost:8000/auth/login/  then /crm/retail-head/")
        out.write("  Sales Head  → http://teams.localhost:8000/auth/login/  then /crm/sales-head/")
