"""
Seed demo data: one user of each internal role, one seller, one dealer,
one vehicle, one scheduled inspection visit.
Run: python manage.py seed_demo
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime


class Command(BaseCommand):
    help = "Seed demo data for every panel surface."

    def handle(self, *a, **k):
        from accounts.models import User, Role, SellerProfile, DealerProfile
        from vehicles.models import Vehicle
        from inspections.models import InspectionVisit
        from crm.models import Lead
        from core.models import FeatureToggle

        # Feature toggles
        for key, label in [
            ("whatsapp_alerts", "WhatsApp Alerts"),
            ("ocb",             "One Click Buy"),
            ("re_auction",      "Re-auction"),
        ]:
            FeatureToggle.objects.get_or_create(key=key, defaults={"label": label, "enabled": True})

        def make(username, role, is_internal, **kwargs):
            u, created = User.objects.get_or_create(username=username, defaults={
                "role": role, "is_internal": is_internal,
                "first_name": kwargs.get("first_name", username.title()),
                "email": f"{username}@carfriend.demo",
            })
            if created:
                u.set_password("demo1234")
                u.save()
            return u

        admin    = make("admin_demo",    Role.ADMIN,     True, first_name="Admin")
        retail   = make("retail_demo",   Role.RETAIL,    True, first_name="Retail")
        sales    = make("sales_demo",    Role.SALES,     True, first_name="Sales")
        inspector= make("inspector_demo",Role.INSPECTOR, True, first_name="Inspector")
        seller   = make("seller_demo",   Role.SELLER,    False, first_name="Seller")
        dealer_u = make("dealer_demo",   Role.DEALER,    False, first_name="Dealer")

        SellerProfile.objects.get_or_create(user=seller, defaults={"city": "Mumbai"})
        DealerProfile.objects.get_or_create(user=dealer_u, defaults={
            "dealership_name": "Demo Motors", "city": "Pune",
            "budget_min": 500000, "budget_max": 2000000,
            "brand_interest": "Maruti, Hyundai",
        })

        vehicle, _ = Vehicle.objects.get_or_create(
            seller=seller, make="Maruti", model="Swift", defaults={
                "variant": "VXI",
                "year": 2020,
                "reg_number": "MH12AB1234",
                "ownership": "1st owner",
                "location": "Mumbai",
                "expected_price": 650000,
                "status": "draft",
            }
        )

        visit, _ = InspectionVisit.objects.get_or_create(
            vehicle=vehicle, inspector=inspector,
            defaults={
                "scheduled_at": timezone.now() + datetime.timedelta(hours=2),
                "status": "scheduled",
            }
        )

        Lead.objects.get_or_create(
            seller=seller, vehicle=vehicle,
            defaults={
                "source": "demo",
                "stage": "new",
                "assigned_to": retail,
                "expected_price": 650000,
            }
        )

        self.stdout.write(self.style.SUCCESS(
            "Demo data seeded.\n"
            "  Login: admin_demo / demo1234  (master.localhost:8000)\n"
            "         retail_demo / demo1234  (teams.localhost:8000)\n"
            "         sales_demo / demo1234   (teams.localhost:8000)\n"
            "         inspector_demo / demo1234 (inspection.localhost:8000)\n"
        ))
