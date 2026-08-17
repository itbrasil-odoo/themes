import publicWidget from '@web/legacy/js/public/public_widget';
import '@website/snippets/s_popup/000';

import { MEDIAS_BREAKPOINTS, SIZES } from '@web/core/ui/ui_service';
import { renderToElement } from '@web/core/utils/render';

publicWidget.registry.CookiesApproval.include({
    /**
     * Render the placeholder with the service the blocked element belongs to.
     *
     * The server stamps which service was stripped and which purpose would
     * release it, so the placeholder can name the provider instead of asking
     * for "optional cookies" in the abstract.
     *
     * Containers are watchlisted by class alone, whatever per-service consent
     * says, so an untouched src is the proof that nothing was blocked and the
     * embed must be left alone. The dataset is merged because a wrapped video
     * carries the flag on its container but the stamps on the iframe.
     *
     * @override
     */
    _addOptionalCookiesWarning() {
        if (!this.iframeEl.dataset.nocookieSrc) {
            return;
        }
        const data = { ...this.el.dataset, ...this.iframeEl.dataset };
        this.optionalCookiesWarningEl = renderToElement('website.cookiesWarning', {
            extraStyle: this.iframeEl.parentElement.classList.contains(
                'media_iframe_video',
            )
                ? `aspect-ratio: 16/9; max-width: ${
                      MEDIAS_BREAKPOINTS[SIZES.SM].maxWidth
                  }px;`
                : '',
            extraClasses:
                getComputedStyle(this.iframeEl.parentElement).position === 'absolute'
                    ? ''
                    : 'my-3',
            serviceName: data.mukCookieService || '',
            serviceLabel: data.mukCookieLabel || '',
            categoryCode: data.mukCookieCategory || '',
            placeholderText: data.mukCookiePlaceholder || '',
        });
        this.iframeEl.insertAdjacentElement('afterend', this.optionalCookiesWarningEl);
        this.iframeEl.classList.add('d-none');
        this._onRemoveOptionalCookiesWarning =
            this._removeOptionalCookiesWarning.bind(this);
        document.addEventListener(
            'optionalCookiesAccepted',
            this._onRemoveOptionalCookiesWarning,
            { once: true },
        );
    },
});
