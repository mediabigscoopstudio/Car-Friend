import random
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Create a completed demo inspection report for madhav (all sections filled, score computed)"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Re-create even if madhav already has a submitted report")

    def handle(self, *args, **options):
        from accounts.models import User
        from inspections.models import InspectionVisit, InspectionReport
        from inspections.schema import CHECKPOINT_SCHEMA

        try:
            madhav = User.objects.get(username="madhav")
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                "User 'madhav' not found. Run: python manage.py seed_demo"
            ))
            return

        # Use existing submitted report if not forcing
        if not options["force"]:
            existing = InspectionReport.objects.filter(
                visit__inspector=madhav, is_locked=True
            ).first()
            if existing:
                self.stdout.write(self.style.WARNING(
                    f"Madhav already has a completed report (#{existing.id}). "
                    "Use --force to recreate."
                ))
                return

        # Find a non-submitted visit for madhav
        visit = InspectionVisit.objects.filter(
            inspector=madhav, status__in=["scheduled", "inprogress"]
        ).select_related("vehicle").first()

        if not visit:
            # Try reinspect too
            visit = InspectionVisit.objects.filter(
                inspector=madhav, status="reinspect"
            ).select_related("vehicle").first()

        if not visit:
            self.stderr.write(self.style.ERROR(
                "No pending visit found for madhav. Run: python manage.py seed_demo"
            ))
            return

        v = visit.vehicle
        visit.status = "submitted"
        visit.save()

        report, _ = InspectionReport.objects.get_or_create(visit=visit)

        checkpoints = {}

        # ── SUMMARY ─────────────────────────────────────────────────────────
        checkpoints["summary"] = {
            "year_of_manufacturing": str(v.year),
            "no_of_owners": "2",
            "duplicate_key": "No",
            "km": str(random.randint(28000, 75000)),
            "fuel_type": v.fuel or "Petrol",
            "registration_number": v.reg_number or "MH12AB1234",
            "reg_state": "Maharashtra",
            "reg_city": "Pune",
            "rto": "MH12",
            "city": "Pune",
            "rto_noc_issued": "No",
            "registration_year": str(v.year),
            "registration_month": "May",
            "fitness_upto": "2029-05-01",
            "insurance_type": "Comprehensive",
            "insurance_expiry": "2026-09-30",
            "road_tax_paid": "Yes",
            "road_tax_validity": "Lifetime",
            "cng_lpg_in_rc": "No",
            "rc_availability": "Original",
            "rc_condition": "Good",
            "mismatch_in_rc": "No",
            "under_hypothecation": "No",
            "chassis_number_embossing": "Clear",
            "inspection_at": "Pune Dealer — Baner",
            "branch": "Pune Central",
            "to_be_scrapped": "No",
            "manufacturing_month": "March",
        }

        # ── PARTS SECTIONS ───────────────────────────────────────────────────
        for sec_key, sec_schema in CHECKPOINT_SCHEMA.items():
            if sec_key == "summary" or sec_schema.get("kind") == "media":
                continue

            sec_data = {}
            for part in sec_schema.get("parts", []):
                # 10 % chance of an issue for visual richness in demo
                issue_roll = random.random() < 0.10

                if part["kind"] == "measure":
                    val = str(round(random.uniform(4.5, 8.5), 1))
                    sec_data[part["key"]] = {"_": {"value": val}}

                elif part["kind"] == "count":
                    val = str(random.randint(2, 4))
                    sec_data[part["key"]] = {"_": {"value": val}}

                else:  # ok / issue toggle
                    if part.get("subparts"):
                        sec_data[part["key"]] = {}
                        for sub in part["subparts"]:
                            st = "issue" if (random.random() < 0.10) else "ok"
                            note = _random_note() if st == "issue" else ""
                            sec_data[part["key"]][sub] = {"status": st, "condition": note}
                    else:
                        st = "issue" if issue_roll else "ok"
                        note = _random_note() if st == "issue" else ""
                        sec_data[part["key"]] = {"_": {"status": st, "condition": note}}

            checkpoints[sec_key] = sec_data

        report.checkpoints = checkpoints
        report.compute_score()
        report.is_locked = True
        report.decision = "pending"
        report.submitted_at = timezone.now()
        report.save()

        self.stdout.write(self.style.SUCCESS(
            f"✓ Demo inspection created for {madhav.get_full_name()} "
            f"— {v.title} · Score {report.score}/100 · Grade {report.condition_grade} "
            f"· Report #{report.id}"
        ))
        self.stdout.write(f"  View on master: http://master.localhost:8000/inspection_review/{report.id}")


def _random_note():
    notes = [
        "Minor scratch", "Small dent", "Paint fade", "Hairline crack",
        "Needs attention", "Surface rust", "Slight wear",
    ]
    return random.choice(notes)
