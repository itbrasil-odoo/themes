# ServIAm Personal Data (`itbr_muk_ai_pii`)

Keeps clients' personal data out of the AI provider in MuK AI chats (shown as
"ServIAm" in pt_BR), as LGPD asks. What the assistant reads from Odoo is masked
before it leaves the server, and the people chatting keep seeing the real values.

Three layers decide what the provider gets:

1. **Blocked models**: HR/payroll and bank data (`hr.contract`, `hr.payslip`,
   `res.partner.bank`, `payment.token`, ...) are not readable at all. The list is
   editable in Settings > MuK AI > Personal data.
2. **Field exposure**: every field is *allowed*, *tokenized* or *blocked*, by
   name and type, with admin exceptions that survive updates. Tokenized fields
   (CPF, CNPJ, e-mail, phone, address, birth date and the name of a person
   contact) reach the provider as `KIND#hex` tokens of the chat. Company names and
   the team's names stay readable. The list "AI field exposure" shows the
   classification for audit.
3. **Detector on the value**: every text sent to the provider is scanned for CPF
   and CNPJ (valid check digits), e-mail and Brazilian phone numbers, wherever it
   comes from (notes, chatter, tool results, the user's message).

On the way back, tokens in the assistant's text, in tool arguments and in approval
previews are turned into the real values, so a search by CPF or a posted message
uses the real data and the screen never shows a token.

Tokens are an HMAC of the value with a key that lives only on the server: the
environment variable `ODOO_AI_PII_KEY` or the option `ai_pii_key` of the Odoo
configuration file. Without a key, tokens are off.

**Known limits**

- Names in free text are not detected: only CPF, CNPJ, e-mail and phone, by value.
- Grouping by a name field tokenizes company and team names too.
- Images, PDFs and attachments the user adds go unmasked (a notice is shown under
  them); documents the AI fetches ask for confirmation first.
- External MCP clients get blocks only: tokenized fields are dropped, no tokens.
- In-chat exports keep tokenized fields (the file goes to the user); external
  exports drop them.
- With this module installed, 5 upstream `muk_mcp` tests fail by design (external
  callers no longer receive `email`).
- Optional modules not covered yet: `muk_ai_subagents`, `muk_ai_chatter`,
  `muk_ai_automation`, `muk_ai_decision` need a bridge before being installed
  together with this module (checked: `muk_ai_chatter` posts the stored answer,
  tokens included, as the note of a mention).
- The HMAC key comes only from env `ODOO_AI_PII_KEY` or odoo.conf `ai_pii_key`;
  without it tokens are off.
- The module depends on `muk_mcp_access`.

## Usage

What the assistant reads from Odoo tools (`search_read`, `read_records`,
`read_group`, `describe_model`) is masked before it goes to the AI provider:

- **Blocked** fields are left out, and a link to a blocked model reads `False`.
- **Tokenized** fields (CPF, CNPJ, e-mail, phone, address, birth date) become
  `KIND#hex` tokens of the chat, and so do the names of person contacts.
  Company names and the names of the team (internal users, employees) stay
  readable.
- **External MCP clients** (no chat session, nothing to turn tokens back):
  tokenized fields are left out and names stay real; blocks apply as well.
- **Exports** (`export_records`) leave out blocked fields. In a chat, tokenized
  fields are exported with their real values (a CSV/XLSX file cannot have its
  tokens turned back); for external MCP clients they are left out.
- **`get_messages`** and **`call_method`** with `read`, `search_read`,
  `web_read`, `web_search_read`, `name_search`, `read_group` or
  `formatted_read_group` are masked the same way.

## Configuration

**Settings > MuK AI > Personal data** (pt_BR: *Configurações > ServIAm > Dados
pessoais*):

- **Protect personal data**: on by default. Shows a warning when no key is set.
- **Blocked models**: comma-separated list of models the assistant cannot read.
- **Company e-mail domains**: e-mails on these domains stay readable.

The key, in the server's environment (Docker `env_file`):

```
ODOO_AI_PII_KEY=<long random string>
```

or in the Odoo configuration file:

```
ai_pii_key = <long random string>
```

Changing the key makes new tokens differ from the old ones; the chats keep the
tokens they already hold.

The field classification is in the MuK AI menu, **AI field exposure**
(pt_BR: *Exposição dos campos à IA*, administrators only); an administrator sets the exception in
*AI Exposure Override*.

## Credits

Author: IT Brasil. Contributors:

- Renan Teixeira <renanteixeiracontato@gmail.com>
