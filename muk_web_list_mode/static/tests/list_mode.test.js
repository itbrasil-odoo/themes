import { expect, test } from '@odoo/hoot';

import { models, fields, defineModels, mountView, onRpc } from '@web/../tests/web_test_helpers';

class Product extends models.Model {
    name = fields.Char();
    _records = [
        { id: 1, name: 'Test 1' },
        { id: 2, name: 'Test 2' },
    ];
}

defineModels({ Product });

onRpc('has_group', () => true);

test(
    'renders mode switch in list view', 
    async () => {
        await mountView({
            type: 'list',
            resModel: 'product',
            arch: '<list><field name="name"/></list>',
        });
        expect('.mk_mode_switch').toHaveCount(1);
    }
);
