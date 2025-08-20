import { patch } from "@web/core/utils/patch";

import { Attachment } from "@mail/core/common/attachment_model";

patch(Attachment.prototype, {
    get isDeletable() {
        if (this.disableDeletable) {
            return false;
        }
        return super.isDeletable;
    },
});
