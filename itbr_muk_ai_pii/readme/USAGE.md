What the assistant reads from Odoo tools (`search_read`, `read_records`,
`read_group`, `describe_model`) is masked before it goes to the AI provider:

- **Blocked** fields are left out, and a link to a blocked model reads `False`.
- **Tokenized** fields (CPF, CNPJ, e-mail, phone, address, birth date) become
  `KIND#hex` tokens of the chat, and so do the names of person contacts.
  Company names and the names of the team (internal users, employees) stay
  readable.
- **External MCP clients** (no chat session, nothing to turn tokens back):
  tokenized fields are left out and names stay real; blocks apply as well.
- **Exports** (`export_records`) leave out blocked and tokenized fields, in a
  chat too: a CSV/XLSX file cannot have its tokens turned back.
