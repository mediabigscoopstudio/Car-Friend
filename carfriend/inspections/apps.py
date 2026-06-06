from django.apps import AppConfig


class InspectionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inspections"

    def ready(self):
        import inspections.signals  # noqa
