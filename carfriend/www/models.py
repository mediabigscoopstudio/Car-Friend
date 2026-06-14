from django.db import models


class HomepageLead(models.Model):
    """A lightweight, anonymous lead captured from the homepage "instant car
    price" hero. This is intentionally NOT crm.Lead — that model requires a
    registered seller and a Vehicle row, which a homepage visitor does not have.
    A retail associate can later qualify these into a full crm.Lead.
    """

    SOURCE_PLATE = "plate"
    SOURCE_BRAND = "brand"
    SOURCE_CHOICES = [
        (SOURCE_PLATE, "Plate lookup"),
        (SOURCE_BRAND, "Brand selection"),
    ]

    plate_number = models.CharField(max_length=20, blank=True)
    make         = models.CharField(max_length=100, blank=True)
    model        = models.CharField(max_length=100, blank=True)
    year         = models.IntegerField(null=True, blank=True)
    fuel_type    = models.CharField(max_length=30, blank=True)

    phone        = models.CharField(max_length=15)

    est_price_low  = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    est_price_high = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)

    source       = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_PLATE)
    is_contacted = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Homepage lead"
        verbose_name_plural = "Homepage leads"

    def __str__(self):
        car = " ".join(str(p) for p in [self.year, self.make, self.model] if p)
        return f"{self.phone} — {car or self.plate_number or 'unknown car'}"
