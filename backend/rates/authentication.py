"""Bearer-token auth for the ingest webhook.

A shared-secret bearer token from INGEST_API_TOKEN, which fits a machine-to-machine
webhook and avoids a User+Token table. GET endpoints stay open.
"""

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework import authentication, exceptions


class BearerTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None  # no bearer header -> let permission layer reject
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Invalid bearer header: malformed token.")
        try:
            token = header[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Invalid bearer token: non-UTF-8 bytes.")
        # Constant-time compare so response timing can't leak the token byte by byte.
        if not constant_time_compare(token, settings.INGEST_API_TOKEN):
            raise exceptions.AuthenticationFailed("Invalid bearer token.")
        return (BearerTokenUser(), None)

    def authenticate_header(self, request):
        return self.keyword


class BearerTokenUser:
    """Minimal authenticated principal (no DB user needed for a webhook)."""

    is_authenticated = True
