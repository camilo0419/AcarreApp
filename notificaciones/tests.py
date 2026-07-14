import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from empresa.models import Empresa
from usuarios.models import UserProfile

from .models import PushSubscription


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], VAPID_PRIVATE_KEY="")
class PushNotificationEndpointTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="Empresa", slug="empresa")
        self.user = User.objects.create_user("push_user", password="pass")
        UserProfile.objects.create(user=self.user, empresa=self.empresa, rol="GERENTE")
        self.client.force_login(self.user)

    def test_subscribe_saves_user_and_empresa(self):
        payload = {
            "subscription": {
                "endpoint": "https://push.example/sub/1",
                "keys": {"p256dh": "abc", "auth": "def"},
            }
        }
        response = self.client.post(
            reverse("notificaciones:subscribe"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        sub = PushSubscription.objects.get(endpoint="https://push.example/sub/1")
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.empresa, self.empresa)

    def test_push_side_effect_endpoints_require_post(self):
        self.assertEqual(self.client.get(reverse("notificaciones:test_me")).status_code, 405)
        self.assertEqual(self.client.get(reverse("notificaciones:delete_my_subs")).status_code, 405)
