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
