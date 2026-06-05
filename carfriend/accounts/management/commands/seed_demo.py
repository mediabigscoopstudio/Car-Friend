import random
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, SellerProfile
from vehicles.models import Vehicle
from crm.models import Lead
from inspections.models import InspectionVisit

CARS = [
    ("Maruti Suzuki","Swift","VXi","Petrol"), ("Hyundai","Creta","SX","Diesel"),
    ("Tata","Nexon","XZ+","Petrol"), ("Skoda","Kylaq","Classic","Petrol"),
    ("Mahindra","XUV300","W8","Diesel"), ("Kia","Seltos","HTX","Petrol"),
    ("Honda","City","ZX","Petrol"), ("Toyota","Glanza","G","Petrol"),
    ("Renault","Kiger","RXZ","Petrol"), ("Volkswagen","Taigun","Highline","Petrol"),
    ("Maruti Suzuki","Baleno","Zeta","Petrol"), ("Hyundai","Venue","SX","Diesel"),
    ("Tata","Punch","Adventure","Petrol"), ("Nissan","Magnite","XV","Petrol"),
    ("MG","Astor","Sharp","Petrol"), ("Citroen","C3","Feel","Petrol"),
    ("Maruti Suzuki","Brezza","ZXi","Petrol"),
]
STATES = [
    ("GJ","09","Ahmedabad","Gujarat"),
    ("MH","12","Pune","Maharashtra"),
    ("DL","03","New Delhi","Delhi"),
    ("KA","05","Bengaluru","Karnataka"),
    ("TN","10","Chennai","Tamil Nadu"),
]
SELLERS = [
    ("Rohan Mehta","rohan"),
    ("Anjali Nair","anjali"),
    ("Imran Shaikh","imran"),
    ("Sneha Reddy","sneha"),
    ("Vikram Singh","vikram"),
]


def _make_thumb(label):
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (480, 320), (14, 17, 14))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 250, 480, 320], fill=(1, 83, 16))
        d.text((18, 270), f"Car Friend · {label}", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        name = f"thumb_{label.replace(' ', '_').replace('/', '_')}.jpg"
        return ContentFile(buf.getvalue(), name=name)
    except Exception:
        return None


class Command(BaseCommand):
    help = "Seed Car Friend demo data (Indian users, cars, leads, scheduled inspections)."

    def handle(self, *args, **kwargs):
        def mk(username, role, name, phone, internal):
            u, _ = User.objects.get_or_create(
                username=username,
                defaults=dict(
                    role=role, is_internal=internal, phone=phone,
                    first_name=name.split()[0],
                    last_name=" ".join(name.split()[1:]),
                ),
            )
            u.set_password("carfriend123")
            u.role = role
            u.is_internal = internal
            u.save()
            return u

        admin = mk("admin", "admin", "Admin User", "9000000001", True)
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()

        priya  = mk("priya",  "retail",    "Priya Sharma", "9000000002", True)
        ankit  = mk("ankit",  "sales",     "Ankit Verma",  "9000000003", True)
        madhav = mk("madhav", "inspector", "Madhav Joshi", "9000000004", True)

        pool = list(CARS)
        random.shuffle(pool)
        ci = 0

        for full_name, uname in SELLERS:
            seller = mk(uname, "seller", full_name, f"98{random.randint(10000000,99999999)}", False)
            SellerProfile.objects.get_or_create(user=seller)
            st = random.choice(STATES)

            for _ in range(random.randint(3, 4)):
                mk_, md, var, fuel = pool[ci % len(pool)]
                ci += 1
                year = random.choice([2021, 2022, 2023, 2024, 2025])
                reg = (
                    f"{st[0]}{st[1]} "
                    f"{random.choice('ABCDEFGH')}{random.choice('ABCDEFGH')} "
                    f"{random.randint(1000,9999)}"
                )
                v = Vehicle.objects.create(
                    seller=seller, make=mk_, model=md, variant=var, year=year, fuel=fuel,
                    reg_number=reg,
                    ownership=f"{random.randint(1,2)} owner",
                    location=st[2],
                    expected_price=random.randint(4, 12) * 100000,
                    status="draft",
                )
                thumb = _make_thumb(f"{mk_} {md}")
                if thumb:
                    try:
                        v.thumbnail.save(thumb.name, thumb, save=True)
                    except Exception:
                        pass

                Lead.objects.create(
                    seller=seller, vehicle=v, source="website",
                    stage="qualified", assigned_to=priya,
                    expected_price=v.expected_price,
                )
                InspectionVisit.objects.create(
                    vehicle=v, inspector=madhav, status="scheduled",
                    scheduled_at=timezone.now() + timedelta(
                        days=random.randint(0, 3),
                        hours=random.randint(9, 17),
                    ),
                )

        self.stdout.write(self.style.SUCCESS(
            "Seeded: admin, priya (retail), ankit (sales), madhav (inspector), "
            "5 sellers with 3-4 cars each. All passwords: carfriend123"
        ))
