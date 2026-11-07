import contextvars
import json
import re

from odoo import models

from odoo.addons.muk_ai.tools.context import with_ui_ctx
from odoo.addons.muk_mcp.core.registry import MIXIN
from odoo.addons.muk_mcp.core.tool import get_tool_index

from ..tools.detector import tokenize_text
from ..tools.keys import TOKEN_RE
from ..tools.records import PARTNER, USERS, Masker

PARAM_EMAIL_DOMAINS = 'itbr_muk_ai_pii.email_domains'
TEXT_BLOCKS = frozenset({'input_text', 'output_text'})

# Where the tools whose arguments are revealed are declared (R27): the Odoo
# data tools of muk_mcp and muk_ai's own screen tools. Every other tool
# (generate_image, web_search, web_fetch, another AI model, a remote or
# database-defined tool, ``tool_load`` whose inline call is dispatched on its
# own) keeps the tokens.
ODOO_TOOL_ORIGINS = (
    'odoo.addons.muk_mcp.mcp.',
    'odoo.addons.muk_ai.mcp.window',
    'odoo.addons.muk_ai.mcp.search',
    'odoo.addons.muk_ai.mcp.notification',
    'odoo.addons.muk_ai.mcp.agent',
)
MCP_TOOL_ATTR = '__mcp_tool__'

TOKEN_KINDS = ('CPF', 'CNPJ', 'EMAIL', 'PHONE', 'NAME', 'ADDR', 'DATE', 'DOC')
# A trailing fragment that may grow into a token with the next delta: a token
# kind (or the start of one) and up to 11 hex digits after the ``#``.
_KIND_PREFIXES = sorted(
    {kind[:i] for kind in TOKEN_KINDS for i in range(1, len(kind) + 1)}, key=len, reverse=True
)
TOKEN_TAIL_RE = re.compile(
    r'(?<!\w)(?:(?:%s)#[0-9a-f]{0,11}|%s)$'
    % ('|'.join(TOKEN_KINDS), '|'.join(_KIND_PREFIXES))
)
TAIL_KEY = 'itbr_pii_tail'
STREAM_KEYS = ('text', 'reasoning')
TOOL_ARGS_PREFIX = 'tool_args_'
# Events shown as they come from the provider, outside ``_append_event``.
REVEALED_PUBLISHES = frozenset({'compact_update', 'view_context'})

# ``{real value: token}`` of the tool call being dispatched, so its echoes are
# masked again, in the output and in the view context it pins.
_DISPATCH_MASK = contextvars.ContextVar('itbr_pii_dispatch_mask', default=None)


def _tail_key(content_key):
    return TAIL_KEY if content_key == 'text' else f'{TAIL_KEY}:{content_key}'


def _streams_revealed(content_key):
    return content_key in STREAM_KEYS or (
        content_key.startswith(TOOL_ARGS_PREFIX) and not content_key.endswith('_last')
    )


def _mask_patterns(mask):
    """Return ``(pattern, token)`` pairs, longest value first.

    A value is matched as a whole word, raw and as JSON escapes it.
    """
    pairs = []
    for value in sorted(mask, key=len, reverse=True):
        for form in {value, json.dumps(value)[1:-1]}:
            pairs.append((re.compile(r'(?<!\w)%s(?!\w)' % re.escape(form)), mask[value]))
    return pairs


def _mask_any(data, pairs):
    if isinstance(data, str):
        for pattern, token in pairs:
            data = pattern.sub(token, data)
        return data
    if isinstance(data, dict):
        return {k: _mask_any(v, pairs) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_mask_any(v, pairs) for v in data]
    return data


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

    def _materialize_round_inputs(self, provider, cache, notice=None):
        """Tokenize the round inputs as they leave for the provider (R25).

        Done on the final list, so items any module adds in
        ``_build_request_inputs`` and the round ``notice`` are covered too.
        Only text is touched: materialized attachment blocks pass as they are.
        """
        inputs = super()._materialize_round_inputs(provider, cache, notice=notice)
        if not self._itbr_pii_on():
            return inputs
        return self._itbr_pii_items(self._itbr_pii_mask_ui_ctx(inputs))

    def _build_compact_inputs(self, prefix):
        return self._itbr_pii_items(super()._build_compact_inputs(prefix))

    # -- return path: users and Odoo see the real values ------------------
    def _itbr_pii_reveal(self, data):
        """Return ``data`` with the tokens of this chat swapped for their values.

        Runs whether tokens are on or off: a chat keeps the tokens it already
        holds after they are switched off. Without a token it is a no-op that
        never reaches the database.
        """
        if not self.id:
            return data
        return self.env['itbr.muk_ai.pii.token']._reveal_any(data, self.sudo())

    def _itbr_pii_tool_origin(self, name):
        """Return the Python module that declares chat tool ``name``, or ``None``."""
        entry = get_tool_index(self.env, registry='odoo').get(name)
        if not entry or entry.get('kind') != 'method':
            return None
        for klass in type(self.env[MIXIN]).mro():
            func = vars(klass).get(entry['method'])
            if func is not None and getattr(func, MCP_TOOL_ATTR, None):
                return klass.__module__
        return None

    def _itbr_pii_reveals_args(self, name, arguments):
        """Whether the arguments of tool ``name`` run inside Odoo (R26, R27)."""
        if not self.id or not TOKEN_RE.search(json.dumps(arguments, default=str)):
            return False
        origin = self._itbr_pii_tool_origin(name) or ''
        return origin.startswith(ODOO_TOOL_ORIGINS)

    def _itbr_pii_mask_of(self, arguments):
        """Return ``{value: token}`` for the tokens of ``arguments`` this chat reveals."""
        tokens = sorted({m.group(0) for m in TOKEN_RE.finditer(json.dumps(arguments, default=str))})
        # NUL never occurs in a stored value (PostgreSQL text refuses it)
        values = self._itbr_pii_reveal('\x00'.join(tokens)).split('\x00')
        return {
            value: token
            for token, value in zip(tokens, values, strict=True)
            if value != token and value
        }

    def _append_event(self, entry):
        """Events are what users see: store and broadcast them with real values."""
        return super()._append_event(self._itbr_pii_reveal(entry))

    def _publish_event(self, event_type, payload):
        """Show the payloads published outside ``_append_event`` with real values.

        Compaction progress and the pinned view context are stored with tokens.
        """
        if event_type in REVEALED_PUBLISHES:
            payload = self._itbr_pii_reveal(payload)
        return super()._publish_event(event_type, payload)

    def fetch_events(self, limit=100, before_sequence=None):
        """Show stored events with real values, compaction summaries included."""
        window = super().fetch_events(limit=limit, before_sequence=before_sequence)
        if window.get('events'):
            window = {**window, 'events': self._itbr_pii_reveal(window['events'])}
        return window

    def _dispatch_tool_call(self, name, arguments, call_id):
        """Run Odoo tools with real values and hand their echoes back as tokens.

        A tool may echo its arguments (``open_view`` returns its domain, an
        error quotes a value): the values revealed for the call are masked
        again in the output, which goes to the provider.
        """
        if not self._itbr_pii_reveals_args(name, arguments):
            return super()._dispatch_tool_call(name, arguments, call_id)
        mask = self._itbr_pii_mask_of(arguments)
        if not mask:
            return super()._dispatch_tool_call(name, arguments, call_id)
        pairs = _mask_patterns(mask)
        reset = _DISPATCH_MASK.set(pairs)
        try:
            output, ok = super()._dispatch_tool_call(
                name, self._itbr_pii_reveal(arguments), call_id
            )
        finally:
            _DISPATCH_MASK.reset(reset)
        return _mask_any(output, pairs), ok

    def _view_context_from_action(self, tool_name, action):
        """The view context a tool pins goes to the provider: keep its tokens."""
        payload = super()._view_context_from_action(tool_name, action)
        if payload and (pairs := _DISPATCH_MASK.get()):
            payload = _mask_any(payload, pairs)
        return payload

    def _enter_waiting_approval(self, call, tool_calls, outputs, index, has_terminating, gate):
        """Preview and later dispatch the paused call with real values.

        The other calls of the round keep their tokens: each one is revealed,
        or not, on its own dispatch.
        """
        if self._itbr_pii_reveals_args(call.get('name'), call.get('arguments')):
            call = {**call, 'arguments': self._itbr_pii_reveal(call['arguments'])}
        super()._enter_waiting_approval(call, tool_calls, outputs, index, has_terminating, gate)
        pending = self.pending_ask
        if isinstance(pending, dict) and pending.get('kind') == 'approval':
            revealed = self._itbr_pii_reveal(pending.get('preview'))
            if revealed != pending.get('preview'):
                self.pending_ask = {**pending, 'preview': revealed}

    def _public_pending_ask(self, pending=None):
        return self._itbr_pii_reveal(super()._public_pending_ask(pending))

    def get_snapshot(self, include_conversation=False):
        """Show the conversation and last message with real values.

        The stored fields keep the tokens: they are what the provider reads.
        """
        snapshot = super().get_snapshot(include_conversation=include_conversation)
        for key in ('conversation', 'last_text'):
            if snapshot.get(key):
                snapshot[key] = self._itbr_pii_reveal(snapshot[key])
        return snapshot

    # -- streaming --------------------------------------------------------
    def _coalesce_and_emit(
        self, buffer_state, content_key, last_key, delta, event_type, extra=None
    ):
        """Stream text, reasoning and tool arguments with real values.

        A trailing fragment that may be the start of a token is held back
        until the next delta completes it, or the stream is flushed.
        """
        if _streams_revealed(content_key):
            tail_key = _tail_key(content_key)
            text = buffer_state.pop(tail_key, '') + (delta or '')
            if match := TOKEN_TAIL_RE.search(text):
                buffer_state[tail_key] = match.group(0)
                text = text[: match.start()]
            delta = self._itbr_pii_reveal(text)
            if not delta:
                return None
        return super()._coalesce_and_emit(
            buffer_state, content_key, last_key, delta, event_type, extra=extra
        )

    def _itbr_pii_release_tail(self, buffer_state, content_key):
        if tail := buffer_state.pop(_tail_key(content_key), ''):
            buffer_state[content_key] = buffer_state.get(content_key, '') + self._itbr_pii_reveal(
                tail
            )

    def _flush_text_buffer(self, buffer_state):
        """Release the held-back tail before the buffer goes out."""
        self._itbr_pii_release_tail(buffer_state, 'text')
        return super()._flush_text_buffer(buffer_state)

    def _flush_stream_buffer(self, buffer_state):
        """Release every held-back tail before the buffers go out."""
        prefix = f'{TAIL_KEY}:'
        for key in [k for k in buffer_state if isinstance(k, str) and k.startswith(prefix)]:
            self._itbr_pii_release_tail(buffer_state, key[len(prefix):])
        return super()._flush_stream_buffer(buffer_state)
