/**
 * Caches locaux des données du portefeuille (sessionStorage), partagés par toutes les pages.
 *
 * La page Portefeuille affiche immédiatement les dernières données connues puis les rafraîchit
 * ("stale-while-revalidate"). Toute modification des ordres DOIT appeler
 * window.invalidatePortfolioCaches() pour que l'écran suivant ne montre pas de chiffres périmés.
 */
(function () {
    'use strict';

    const PREFIXES = ['portfolioSummary_', 'portfolioChartData_'];

    window.invalidatePortfolioCaches = function () {
        try {
            Object.keys(sessionStorage)
                .filter(key => PREFIXES.some(prefix => key.startsWith(prefix)))
                .forEach(key => sessionStorage.removeItem(key));
        } catch (e) {
        }
    };

    window.debug = window.debug || {};
    window.debug.appCache = () => {
        try {
            return Object.keys(sessionStorage)
                .filter(key => PREFIXES.some(prefix => key.startsWith(prefix)))
                .map(key => {
                    const { timestamp } = JSON.parse(sessionStorage.getItem(key)) || {};
                    return { key, ageSec: timestamp ? Math.round((Date.now() - timestamp) / 1000) : null };
                });
        } catch (e) {
            return [];
        }
    };
})();
