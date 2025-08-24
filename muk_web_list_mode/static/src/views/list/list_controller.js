
import { patch } from '@web/core/utils/patch';
import { _t } from '@web/core/l10n/translation';

import { ListController } from '@web/views/list/list_controller';

patch(ListController.prototype, {
    get display() {
        const res = super.display;
        if (!this.props.readonly && this.activeActions.edit && res.controlPanel) {
            const initialEditable = this.editable || 'bottom';
            const initialMultiEdit =  this.archInfo.multiEdit || false;
            const modeEntries = [
                { mode: 'read', name: _t('Open Form View'), icon: 'fa fa-external-link' },
                { mode: 'edit',  name: _t('Inline Edit Mode'), icon: 'fa fa-pencil' },
            ]
            const setMode = (mode) => {
                this.editable = (
                    mode === 'edit' ? initialEditable : false
                );
                this.model.multiEdit = (
                    mode === 'edit' ? true : initialMultiEdit
                );
                this.model.notify();
            };
            res.controlPanel.modeSwitch = {
                currentMode: modeEntries.find((e) => (
                    e.mode === (this.editable ? 'edit' : 'read')
                )),
                modeSwitcherEntries: modeEntries.map((entry) => ({
                    ...entry,
                    onSelected: () => setMode(entry.mode),
                })),
            };
        }
        return res;
    }
});


