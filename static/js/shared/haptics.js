/**
 * Retours haptiques (vibrations) partagés par toute l'app — window.haptics
 *
 * Principe : vibrer seulement quand ça apporte une information, jamais "pour décorer".
 *   - selection : changer d'onglet / d'option (tic très léger)
 *   - light     : ouvrir / valider une action courante
 *   - medium    : action destructive (supprimer)
 *   - success   : une action a abouti (ordre ajouté, import confirmé…)
 *   - warning   : action bloquée (fonction Premium verrouillée)
 *   - error     : échec (erreur serveur, identifiants invalides…)
 *   - tick      : défilement de valeurs (glisser sur un graphique), limité en fréquence
 *
 * Plateformes :
 *   - Android / Chrome : Vibration API (navigator.vibrate)
 *   - iOS 18+ Safari   : pas de Vibration API ; un clic sur un <input type="checkbox" switch>
 *                        déclenche le retour haptique système (un "tap" par impulsion)
 *   - Souris / desktop : aucune vibration
 *
 * Désactivable par l'utilisateur (Paramètres → Vibrations), stocké dans localStorage.
 * Debug console : window.debug.haptics()
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'hapticsEnabled';
    const canVibrate = typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';
    const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

    // Motifs Android (ms) et nombre de "taps" équivalents sur iOS
    const PATTERNS = {
        selection: { vibrate: 8, ios: [0], priority: 1 },
        tick:      { vibrate: 6, ios: [0], priority: 0 },
        light:     { vibrate: 12, ios: [0], priority: 2 },
        medium:    { vibrate: 22, ios: [0], priority: 3 },
        success:   { vibrate: [12, 70, 28], ios: [0, 110], priority: 4 },
        warning:   { vibrate: [24, 90, 24], ios: [0, 140], priority: 4 },
        error:     { vibrate: [35, 60, 35, 60, 35], ios: [0, 100, 200], priority: 5 },
    };

    let lastPointerType = null;
    let lastPulseAt = 0;
    let lastPriority = -1;
    let iosLabel = null;
    const stats = { fired: 0, skipped: 0, last: null };

    function isEnabled() {
        try {
            return localStorage.getItem(STORAGE_KEY) !== 'false';
        } catch (e) {
            return true;
        }
    }

    function setEnabled(value) {
        try {
            localStorage.setItem(STORAGE_KEY, value ? 'true' : 'false');
        } catch (e) {
        }
        if (value) pulse('success', { force: true });
    }

    // Appareil tactile ? (dernier pointeur utilisé, sinon capacité de l'écran)
    function isTouchContext() {
        if (lastPointerType) return lastPointerType !== 'mouse';
        try {
            return window.matchMedia('(pointer: coarse)').matches;
        } catch (e) {
            return false;
        }
    }

    function iosTap() {
        try {
            if (!iosLabel) {
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.setAttribute('switch', '');
                input.id = 'hapticsIosSwitch';
                input.tabIndex = -1;
                input.setAttribute('aria-hidden', 'true');
                const hidden = 'position:fixed;opacity:0;pointer-events:none;width:1px;height:1px;left:-10px;top:0;';
                input.style.cssText = hidden;
                iosLabel = document.createElement('label');
                iosLabel.htmlFor = input.id;
                iosLabel.style.cssText = hidden;
                iosLabel.setAttribute('aria-hidden', 'true');
                document.body.append(input, iosLabel);
            }
            iosLabel.click();
        } catch (e) {
        }
    }

    /**
     * Déclenche un retour haptique.
     * Anti-rafale : dans une fenêtre de 120 ms, seul un retour plus important passe
     * (ex. le "tap" du bouton puis le "succès" de l'action → seul le succès est ressenti en plus).
     */
    function pulse(kind, opts = {}) {
        const p = PATTERNS[kind];
        if (!p) return false;
        if (!opts.force && (!isEnabled() || !isTouchContext())) {
            stats.skipped++;
            return false;
        }

        const now = performance.now();
        if (kind === 'tick') {
            if (now - lastPulseAt < 40) { stats.skipped++; return false; }
        } else if (now - lastPulseAt < 120 && p.priority <= lastPriority) {
            stats.skipped++;
            return false;
        }
        lastPulseAt = now;
        lastPriority = p.priority;

        if (canVibrate && !isIOS) {
            try { navigator.vibrate(p.vibrate); } catch (e) {}
        } else if (isIOS) {
            p.ios.forEach(delay => delay ? setTimeout(iosTap, delay) : iosTap());
        } else {
            stats.skipped++;
            return false;
        }
        stats.fired++;
        stats.last = kind;
        return true;
    }

    // ---- Retours automatiques par délégation (aucun code à ajouter dans les pages) ----
    // Ordre = priorité : la première règle qui correspond à l'élément cliqué gagne.
    const AUTO_RULES = [
        ['[data-haptic]', el => el.getAttribute('data-haptic')],
        ['.locked, .kpi-value-lock, [data-locked="true"]', () => 'warning'],
        ['.btn-danger, .settings-action-btn.danger', () => 'medium'],
        ['.tab-bar-item', () => 'selection'],
        ['.period-btn, .tab-btn, .settings-radio-option, .details-toggle', () => 'selection'],
        ['input[type="checkbox"], input[type="radio"], select', () => 'selection'],
        ['.portfolio-row, .user-avatar', () => 'light'],
        ['.btn-primary, button[type="submit"], .cta-button', () => 'light'],
    ];

    document.addEventListener('pointerdown', e => {
        lastPointerType = e.pointerType || null;
    }, { capture: true, passive: true });

    document.addEventListener('click', e => {
        const target = e.target instanceof Element ? e.target : null;
        if (!target || target.closest('#hapticsIosSwitch, label[for="hapticsIosSwitch"]')) return;
        for (const [selector, kindOf] of AUTO_RULES) {
            const el = target.closest(selector);
            if (el) {
                if (el.disabled) return;
                const kind = kindOf(el);
                if (kind && kind !== 'none') pulse(kind);
                return;
            }
        }
    }, { capture: true, passive: true });

    // ---- Notifications : un succès / une erreur affiché(e) se ressent aussi ----
    const MESSAGE_KINDS = { success: 'success', error: 'error', warning: 'warning', danger: 'error' };

    function wrapGlobal(name, before) {
        const original = window[name];
        if (typeof original !== 'function' || original.__haptics) return;
        const wrapped = function (...args) {
            try { before(...args); } catch (e) {}
            return original.apply(this, args);
        };
        wrapped.__haptics = true;
        window[name] = wrapped;
    }

    function installWrappers() {
        // showMessage(message, type) : utils.js partagé + login/register
        wrapGlobal('showMessage', (message, type) => {
            const kind = MESSAGE_KINDS[type];
            if (kind) pulse(kind);
        });
        // Modale Premium (fonction verrouillée)
        wrapGlobal('openPremiumModal', () => pulse('warning'));
    }

    if (document.readyState === 'complete') {
        installWrappers();
    } else {
        window.addEventListener('load', installWrappers);
    }

    window.haptics = {
        selection: () => pulse('selection'),
        light: () => pulse('light'),
        medium: () => pulse('medium'),
        success: () => pulse('success'),
        warning: () => pulse('warning'),
        error: () => pulse('error'),
        tick: () => pulse('tick'),
        pulse,
        isEnabled,
        setEnabled,
        get supported() { return canVibrate || isIOS; },
    };

    window.debug = window.debug || {};
    window.debug.haptics = () => ({
        enabled: isEnabled(),
        supported: canVibrate || isIOS,
        platform: isIOS ? 'ios-switch' : (canVibrate ? 'vibration-api' : 'none'),
        lastPointerType,
        touchContext: isTouchContext(),
        ...stats,
    });
})();
