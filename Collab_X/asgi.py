# Collab_X/asgi.py

import os
import django
from django.core.asgi import get_asgi_application

# --- THIS IS THE FIX ---
# We must set the settings module and run django.setup()
# BEFORE importing any other part of your app (like routing).

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Collab_X.settings')
django.setup()

# --- END OF FIX ---

# These imports must come AFTER django.setup()
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import chatapp.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            chatapp.routing.websocket_urlpatterns
        )
    ),
})