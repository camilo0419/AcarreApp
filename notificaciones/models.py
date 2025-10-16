from django.conf import settings
from django.db import models

class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subs")
    endpoint = models.URLField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} · {self.endpoint[:40]}..."
