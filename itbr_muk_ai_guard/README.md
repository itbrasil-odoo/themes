# ServIAm Guard (`itbr_muk_ai_guard`)

Guard rails for the MuK AI assistant (shown as "ServIAm" in pt_BR), each one a
switch in Settings > MuK AI > Guard, all on after installation:

- **Approve every write**: any create, update, delete or action the assistant runs
  waits for the user's approval, on every model. Out of the box MuK AI only asks
  for models flagged "Sensitive for AI" (just Users).
- **Only admins turn approvals off**: in a chat or on an agent. Without it any user
  can switch approvals off in their own chat.
- **Block web access**: `web_search`, `web_fetch` and the provider's built-in web
  search are off, so text planted in a record (an e-mail, a chatter message) cannot
  make the assistant send what it read to an outside address.

Odoo access rights and record rules still apply: the assistant acts as the user
who is chatting.

**API keys off the database.** A provider's key is read, in this order, from:

1. the environment variable `ODOO_AI_KEY_<PROVIDER>` (`ODOO_AI_KEY_ANTHROPIC`,
   `ODOO_AI_KEY_OPENAI`, `ODOO_AI_KEY_GOOGLE`);
2. the option `ai_key_<provider>` of the Odoo configuration file;
3. the provider's API Key field, as before.

For a provider whose code is not `default`, the account-specific name is tried
first: `ODOO_AI_KEY_ANTHROPIC_FILIAL_2` / `ai_key_anthropic_filial_2` (code in upper
case, anything outside `A-Z0-9` becomes `_`). The provider form then shows "Key set
on the server" instead of the field. A key left in the database as well is ignored,
with one warning in the log (without the key). Keys never reach backups or restored
copies of the database. The same names are used by IT Brasil's native-AI modules.

## Configuration

**Settings > MuK AI > Guard** (pt_BR: *Configurações > ServIAm > Proteções*):

- **Approve every write** — on by default.
- **Only admins turn approvals off** — on by default.
- **Block web access** — on by default.

API keys, in the server's environment (Docker `env_file`):

```
ODOO_AI_KEY_ANTHROPIC=sk-ant-...
```

or in the Odoo configuration file:

```
ai_key_anthropic = sk-ant-...
```

Then clear the key from the provider record.

## Known effects

- With the guard on, 11 `muk_ai` tests that expect free writes on
  non-sensitive models or web access fail by design.
- Agents that run unattended (`muk_ai_chatter`, `muk_ai_schedule`,
  `muk_ai_automation`) stop on the first write and wait for an approval
  nobody gives. Turn **Approve every write** off, or keep those modules
  uninstalled, until they get their own rule.

## Credits

Author: IT Brasil. Contributors:

- Renan Teixeira <renanteixeiracontato@gmail.com>
