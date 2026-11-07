# itbr_muk_ai_pii Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep personal data (CPF, CNPJ, e-mail, phone, address, birth date, names of person clients/contacts) out of the AI provider in every MuK AI (ServIAm) conversation, while users keep seeing real values.

**Architecture:** New module `itbr_muk_ai_pii` (depends on `muk_ai`). Three layers decide what leaves: blocked models (`muk_mcp.mixin._resolve_model`), per-field exposure on `ir.model.fields` applied in `muk_mcp.mixin._mcp_read` / `read_group` / `describe_model`, and a value detector run on every text crossing the provider boundary (`muk_ai.session._build_request_inputs`, `_build_compact_inputs`). Tokens are `TYPE#` + 12 hex of an HMAC with a server-side key; a token→value table restores real values in events, streamed text, approval previews and tool arguments.

**Tech Stack:** Odoo 19.0 (Community/Enterprise), Python 3.12, `hmac`/`hashlib`, OWL template inheritance for one notice. Tests: `odoo.tests` with `muk_ai.tests.common.AITestCommon`.

**Spec:** `docs/superpowers/specs/2026-11-07-itbr-muk-ai-pii-design.md` (read it first; this plan argues from it).

## Global Constraints

- Module path `itbr_muk_ai_pii/`, version `19.0.1.0.0`, license `LGPL-3`, author `IT Brasil`, website `https://github.com/itbrasil-odoo/themes`, depends `['muk_ai']`. Code style of the repo: single quotes, OCA layout, `readme/DESCRIPTION.md` + `README.md` + `static/description/index.html`, `i18n/pt_BR.po`.
- No change to upstream `muk_*` files unless a task says so (none does).
- HMAC key only from env `ODOO_AI_PII_KEY`, then `odoo.conf` option `ai_pii_key` (stripped). Never from the database. No key ⇒ tokens off (blocks still apply).
- Token format: regex `\b(CPF|CNPJ|EMAIL|PHONE|NAME|ADDR|DATE|DOC)#[0-9a-f]{12}\b`; value `TYPE#` + first 12 hex of `HMAC-SHA256(key, f'{TYPE}:{normalized}')`.
- Normalization: CPF/CNPJ digits only; e-mail lower-case and stripped; phone digits only with leading `55` added when 10–11 digits; names/text collapse whitespace and strip.
- Users see real values; the provider sees tokens; anything written to Odoo by the AI is detokenized.
- Team names stay readable: a `res.partner` linked to an internal user (`user_ids.share == False`) or to an `hr.employee` (when `hr` is installed) is not tokenized; Many2one to `res.users`/`hr.employee` is not tokenized.
- Default blocked models (only those present in the registry): `hr.contract`, `hr.version`, `hr.payslip`, `hr.payslip.line`, `hr.payslip.run`, `hr.salary.attachment`, `res.partner.bank`, `payment.token`.
- Tests offline; run with `bash /home/renanteixeira/Dev/Odoo/v19/custom/itbrasil/grupodedicata/.vscode/tools/muk_ai_run_tests.sh <modules> <tags>` with `DB=muk_ai_solo` (database without the guard); expected tail `0 failed, 0 error(s)`.
- Commits: Odoo style `[ADD]/[IMP]/[FIX] itbr_muk_ai_pii: ...`, English, no `Co-Authored-By`.

## Review Focus

1. A token split across two streamed deltas (`...CPF#3f1a` + `9c0d22e4 ...`): the user must see the real value, never a half token. → Task 7 test `test_stream_split_token`.
2. A token the model invents or copies from another user's chat: shown as-is, never resolved. → Task 1 test `test_foreign_token_not_revealed`.
3. Same CPF formatted two ways (`123.456.789-09` / `12345678909`) must give one token, so grouping works. → Task 2 test `test_same_cpf_two_formats`.
4. Tool result that is a list of dicts with nested Many2one tuples `[id, 'Name']` to a person partner: the name must be tokenized, the id kept. → Task 5 test `test_many2one_person_name_tokenized`.
5. An approval preview of `update_records` whose `values` carry tokens: the card shows real values, and dispatch writes real values. → Task 7 test `test_approval_preview_detokenized`.

---

### Task 1: Module, key, settings and token store

**Files:**
- Create: `itbr_muk_ai_pii/__init__.py`, `__manifest__.py`, `models/__init__.py`, `models/pii_token.py`, `models/res_config_settings.py`, `tools/__init__.py`, `tools/keys.py`, `security/ir.model.access.csv`, `data/ir_config_parameter.xml`, `views/res_config_settings.xml`, `tests/__init__.py`, `tests/test_token_store.py`

**Interfaces:**
- Produces:
  - `tools.keys.pii_key() -> str` (env, then `odoo.tools.config.get('ai_pii_key')`, stripped, `''` when unset).
  - `tools.keys.make_token(kind: str, normalized: str, key: str) -> str`.
  - `TOKEN_RE` (compiled regex, Global Constraints).
  - Model `itbr.muk_ai.pii.token` (`_log_access=False`): `token` (Char, unique, index), `kind` (Char), `value` (Char), `session_ids` (Many2many `muk_ai.session`, relation `itbr_muk_ai_pii_token_session_rel`). Access: none for users (no `ir.model.access` line for `base.group_user`; system-only read for audit).
  - `env['itbr.muk_ai.pii.token']._enabled() -> bool` (key present and parameter `itbr_muk_ai_pii.enabled == 'True'`).
  - `env['itbr.muk_ai.pii.token']._emit(kind: str, value: str, session) -> str` returns the token, upserts the row, links `session`; returns `value` unchanged when `not _enabled()` or `session` is empty.
  - `env['itbr.muk_ai.pii.token']._reveal(text: str, session) -> str` replaces every token emitted for a session of the same `user_id` or of the same subagent tree (walk `parent_session_id` when the field exists) with its value; others stay as-is.
  - `env['itbr.muk_ai.pii.token']._reveal_any(data, session)` recursive over `dict`/`list`/`str`.
  - Settings fields on `res.config.settings`: `itbr_muk_ai_pii_enabled` (Boolean, `config_parameter='itbr_muk_ai_pii.enabled'`, default on via data XML `True`), `itbr_muk_ai_pii_key_set` (Boolean compute, readonly), `itbr_muk_ai_pii_blocked_models` (Char, `config_parameter='itbr_muk_ai_pii.blocked_models'`, comma-separated, data default = list in Global Constraints), `itbr_muk_ai_pii_email_domains` (Char, `config_parameter='itbr_muk_ai_pii.email_domains'`, comma-separated, empty default). Block "Personal data" after `muk_ai_settings_defaults`, with a warning line when `not itbr_muk_ai_pii_key_set`.

- [ ] **Step 1: Write the failing tests** in `tests/test_token_store.py` (class `TestTokenStore(AITestCommon)`, patch `os.environ` with `ODOO_AI_PII_KEY='test-key'` like `itbr_muk_ai_guard/tests/test_external_key.py`):
  - `test_token_shape`: `_emit('CPF', '12345678909', s)` matches `^CPF#[0-9a-f]{12}$`.
  - `test_deterministic`: two sessions of the same user get the same token for the same value.
  - `test_reveal_own`: `_reveal(f'x {tok} y', s)` → `'x 12345678909 y'`.
  - `test_foreign_token_not_revealed`: token emitted only for another user's session stays literal.
  - `test_unknown_token_literal`: `'CPF#000000000000'` stays literal.
  - `test_disabled_without_key`: env without key → `_enabled()` False, `_emit` returns the value.
  - `test_disabled_by_setting`: key set, parameter removed → `_emit` returns the value.
  - `test_reveal_any_nested`: dict/list with tokens inside strings are revealed, non-strings untouched.
- [ ] **Step 2: Run, expect failures** — `DB=muk_ai_solo bash .../muk_ai_run_tests.sh itbr_muk_ai_pii /itbr_muk_ai_pii:TestTokenStore` → install error / failures.
- [ ] **Step 3: Implement** the files above. The key never goes into a field, log or error.
- [ ] **Step 4: Run, expect** `0 failed, 0 error(s) of 8 tests`.
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: HMAC tokens with a server-side key and a per-user token store`.

### Task 2: Value detector

**Files:**
- Create: `itbr_muk_ai_pii/tools/detector.py`, `tests/test_detector.py`

**Interfaces:**
- Produces: `detector.tokenize_text(text: str, emit: Callable[[str, str], str], email_domains: frozenset[str] = frozenset()) -> str` — finds CPF and CNPJ (formatted or 11/14 bare digits, only with valid check digits), e-mails (skipped when the domain is in `email_domains`), Brazilian phones (`(11) 91234-5678`, `+55 11 91234-5678`, `11912345678` only when prefixed by `+55` or formatted), normalizes per Global Constraints and replaces each match by `emit(kind, normalized)`. Text already holding tokens is left as is (do not re-tokenize `TYPE#hex`).
- Port the patterns from `oLucasAguilar/pii-tokens` `plugin/scripts/pii.py` (MIT); keep its copyright notice in a comment at the top of `detector.py`.

- [ ] **Step 1: Write failing tests** (`TestDetector`, plain `odoo.tests.BaseCase`, `emit` = `lambda k, v: f'{k}<{v}>'`):
  - `test_cpf_valid_formatted` → `'CPF<12345678909>'`; `test_cpf_invalid_digits_kept` (`123.456.789-00` unchanged).
  - `test_same_cpf_two_formats` → both forms emit the same normalized value.
  - `test_cnpj_valid` (`11.222.333/0001-81` → `CNPJ<11222333000181>`).
  - `test_email_and_allowed_domain` (`a@x.com` tokenized; `b@empresa.com.br` kept when domain allowed).
  - `test_phone_formats` (three formats above → `PHONE<5511912345678>`).
  - `test_existing_token_untouched` (`'CPF#3f1a9c0d22e4'` unchanged).
  - `test_protocol_number_not_cpf` (11 random digits failing the check digit unchanged).
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement `tokenize_text`.**
- [ ] **Step 4: Run, expect 0 failed.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: detect CPF, CNPJ, e-mail and phone in text`.

### Task 3: Field exposure classification

**Files:**
- Create: `itbr_muk_ai_pii/models/ir_model_fields.py`, `views/ir_model_fields.xml` (list + search + action + menu under MuK AI > Configuration), `tests/test_exposure.py`
- Modify: `models/__init__.py`, `__manifest__.py`

**Interfaces:**
- Produces on `ir.model.fields`:
  - `ai_exposure_auto` Selection `[('allow','Allowed'),('tokenize','Tokenized'),('block','Blocked')]`, stored compute on `name`, `ttype`, `model`.
  - `ai_exposure_override` same selection, optional (admin exceptions; never touched by module updates).
  - `ai_exposure` Selection compute (override or auto), searchable.
  - `env['ir.model.fields']._ai_exposure_map(model_name: str) -> dict[str, str]` cached per registry (`ormcache('model_name')`), cleared when an override is written.
- Rules (first match wins, field name compared lower-case):
  - block: `password`, names ending `_token` or `token`, `acc_number`, `iban`, names starting `bank_`, `wage`, `salary`, names starting `private_`, `ssnid`, `passport_id`, `identification_id`, `permit_no`, `visa_no`; any `binary` field on `hr.employee`.
  - tokenize: `vat`, `cnpj_cpf`, names starting `cpf` or `cnpj`, names starting `email`, `phone`, `mobile`, names starting `street`, `zip`, `birthday`, names starting `birth`, `contact_name`, `partner_name`, `invoice_partner_display_name`, names ending `_partner_name`; also `login` on `res.users`.
  - allow: everything else (including `city`, `state_id`, `country_id`).

- [ ] **Step 1: Failing tests** (`TestExposure`): `res.partner.vat` → tokenize; `res.partner.email` → tokenize; `res.partner.city` → allow; `res.users.password` → block; `res.partner.bank.acc_number` → block; `test_new_field_classified` creates `x_cpf_responsavel` (Char, manual field on `res.partner`) → tokenize; `test_override_survives_update` sets override `allow` on `res.partner.email`, triggers `ir.model.fields` recompute of `ai_exposure_auto`, override and effective value stay `allow`; `_ai_exposure_map('res.partner')['vat'] == 'tokenize'`.
- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Menu "Exposição dos campos à IA" (pt_BR) / "AI field exposure" for `base.group_system`, list grouped by `ai_exposure`, override editable inline.
- [ ] **Step 4: Run, expect 0 failed.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: classify fields as allowed, tokenized or blocked for the AI`.

### Task 4: Blocked areas

**Files:**
- Create: `itbr_muk_ai_pii/models/muk_mcp_mixin.py`, `tests/test_blocked_models.py`

**Interfaces:**
- Produces on `muk_mcp.mixin`:
  - `_itbr_pii_blocked_models() -> frozenset[str]` (from parameter, only names in `self.env`).
  - override `_resolve_model(model)`: blocked ⇒ `AccessError(_('Model %(model)r is not accessible via MCP.', model=model))` (same text as `muk_mcp_access`).
  - override `_mcp_listable_model_names()`: removes blocked names (keep `None` semantics: when super returns `None`, return all listable minus blocked — compute from `self.env.registry` models the same way `muk_mcp` lists them).
- Applies to the in-app chat and external MCP alike.

- [ ] **Step 1: Failing tests** (`TestBlockedModels`, as admin): `search_read` on `res.partner.bank` through `env['muk_mcp.tool']._call('search_read', {'model': 'res.partner.bank'}, env)` returns an error / raises `AccessError`; `list_models` result lacks `res.partner.bank`; removing it from the parameter makes it readable again.
- [ ] **Step 2–4: Run red, implement, run green.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: block HR/payroll and bank models from the AI`.

### Task 5: Record serialization (fields, names, read_group, describe)

**Files:**
- Create: `itbr_muk_ai_pii/tools/records.py`, `tests/test_records.py`
- Modify: `models/muk_mcp_mixin.py`, `models/muk_ai_session.py` (create; only `_tool_dispatch_context` here)

**Interfaces:**
- Consumes: Task 1 `_emit`, Task 3 `_ai_exposure_map`.
- Produces:
  - `muk_ai.session._tool_dispatch_context()` adds `itbr_pii_session_id: self.id`.
  - `muk_mcp.mixin._itbr_pii_session()` → the `muk_ai.session` from context, or empty (external MCP).
  - `records.mask_rows(env, model_name: str, rows: list[dict], session) -> list[dict]`: drops `block` fields; `tokenize` fields → `_emit(kind, value)` with kind by field (`vat`/`cnpj*`/`cpf*` → `CPF` or `CNPJ` by digit count; e-mail → `EMAIL`; phone/mobile → `PHONE`; street/zip → `ADDR`; birth* → `DATE`; name-copy fields → `NAME`; other → `DOC`); for `res.partner` rows the `name`/`display_name`/`complete_name` of person partners (not team, see Global Constraints) → `NAME`; Many2one values `[id, label]` whose comodel is `res.partner` and target is a non-team person → `[id, NAME#…]`. With no session (external MCP): `tokenize` fields are dropped instead and names stay (blocks only).
  - Overrides: `_mcp_read(records, fields)` → `mask_rows(...)` on the result; `_mcp_read_group(...)` → same masking on group label values of Many2one/tokenized groupby fields; `_mcp_describe_model(model, ...)` → removes blocked fields (and tokenized ones when no session).
  - `export_records`: drop `block` and `tokenize` fields from the requested field list when a session is active (exports go to files, not detokenizable) — note in README.

- [ ] **Step 1: Failing tests** (`TestRecords`, key in env, a session of a sales user):
  - `test_person_partner_masked`: person with vat/email/phone → `NAME#`, `CPF#`, `EMAIL#`, `PHONE#`; `city` real.
  - `test_company_partner`: company name real, `vat` → `CNPJ#`, `email` tokenized.
  - `test_team_partner_readable`: partner of an internal user keeps its name.
  - `test_many2one_person_name_tokenized`: `sale.order`-like row via `account.move` (`partner_id` to person) → `[id, 'NAME#…']`, id unchanged (use `res.partner` `parent_id` Many2one if sale/account not installed in the test DB).
  - `test_blocked_field_dropped`: `res.users` read never contains `password`.
  - `test_external_mcp_drops_tokenized`: no session in context → `vat` absent, name real.
  - `test_describe_hides_blocked`.
  - `test_read_group_partner_label_tokenized`.
- [ ] **Step 2–4: Run red, implement, run green.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: mask personal fields and person names in tool results`.

### Task 6: Provider boundary

**Files:**
- Modify: `itbr_muk_ai_pii/models/muk_ai_session.py`
- Create: `tests/test_provider_boundary.py`

**Interfaces:**
- Consumes: Task 1 `_emit`, Task 2 `tokenize_text`.
- Produces on `muk_ai.session`:
  - `_itbr_pii_tokenize(text: str) -> str` (detector with this session's `emit`, configured e-mail domains).
  - override `_build_request_inputs()` and `_build_compact_inputs(prefix)`: return copies where every text field is passed through `_itbr_pii_tokenize`: content blocks with `text` (types `input_text`, `output_text`), `function_call_output.output` when `str`, the system message text. Never mutate `self.conversation`.

- [ ] **Step 1: Failing tests** (`TestProviderBoundary`, capture the `inputs` kwarg via `self._mock_responses([...])` from `AITestCommon` — the fake receives `*args, **kwargs`):
  - `test_user_message_cpf_tokenized`: user writes a valid CPF → provider input holds `CPF#`, `session.conversation` still holds the digits.
  - `test_tool_output_note_tokenized`: a tool result string containing an e-mail is tokenized on the way out.
  - `test_compaction_tokenized`: `_build_compact_inputs([...])` with a CPF → token.
  - `test_round_count_unchanged`: a two-round mocked turn calls the provider exactly twice with the module installed.
- [ ] **Step 2–4: Run red, implement, run green.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: tokenize every text sent to the AI provider`.

### Task 7: Return path (events, stream, arguments, approval preview)

**Files:**
- Modify: `itbr_muk_ai_pii/models/muk_ai_session.py`
- Create: `tests/test_return_path.py`

**Interfaces:**
- Consumes: Task 1 `_reveal`, `_reveal_any`, `TOKEN_RE`.
- Produces on `muk_ai.session`:
  - override `_append_event(entry)`: stores `_reveal_any(entry)` (events are what users see).
  - override `_coalesce_and_emit(buffer_state, content_key, flush_key, delta, event_type)`: for `content_key == 'text'`, prepend `buffer_state.get('itbr_pii_tail', '')`, hold back a trailing fragment matching `r'(?:CPF|CNPJ|EMAIL|PHONE|NAME|ADDR|DATE|DOC)(?:#[0-9a-f]{0,11})?$'` in `buffer_state['itbr_pii_tail']`, reveal the rest, then call super with the revealed delta. Override `_flush_text_buffer(buffer_state)` to release the held tail (revealed) first.
  - override `_dispatch_tool_call(name, arguments, call_id)`: calls super with `_reveal_any(arguments)`.
  - override `_enter_waiting_approval(call, tool_calls, outputs, index, has_terminating, gate)`: passes a copy of `call` with revealed `arguments`.
  - `get_snapshot(include_conversation=True)`: reveal the returned `conversation` copy.

- [ ] **Step 1: Failing tests** (`TestReturnPath`):
  - `test_text_event_revealed`: final text with a token is stored revealed in `muk_ai.session.event`.
  - `test_stream_split_token`: feed `_coalesce_and_emit` the deltas `'O CPF é CPF#3f1a'` and `'9c0d22e4.'` (token emitted beforehand), collect published `text_delta` payloads (patch `_publish_event`), concatenation equals the real sentence and no payload contains `#`.
  - `test_tool_args_revealed`: mocked `search_read` call with domain `[('vat','=', tok)]` → the patched `muk_mcp.tool._call` receives the real CPF.
  - `test_approval_preview_detokenized`: guard-like pause on `update_records` with `values={'email': tok}` → `session.pending_ask` preview shows the real e-mail (use `_mark_sensitive('res.partner')`).
  - `test_conversation_keeps_tokens`: `session.conversation` still holds the token after the round.
- [ ] **Step 2–4: Run red, implement, run green.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: show and write real values back from tokens`.

### Task 8: Document confirmation

**Files:**
- Create: `itbr_muk_ai_pii/models/muk_ai_approval.py`, `tests/test_documents.py`

**Interfaces:**
- Produces: override `muk_ai.approval._assess_risk(tool_name, arguments)`: when `itbr.muk_ai.pii.token._enabled()` and `tool_name in ('print_report', 'read_resource')`, return a risk dict (same keys as upstream: `tool`, `model`, `ids`, `method`, `reason`, `signature`) with `model` resolved from the report (`ir.actions.report` by xmlid/report_name/id → `model`) or from the `odoo://<model>/...` URI, `reason` = `_('This document may contain personal data (CPF, address, name) that goes to the AI provider without masking.')`, `signature = self._signature(tool_name, model)`; otherwise `super()`. Blocked models (Task 4) already refuse before this.

- [ ] **Step 1: Failing tests** (`TestDocuments`): `print_report` of `base.action_report_...`-like report on `res.partner` pauses with the reason; `approve_tool(for_session=True)` (use the upstream approval API seen in `muk_ai/tests/test_approval.py`) lets a second call with the same model pass; tokens disabled ⇒ no pause.
- [ ] **Step 2–4: Run red, implement, run green.**
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: ask before a document goes to the AI unmasked`.

### Task 9: Attachment notice, translations, docs, full run

**Files:**
- Create: `itbr_muk_ai_pii/static/src/chat_composer.xml` (inherit `muk_ai.ChatComposer`, `t-inherit-mode="extension"`, after the `.mk_attachments` block: a muted line "Attachments go to the AI provider without masking personal data." shown when `props.attachments.length` and the session flag is on), `i18n/pt_BR.po`, `README.md`, `readme/DESCRIPTION.md`, `readme/CONTRIBUTORS.md`, `static/description/index.html`
- Modify: `__manifest__.py` (assets `web.assets_backend`)

**Interfaces:**
- Consumes: everything above. Exposes the flag to the client by adding `'itbr_pii_enabled'` to `muk_ai.session.get_snapshot()` result.

- [ ] **Step 1:** Template + snapshot flag; check in the browser on the copy (`.vscode/tools/ensaio_prodtree_up.sh -u itbr_muk_ai_pii` after `-i`), attach a file, see the line.
- [ ] **Step 2:** Export pt_BR (`odoo i18n export -d muk_ai_solo itbr_muk_ai_pii -l pt_BR`, modules before `-l`), translate, `python3 .vscode/tools/po_check.py` exits 0.
- [ ] **Step 3:** README (the three layers, the key variable, what is not covered: images/PDF without confirmation, external MCP gets blocks only, exports drop personal fields).
- [ ] **Step 4:** Full runs: `DB=muk_ai_solo ... muk_ai_run_tests.sh itbr_muk_ai_pii /itbr_muk_ai_pii` → 0 failed; `/muk_ai` with the module installed → only failures explained by masking (list them in the PR); `itbr_muk_ai_guard` tests still green with both installed. Then install `muk_ai_chatter` in a scratch database with this module and check that the text the AI composes into the chatter editor (it reads session events/snapshot) holds no `TYPE#` token; if it reads another path, reveal it there and add a test.
- [ ] **Step 5: Commit** `[ADD] itbr_muk_ai_pii: attachment notice, pt_BR and documentation`.
