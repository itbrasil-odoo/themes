Tokens need an HMAC key that lives only on the server, never in the database.
Define it in one of two places (the environment wins):

- environment variable `ODOO_AI_PII_KEY`;
- option `ai_pii_key` in the Odoo configuration file.

Without a key, tokens are off.

Changing the key changes every token, so values seen before no longer match and
the AI provider's prompt cache is invalidated. Pick a key once and keep it.

## Deploy note

A fresh install (`-i`) is safe. A future upgrade (`-u`) that adds new view records may fail
on databases with `website` installed: in Odoo 20 upgrade mode this base-only module loads
before `website`, and `ir_ui_view.visibility` is `NOT NULL` without a database default.
Plan such an upgrade accordingly (for example, reinstall or set the default first).
