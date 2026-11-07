from odoo import models

from odoo.addons.muk_ai.tools.context import with_ui_ctx

from ..tools.detector import tokenize_text
from ..tools.records import PARTNER, USERS, Masker

PARAM_EMAIL_DOMAINS = 'itbr_muk_ai_pii.email_domains'
TEXT_BLOCKS = frozenset({'input_text', 'output_text'})


class MukAiSession(models.Model):
    _inherit = 'muk_ai.session'

    def _tool_dispatch_context(self):
        """Tell tool results which chat they go to, so they can be tokenized for it."""
        return {**super()._tool_dispatch_context(), 'itbr_pii_session_id': self.id}

    # -- provider boundary ----------------------------------------------
    def _itbr_pii_email_domains(self):
        value = self.env['ir.config_parameter'].sudo().get_param(PARAM_EMAIL_DOMAINS) or ''
        return frozenset(d.strip().lower() for d in value.split(',') if d.strip())

    def _itbr_pii_emitter(self):
        """Return ``(emit, email_domains)`` for one request, tokens cached per value."""
        session = self.sudo()
        store = self.env['itbr.muk_ai.pii.token']
        cache = {}

        def emit(kind, value):
            if (kind, value) not in cache:
                cache[kind, value] = store._emit(kind, value, session)
            return cache[kind, value]

        return emit, self._itbr_pii_email_domains()

    def _itbr_pii_tokenize(self, text, emitter=None):
        """Return ``text`` with its documents, e-mails and phones as tokens of this chat."""
        if not isinstance(text, str) or not text or not self._itbr_pii_on():
            return text
        emit, domains = emitter or self._itbr_pii_emitter()
        return tokenize_text(text, emit, domains)

    def _itbr_pii_on(self):
        return bool(self.id) and self.env['itbr.muk_ai.pii.token']._enabled()

    def _itbr_pii_item(self, item, emitter):
        """Return a tokenized copy of one input item; the original is left untouched.

        ``function_call`` arguments are written by the model and stay as they are.
        """
        if not isinstance(item, dict):
            return item
        copied = dict(item)
        if item.get('type') == 'function_call_output' and isinstance(item.get('output'), str):
            copied['output'] = self._itbr_pii_tokenize(item['output'], emitter)
        content = item.get('content')
        if isinstance(content, str):
            copied['content'] = self._itbr_pii_tokenize(content, emitter)
        elif isinstance(content, list):
            copied['content'] = [
                {**block, 'text': self._itbr_pii_tokenize(block['text'], emitter)}
                if isinstance(block, dict) and block.get('type') in TEXT_BLOCKS
                and isinstance(block.get('text'), str)
                else block
                for block in content
            ]
        return copied

    def _itbr_pii_items(self, items):
        if not self._itbr_pii_on():
            return items
        emitter = self._itbr_pii_emitter()
        return [self._itbr_pii_item(item, emitter) for item in items]

    def _itbr_pii_view_context(self):
        """The view context with the open person's name as a ``NAME#`` token (R19).

        The stored ``view_context`` keeps the real name: the user sees it.
        """
        payload = self.view_context
        if not (isinstance(payload, dict) and payload.get('kind') == 'record'):
            return payload
        model, res_id, name = payload.get('model'), payload.get('id'), payload.get('display_name')
        if model not in (PARTNER, USERS) or not isinstance(res_id, int) or not name:
            return payload
        masker = Masker(self.env, self.sudo())
        masked = masker.is_client_user(res_id) if model == USERS else masker.is_person(res_id)
        if not masked or str(name) == str(res_id):
            return payload
        return {**payload, 'display_name': masker.emit('NAME', name)}

    def _itbr_pii_mask_ui_ctx(self, inputs):
        """Swap the ui_ctx message of the open record for its masked version."""
        masked = self._itbr_pii_view_context()
        if masked is self.view_context:
            return inputs
        kinds = self._view_kinds()
        [real] = with_ui_ctx([], self.view_context, kinds) or [None]
        [safe] = with_ui_ctx([], masked, kinds) or [None]
        if real is None or safe is None:
            return inputs
        return [safe if item == real else item for item in inputs]

    def _build_request_inputs(self):
        inputs = super()._build_request_inputs()
        if not self._itbr_pii_on():
            return inputs
        return self._itbr_pii_items(self._itbr_pii_mask_ui_ctx(inputs))

    def _build_compact_inputs(self, prefix):
        return self._itbr_pii_items(super()._build_compact_inputs(prefix))
