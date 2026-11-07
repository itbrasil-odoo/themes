# Final review (c35a4430..38670da2) — verdict: With fixes. Module suite 159/159 green on muk_ai_acc.
Fix wave NOT started (paused 2026-11-07, Renan ends the day). Dispatch ONE fix subagent with this list, then one scoped re-review.

## Critical
1. Payroll via hr.employee _inherits hr.version: inherited fields judged by name only; contract_wage, hourly_wage, contract_date_start/end, contract_type_id come out 'allow'. Fix: level() returns block when field.related/inherited passes through a blocked comodel; match wage/salary as name parts; test on hr.employee (records.py:103-108, ir_model_fields.py:12-15).
2. After approval, tool output goes to provider unmasked: _enter_waiting_approval stores REVEALED args in pending_ask; resume dispatches real values; no token → no echo mask. With guard approve_all_writes (prod default) every write echoes names. Fix: keep tokenized args in pending_ask, reveal only the preview (or store the mask in pending_ask); test approving create_records and assert provider input has no name (muk_ai_session.py:273-310).

## Important
3. Screen context of blocked models (res.partner.bank display = acc_number, hr.payslip) sent in ui_ctx: drop/reduce when view_context.model is blocked (muk_ai_session.py:140-167).
4. Client re-pins real domain via set_view_context after open_view: mask domain leaves of list/pivot/graph contexts by field exposure + person names at the boundary (muk_ai_session.py:295-300). One function _itbr_pii_mask_ui_ctx should own screen→provider.
5. call_method export_data / copy_data / onchange / default_get return unmasked: refuse export_data/copy_data via call_method (point to export_records) or mask (muk_mcp_mixin.py:19-23,153-159).
6. Search by token fails: store keeps NORMALIZED value (vat digits only) but records store formatted (123.456.789-09); hash normalized, store/reveal raw first-seen value; end-to-end search_read test without stub (records.py:134-139, pii_token.py:31-52).
7. R30 blocks the chat's own attachments (uploads, exports, report PDFs on muk_ai.session): allow attachments with res_model muk_ai.session and res_id in the current chat tree (muk_mcp_mixin.py:13-15,58-60).
8. Token rows kept forever (LGPD retention): @api.autovacuum deleting tokens with no session_ids (pii_token.py).
9. mail.tracking.value / mail.followers / mail.notification of blocked records not filtered (muk_mcp_mixin.py:81-93).
10. Strip show_address/show_email/show_vat/formatted_display_name from tool context when a session is active (muk_mcp_tool.py:12-22).
11. Performance: _emit per distinct value (flush+insert+invalidate); _reveal per leaf walks tree → batch _emit_many and one-query reveal.

## Minor (can wait unless cheap)
- keyless-but-enabled: log warning; consider dropping tokenized fields.
- print_report pause may protect nothing in chat (_persist_tool_file strips base64) — ask Renan if 6c stays.
- _assess_risk should return None for documents of blocked targets (avoid asking then failing).
- token table: group_system read ACL — make all-zero.
- refuse Odoo-tool dispatch when an unrevealable token remains (would be written to business data).
- approval audit stores tokens for auto_approved rows.
- alphanumeric CNPJ in detector (issued since 07/2026).
- uninstall leaves tokens in old chats (document).
- cache tool origin by name.
- reuse _itbr_pii_group_args in masker (string groupby yields chars).
Must-fix from deferred ledger: T4 tracking (item 9), T5 show_address (item 10), T7 carry-over domains (item 4), T9 browser check.
