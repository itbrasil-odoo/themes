import { describe, expect, test } from '@odoo/hoot';
import {
    defineModels,
    fields,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/fields/effort_picker/effort_picker';

describe.current.tags('muk_ai');
defineMailModels();

const ARCH = `
    <form>
        <field name="effort_options" invisible="1"/>
        <field name="effort" widget="effort_picker"
               options="{'options_field': 'effort_options'}"/>
    </form>`;

class MukAiEffortModel extends models.Model {
    _name = 'muk_ai.effort_model';
    effort = fields.Selection({
        selection: [
            ['minimal', 'Minimal'],
            ['low', 'Low'],
            ['medium', 'Medium'],
            ['high', 'High'],
            ['xhigh', 'Extra High'],
            ['max', 'Maximum'],
        ],
    });
    effort_options = fields.Json();
    _records = [
        { id: 1, effort: 'low', effort_options: ['low', 'high'] },
        { id: 2, effort: false, effort_options: false },
    ];
}
defineModels([MukAiEffortModel]);

/**
 * Return the selectable effort labels, dropping the empty placeholder option.
 * @returns {string[]} labels in render order
 */
function effortChoices() {
    const options = document.querySelectorAll(
        '.o_field_widget[name="effort"] select option',
    );
    return [...options]
        .filter((el) => el.value !== 'false')
        .map((el) => el.textContent.trim());
}

test('EffortPickerField limits choices to the supported options', async () => {
    await mountView({
        resModel: 'muk_ai.effort_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    expect(effortChoices()).toEqual(['Low', 'High']);
});

test('EffortPickerField falls back to every choice without options', async () => {
    await mountView({
        resModel: 'muk_ai.effort_model',
        resId: 2,
        type: 'form',
        arch: ARCH,
    });
    expect(effortChoices().length).toBe(6);
});
