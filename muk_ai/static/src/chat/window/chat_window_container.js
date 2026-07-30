import { Component, useEffect, useState } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';
import { dockWidth } from '@muk_ai/chat/window/chat_window_service';

/** Root container rendering all open chat windows from the chat-window service. */
export class ChatWindowContainer extends Component {
    static template = 'muk_ai.ChatWindowContainer';
    static components = { ChatWindow };
    static props = {};
    setup() {
        this.cw = useService('muk_ai.chat_window');
        this.state = useState(this.cw.state);
        this.mailStore = useService('mail.store');
        useEffect(
            () => this.remeasureDiscuss(),
            () => [this.state.windows.length],
        );
    }
    /**
     * Ask Discuss to trim its open row to what still fits beside the dock.
     * It only does so when its own state changes, so a window opening or
     * closing here would otherwise leave windows stranded underneath us.
     */
    remeasureDiscuss() {
        this.mailStore.chatHub.onRecompute();
    }
    /**
     * Measure the corner both docks share, so this one can sit beside Discuss
     * instead of on top of it. Read from Discuss's own layout constants and
     * mirror what its template renders: nothing at all until a conversation
     * exists, bubbles only while it is collapsed, and one slot per open
     * window otherwise.
     * @returns {number} reserved width in pixels
     */
    get discussReservedWidth() {
        const hub = this.mailStore.chatHub;
        if (!hub.opened.length && !hub.folded.length) {
            return 0;
        }
        const bubbles = hub.BUBBLE_START + hub.BUBBLE + hub.BUBBLE_OUTER * 2;
        if (hub.compact) {
            return bubbles;
        }
        return bubbles + hub.opened.length * (hub.WINDOW + hub.WINDOW_INBETWEEN * 2);
    }
    get dockWidth() {
        return dockWidth(this.state.windows.length);
    }
}

registry.category('main_components').add('muk_ai.ChatWindowContainer', {
    Component: ChatWindowContainer,
});
