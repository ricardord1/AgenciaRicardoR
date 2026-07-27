"""
Django settings for config project — AduanaBilling
Refactorizado para producción-ready: SECRET_KEY desde entorno,
DEBUG controlado, zona horaria Colombia, DRF con defaults seguros.
"""

from pathlib import Path
import os

# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# SEGURIDAD — Leer desde variables de entorno
# ============================================================
# En producción, define SECRET_KEY en tu entorno o archivo .env
# Nunca hardcodees esta clave en el código fuente.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-clave-de-desarrollo-reemplazar-en-produccion'
)

# ADVERTENCIA: Nunca uses DEBUG=True en producción.
# Define la variable de entorno DEBUG=False para producción.
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')


# ============================================================
# APLICACIONES INSTALADAS
# ============================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Terceros
    'rest_framework',
    # Apps propias
    'core.apps.CoreConfig',
    'facturacion.apps.FacturacionConfig',
]


# ============================================================
# MIDDLEWARE
# ============================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'


# ============================================================
# TEMPLATES
# ============================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ============================================================
# BASE DE DATOS
# ============================================================
# Por defecto SQLite para desarrollo.
# Para producción se recomienda PostgreSQL (ver .env.example).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Tipo de clave primaria por defecto (buena práctica desde Django 3.2+)
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================================
# VALIDACIÓN DE CONTRASEÑAS
# ============================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ============================================================
# INTERNACIONALIZACIÓN — Configurado para contexto colombiano
# ============================================================
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True


# ============================================================
# ARCHIVOS ESTÁTICOS
# ============================================================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# ============================================================
# DJANGO REST FRAMEWORK — Configuración global
# ============================================================
REST_FRAMEWORK = {
    # Autenticación: soporta sesión de Django (ideal para frontend mismo dominio)
    # y autenticación básica para desarrollo/pruebas.
    # Para producción con frontend separado, reemplazar BasicAuthentication
    # por TokenAuthentication o JWT (djangorestframework-simplejwt).
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    # Permisos por defecto: solo usuarios autenticados pueden escribir.
    # Cambiar a IsAuthenticated para requerir login en lecturas también.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    # Paginación por defecto para todos los listados
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Formato de fecha legible en las respuestas JSON
    'DATETIME_FORMAT': '%d/%m/%Y %H:%M',
}


# ============================================================
# CORREO ELECTRÓNICO
# ============================================================
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'facturacion@aduana.com')


# ============================================================
# TWILIO / WHATSAPP (Opcional)
# ============================================================
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
