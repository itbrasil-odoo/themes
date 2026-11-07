# SDD ledger — plan: docs/superpowers/plans/2026-11-07-itbr-muk-ai-pii.md
Spec: docs/superpowers/specs/2026-11-07-itbr-muk-ai-pii-design.md
Branch: feat/muk-ai-pii-19 (themes), start b52a7420^ = parent of the design commit; MERGE_BASE for final review = 8d? use `git merge-base origin/imp/muk-ai-ptbr-19 HEAD`

## Pre-flight scan
| Tasks | Shared file/interface | Finding |
|---|---|---|
| T1→T5,T6,T7,T8 | `_emit`, `_reveal`, `_reveal_any`, `_enabled`, `TOKEN_RE` | consistent names |
| T2→T6 | `tokenize_text(text, emit, email_domains)` | consistent |
| T3→T5 | `_ai_exposure_map(model_name)` | consistent |
| T4→T5 | models/muk_mcp_mixin.py created in T4, modified in T5 | sequential, fine |
| T5→T6→T7 | models/muk_ai_session.py created T5 (_tool_dispatch_context), extended T6, T7 | sequential, fine |
| T7↔T9 | both touch `get_snapshot` (T7 reveal conversation, T9 add flag) | T9 must extend T7's override, not add a second |
| T5 vs spec | plan drops tokenized fields from export_records; spec lists export under masking | see ruling R1 |
| T8 | upstream approval API name (`approve_tool(for_session=...)`) not verified in plan | implementer reads muk_ai/tests/test_approval.py |
| each task | tests vs code self-consistent | T1–T9 checked, no contradiction found |

Ruling R1: export_records drops tokenized+blocked fields when a session is active (plan) instead of emitting tokens (spec) — exported files leave the chat and cannot be detokenized for the user — cost if wrong: AI exports lack e-mail/phone columns; easy to switch to tokens later.
Ruling R2: T9 extends the get_snapshot override written in T7 — two overrides of the same method in one class would shadow each other — cost if wrong: none.
Ruling R3: work in place on branch feat/muk-ai-pii-19 (no extra worktree) — the local Odoo containers mount this checkout path for tests — cost if wrong: an unrelated edit in this checkout during the run would mix into the branch.

## Progress
Task 1: dispatched (BASE 034f1b95, implementer a0569cdc3c9945095, sonnet)
Task 1: implemented d80d4fe5 (DONE_WITH_CONCERNS: subagent-tree reveal untested)
Task 1: review 1 — Needs fixes: I1 subagent-tree reveal untested; I2 concurrent first emit IntegrityError
Task 1: minor (deferred): foreign-token test lacks shared-row case and other-session-same-user case
Task 1: minor (deferred): _tree_session_ids re-walked per _reveal call (cache for streaming in T7)
Task 1: minor (deferred): settings view field order (key_set field after div)
Ruling R4: fold the minor "empty user_id ⇒ domain = False" into fix round 1 — it decides who sees real values — cost if wrong: one extra line
Task 1: fix round 1/5 (3 addressed, 0 open; commits d80d4fe5..98bc118c)
Task 1: minor (deferred): test_reveal_without_user_uses_tree_only would pass before the fix (weak)
Task 1: minor (deferred): invalidate_all() after single-row insert is heavy on hot path
Task 1: complete (commits 034f1b95..98bc118c, review clean after 1 fix round)
Task 2: dispatched (BASE 98bc118c)
Task 2: implemented 1b91ae7e (TDD order not followed: code before tests; report file transcribed by controller)
Task 2: review 1 — Needs fixes: spec ❌ phone test (3 formats not asserted); I1 token-preservation test cannot fail; I2 CPF as e-mail local part leaks domain; I3 thin tests
Ruling R5: fold into fix round — phones without +55/parentheses ("11 91234-5678", "55 11 91234-5678", double space after +55) and NUL-placeholder crash — both leak or crash on ordinary input — cost if wrong: a few more phone false positives
Ruling R6: alphanumeric CNPJ out of scope for v1 (brief and spec say digits) — cost if wrong: alphanumeric CNPJs leak until added
Task 2: minor (deferred): CPF glued to letters/dots (CPF12345678909, ref.12345678909) missed
Task 2: minor (deferred): space-separated CPF/CNPJ widen false positives
Task 2: minor (deferred): email_domains exact match (subdomains/@-prefixed entries) undocumented
Task 2: minor (deferred): dead .strip() on e-mail
Task 2: fix round 1/5 (5 addressed, 1 open — I1 token-preservation test cannot fail; new breakage: separator-only phone rule matches '20 1234-5678', year ranges; commits 1b91ae7e..392d6357)
Ruling R7: I1 closed as satisfied by construction — a 12-hex TOKEN_RE token cannot contain any span a CPF/CNPJ/e-mail/phone rule matches, so "leave tokens untouched" holds without the token alternative; the tests stay as regression guards — cost if wrong: a future rule matching hex runs would re-tokenize tokens unnoticed
Task 2: fix round 2/5 (DDD + shape addressed; 1 open — year-range exclusion hides 9-digit mobiles like '11 92024-2025'; commits 392d6357..b1605181)
Ruling R8: separator-only 8-digit landlines shaped like two years (20xx-20xx / 20xx-19xx) stay untokenized — year ranges after a 2-digit number are common in business text; such landlines are rare and the +55/parentheses forms still catch them — cost if wrong: a landline written "11 2024-2025" reaches the provider
Task 2: fix round 3/5 (1 addressed, 0 open; commits b1605181..0e737dc2)
Task 2: complete (commits 98bc118c..0e737dc2, review clean after 3 fix rounds)
Task 3: dispatched (BASE 0e737dc2)
Task 3: implemented b24e40b4 (bumped version to 19.0.1.1.0 inside unshipped branch)
Task 3: review 1 — Needs fixes: I1 write bypass lets group_erp_manager lower PII exposure; I2 (plan-mandated) prefix rules miss x_responsavel_cpf/x_cliente_email/x_telefone; A token rule narrower than brief; B pt_BR menu missing
Ruling R9: B pt_BR deferred to Task 9 (plan puts all translations there) — cost if wrong: none
Ruling R10: I2 — change plan's prefix rules to name-part matching (split on '_', strip x_/x_studio_) with pt-BR synonyms (telefone, celular, cep, nascimento, endereco/rua) — custom fields are the main "reflected after install" case and prefix matching leaks them — cost if wrong: some extra tokenized custom fields, overridable by admin
Ruling R11: fold minor "exposure or 'allow' fails open on NULL" into the fix (fall back to classify_field) — fail-closed matters for a leak gate — cost if wrong: none
Task 3: minor (deferred): cache not cleared on unlink/rename; other workers keep stale map after rename
Task 3: minor (deferred): BaseModel.write bypass skips other modules' ir.model.fields.write overrides; registry.clear_cache() too broad
Task 3: minor (deferred): tests miss hr.employee binary, -u through _reflect_fields
Task 3: fix round 1 implemented 13bcacb0 (I1, I2, A, R11 claimed fixed; 40 fields allow→tokenize, 8 false positives on non-text types)
Ruling R12: tokenize only applies to text-like/date types (char, text, html, date, datetime, selection? no — char/text/html/date/datetime only); other types classified 'tokenize' by name fall back to 'allow' — tokenizing ints/booleans is meaningless and hides config — cost if wrong: a numeric field holding a phone/CPF as integer would pass (detector layer still catches it in text)
Task 3: minor (deferred): rule changes after deploy need a recompute of stored ai_exposure_auto (post-migration) — not needed for first install
Task 3: fix round 1/5 (5 addressed, 1 open — create() accepts ai_exposure_override without system check; commits b24e40b4..fb2d9461)
Task 3: fix round 2/5 (1 addressed, 0 open; commits fb2d9461..74942f6e)
Task 3: complete (commits 0e737dc2..74942f6e, review clean after 2 fix rounds)
Task 4: dispatched (BASE 74942f6e)
Task 4: implemented c6c86c41
Task 4: review 1 — Needs fixes: I1 blocked data reachable via attachments (read_resource odoo://attachment, search_read ir.attachment/mail.message by res_model), relation paths (export_records bank_ids/acc_number, domain bank_ids.acc_number), Many2one display names of blocked comodels
Ruling R13: itbr_muk_ai_pii depends on muk_mcp_access (installed in prod) to reuse its path/attachment guards, which run even with an empty allowlist and call _resolve_model — cost if wrong: one more dependency for clients
Ruling R14: close ir.attachment / mail.message / mail.activity searches with a _mcp_record_domain override excluding blocked res_model — cost if wrong: AI cannot see attachments/messages of blocked records (intended)
Ruling R15: Many2one display names whose comodel is blocked are handled in Task 5 mask_rows (value False) — Task 5 owns serialization — cost if wrong: none
Task 4: minor (deferred): list_models test does not assert an absent-from-DB blocked name stays out
Ruling R16: from Task 5 on, tests run in DB=muk_ai_acc (module now depends on muk_mcp_access) — cost if wrong: none
Task 4: fix round 1/5 (3 addressed, 0 open; commits c6c86c41..cc714c74)
Task 4: minor (deferred, NOTABLE for final review): mail.tracking.value / mail.followers / mail.notification pointing at blocked records not filtered — tracking can hold old bank/payroll values
Task 4: minor (deferred): no tests for NULL-model rows, mail.activity, by-id read_records on blocked attachment/message
Task 4: complete (commits 74942f6e..cc714c74, review clean after 1 fix round)
Task 5: dispatched (BASE cc714c74)
Task 5: implemented f123ee2c (opus); implementer concerns: export leaks names/base64, group labels tokenize companies/team, contact_address allowed, portal users real names, _emit per-value cost; 5 muk_mcp tests fail by design (external email dropped)
Task 5: review 1 — Needs fixes: I1 name-copy fields (parent_name, mail.followers.name, record_name/res_name) real; I2 portal users' names real in res.users rows; I3 contact_address allow; I4 export drops tokenized fields in chat without privacy gain
Ruling R17: export_records — with session drop only 'block'; without session drop 'block'+'tokenize' — chat exports go to the user as attachments, the model reads them only via read_resource (confirmation in T8) — cost if wrong: an exported file with e-mails read back by the model after confirmation
Ruling R18: get_messages and call_method read-like methods (read, search_read, web_read, web_search_read, name_search, read_group) are masked in Task 5 (result serialization) — no other task owns them — cost if wrong: more scope in T5
Ruling R19: view/record context block display_name of person partners → NAME# belongs to Task 6 (provider boundary) — carry into T6 dispatch
Ruling R20: read_resource on a binary field classified 'block' is refused in Task 8 (documents) — carry into T8 dispatch
Ruling R21: fold minors login→EMAIL and place_of_birth kind into fix round 1 — cheap correctness
Ruling R22: manifest version bump once in Task 9 before publishing (user rule: bump before push/PR) — cost if wrong: none
Task 5: minor (deferred): grouping by partner name tokenizes companies/team too (README note)
Task 5: minor (deferred): _emit per distinct value is slow on large results (_emit_many later)
Task 5: minor (deferred): 5 upstream muk_mcp tests fail by design with this module installed (document in README)
Task 5: minor (deferred): show_address/formatted_display_name context can embed address in display_name
Task 5: fix round 1 implemented 32c6348e (I1-I3, R17, R18, R21; plus reclassify-on-update and tracking values)
Ruling R23 (corrects R15-era team rule): Many2one to res.users is tokenized when the target user is a portal/share user (share=True); internal users stay readable — the rule meant to protect team names, portal users are clients — cost if wrong: none
Task 5: fix round 1/5 (I1 partly, I2, I3, R17, R21, R23 addressed; 1 open — read_group alias 'x:array_agg(vat)' via call_method returns real data; commits f123ee2c..9378b279)
Ruling R24: fold into round 2 — mail.followers.display_name (computed from partner) and call_method web_read_group / web_save results; fail closed: an aggregate key that does not resolve to a field and holds a non-numeric value is dropped — cost if wrong: an exotic aggregate result disappears from the AI's view
Task 5: minor (deferred): record_name/res_name N small exists() queries per row
Task 5: minor (deferred): portal user whose partner is also an employee work contact gets inconsistent treatment
Task 5: fix round 2/5 (R24a, R24b addressed; 1 open — alias colliding with a groupby key or __count passes real values; commits 9378b279..b219568b)
Task 5: fix round 3/5 (1 addressed, 0 open; commits b219568b..36963240)
Task 5: minor (deferred): masker parsing duplicated from _itbr_pii_group_args (could call it)
Task 5: minor (deferred): alias '<groupby>_count' overwrites lazy count (tokenized, not leaked) — test only
Task 5: complete (commits cc714c74..36963240, review clean after 3 fix rounds)
Task 6: dispatched (BASE 36963240)
Task 6: implemented 02096e61 (concerns: muk_ai_chatter linked_record name and round notice escape the _build_request_inputs layer)
Ruling R25: the chat boundary moves to the output of _materialize_round_inputs (last step before the request; covers any extension of _build_request_inputs and the notice); _build_compact_inputs stays covered separately — cost if wrong: none
Task 6: minor (deferred): history re-tokenized every round (one upsert per distinct value per round)
Task 6: R25 applied 42eec143
Task 6: review 1 — Approved (0 Critical/Important on task; forward risk for T7)
Task 6: minor (deferred): dead identity check `masked is self.view_context` (Json returns deepcopy)
Task 6: minor (deferred, optional modules): muk_ai_chatter linked_record/thread_context names, muk_ai_decision llm.py sends record state untokenized — bridge needed if installed
Task 6: complete (commits 36963240..42eec143, review clean)
Ruling R26: Task 7 reveals tool arguments only for tools that run inside Odoo; tools that send data to third parties (generate_image, web_search, web_fetch, and any tool whose registry entry is not 'odoo'/muk_mcp) keep tokens — cost if wrong: an image prompt or search query keeps a token
Task 7: dispatched (BASE 42eec143)
Task 7: implemented fcf9effb (concerns: subagents/chatter/decide paths keep or leak tokens — optional modules; compaction summary shows tokens in UI)
Task 7: review 1 — Needs fixes: I1 tool outputs/errors echo revealed args back to provider (open_view domain, error strings); I2 tool_call_args_delta/reasoning_delta show tokens; I3 compact_update/compact_progress summaries show tokens
Ruling R27: replace R26 denylist with an allowlist by tool origin (muk_mcp core tools + muk_ai window/search/notification/ask tools); unknown tools keep tokens (fail closed) — cost if wrong: a legitimate new Odoo tool gets tokens until added
Ruling R28: fold minor test_stream_split_token forcing a flush between deltas — cheap test strength
Task 7: minor (deferred, optional modules): muk_ai_subagents _recent_messages leaks revealed events to lead provider; muk_ai_chatter/automation post tokenized last_text/tool_log; decide domain with tokens matches nothing
Task 7: fix round 1/5 (I2, R27, R28 addressed; open — regression: tokenized view_context exposed via _state_metrics/get_snapshot/bus/record read and breaks openPinnedContext; I1 residual: string-level mask misses double-encoded/case/format variants and over-masks short values/ids; I3 residual: compact_delta live deltas raw; commits fcf9effb..3dd69644)
Ruling R29: echo masking works on JSON structure when the output parses (string leaves only, case-insensitive, CPF/CNPJ/PHONE formatted variants too; ints never masked); string fallback otherwise (also masks the double-escaped form) — cost if wrong: an exotic echo format leaks a fragment
Task 7: minor (deferred): muk_mcp.log stores revealed args/errors (server-side, predates)
Task 7: minor (deferred): user-set list view_context domains only protected by the free-text detector
Task 7: minor (deferred): tool_load inline approval preview not revealed
Task 7: fix round 2/5 (REG, R29, I3r addressed, 0 open; commits 3dd69644..b8c109e7)
Task 7: minor (deferred): mask_tree skips dict keys — data-keyed outputs ({"Maria José": 1}) leak echoes
Task 7: minor (deferred): _state_metrics reveal lacks the _itbr_pii_reads_revealed() guard (call_method get_snapshot); call_method kwargs.context not stripped of muk_mcp_session_id
Task 7: minor (deferred): carry-over view_context domains with names reach provider (not a regression vs. pre-module)
Task 7: minor (deferred): _read_format one browse+_reveal per row
Task 7: complete (commits 42eec143..b8c109e7, review clean after 2 fix rounds)
Ruling R30: muk_ai.session, muk_ai.session.event and itbr.muk_ai.pii.token are always blocked for AI/MCP tools (in code, not only the parameter) — events and the token store hold real values — cost if wrong: the AI cannot inspect its own chats via tools (no product need)
Task 8: dispatched (BASE b8c109e7) with R20 + R30
Task 8: implemented e2665487 (R30+R20), 53f83306 (documents)
Task 8: review 1 — Needs fixes: I1 attachment approvals signed as ir.attachment (session approval covers all attachments); I2 R20 bypass via odoo://attachment/<id> with res_field of a block-exposed binary
Ruling R31: fold minor non-string uri guard and a negative signature test into fix round 1 — cheap correctness — cost if wrong: none
Task 8: minor (deferred): import json inside test body
Task 8: fix round 1/5 (3 addressed, 0 open; commits 53f83306..9e54fc24)
Task 8: complete (commits b8c109e7..9e54fc24, review clean after 1 fix round)
Ruling R32: final module version 19.0.1.0.0 (first release; earlier bumps were inside the unshipped branch, only test DBs had it) — cost if wrong: test DBs see a version downgrade (irrelevant)
Task 9: dispatched (BASE 9e54fc24)
Task 9: implemented 38670da2 (browser check not done; muk_ai_chatter mention leak documented; itbr_pii_enabled computed field + JS registry)
Task 9: review 1 — Approved; ServIAm brand concern verified false by controller (muk_ai pt_BR "MuK AI" → "ServIAm", 26 msgstr)
Task 9: minor (deferred): itbr_pii_enabled compute without depends_context/comment
Task 9: minor (deferred): README duplicates known-limits/key lines
Task 9: minor (deferred): browser check of the attachment notice not done (controller to do on the copy)
Task 9: complete (commits 9e54fc24..38670da2, review clean)
MERGE_BASE=c35a4430997a8870fa25b747ffb47f6c8a62fd55
PAUSE: Renan ends the day (Techmobi migration). Final review running; no fix wave until resumed. Brain RETOMADA updated locally (no commit).
Final review: With fixes — 2 Critical, 9 Important; list in final-review-findings.md; fix wave pending (paused)
