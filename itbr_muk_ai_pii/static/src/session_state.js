import { registry } from '@web/core/registry';

// The server tells whether personal data is masked in this chat, so the
// composer can warn that attachments are not.
registry.category('muk_ai.session_state_fields').add('itbr_muk_ai_pii.enabled', {
    field: 'itbr_pii_enabled',
    apply: (state, record) => {
        state.itbrPiiEnabled = !!record.itbr_pii_enabled;
    },
});
