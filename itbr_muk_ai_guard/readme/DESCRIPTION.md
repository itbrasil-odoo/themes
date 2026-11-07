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
