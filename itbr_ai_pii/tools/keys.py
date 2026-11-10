import hashlib
import hmac
import os
import re

from odoo.tools import config

TOKEN_RE = re.compile(r'\b(CPF|CNPJ|EMAIL|PHONE|NAME|ADDR|DATE|DOC)#[0-9a-f]{12}\b')


def pii_key():
    """Return the HMAC key from the environment or the Odoo configuration file.

    The key is never read from the database. Empty means tokens are off.
    """
    value = os.environ.get('ODOO_AI_PII_KEY') or config.get('ai_pii_key')
    return str(value).strip() if value else ''


def make_token(kind, normalized, key):
    """Return ``KIND#`` plus the first 12 hex digits of the keyed hash."""
    digest = hmac.new(
        key.encode(), f'{kind}:{normalized}'.encode(), hashlib.sha256
    ).hexdigest()
    return f'{kind}#{digest[:12]}'
