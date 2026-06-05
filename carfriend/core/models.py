from django.conf import settings
from django.db import models


class FeatureToggle(models.Model):
    key         = models.SlugField(unique=True)
    label       = models.CharField(max_length=160)
    enabled     = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.label} [{'ON' if self.enabled else 'OFF'}]"

    @classmethod
    def is_on(cls, key, default=True):
        val = cls.objects.filter(key=key).values_list("enabled", flat=True).first()
        return val if val is not None else default


class AuditLog(models.Model):
    actor       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action      = models.CharField(max_length=120)
    target_type = models.CharField(max_length=80, blank=True)
    target_id   = models.CharField(max_length=40, blank=True)
    meta        = models.JSONField(default=dict, blank=True)
    ip          = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor} {self.action}"


def log(actor, action, target=None, request=None, **meta):
    AuditLog.objects.create(
        actor=actor, action=action,
        target_type=type(target).__name__ if target else "",
        target_id=str(getattr(target, "pk", "")),
        ip=(request.META.get("REMOTE_ADDR") if request else None),
        meta=meta,
    )
