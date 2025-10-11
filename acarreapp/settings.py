from pathlib import Path
import os
from dotenv import load_dotenv

# =========================
# Paths & env
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# =========================
# Core
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insegura")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Comma-separated list in .env, e.g. "localhost,127.0.0.1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# =========================
# Apps
# =========================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Project apps
    "empresa",
    "usuarios",
    "rutas",
    "servicios",
    "cartera",
    "dashboard",

    # Third-party
    "django_filters",
]

# =========================
# Middleware
# =========================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Tenancy actual de empresa
    "acarreapp.middleware.EmpresaActualMiddleware",
]

# =========================
# URLs / WSGI
# =========================
ROOT_URLCONF = "acarreapp.urls"
WSGI_APPLICATION = "acarreapp.wsgi.application"

# =========================
# Templates
# =========================
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            # Empresa actual a todas las plantillas
            "acarreapp.tenancy.empresa_context",
        ],
    },
}]

# =========================
# Database (env: DB_ENGINE=postgres|sqlite)
# =========================
if os.getenv("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# =========================
# Internationalization
# =========================
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# =========================
# Static & Media
# =========================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]        # tus assets (css/js/img) en desarrollo
STATIC_ROOT = BASE_DIR / "staticfiles"          # destino de collectstatic en producción

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =========================
# Auth redirects (usar NOMBRES, no rutas)
# =========================
LOGIN_REDIRECT_URL = "/post-login/"
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "/accounts/login/"


# =========================
# Misc
# =========================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
