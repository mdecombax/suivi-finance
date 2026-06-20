/* =====================================================================
   Refonte « Cahier d'école » — comportements JS
   - Polices manuscrites par défaut pour Chart.js
   - Graphique d'évolution redessiné « à la main » (rough.js)
   - Animation d'écriture : le trait se dessine de gauche à droite
   Chargé en defer : Chart.js et rough.js (scripts normaux) sont déjà prêts.
   ===================================================================== */
(function () {
    'use strict';

    if (typeof Chart === 'undefined') return; // page sans graphique

    var INK_BLUE = '#27408b';
    var PENCIL = '#8a8f98';
    var prefersReduced = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---- Réglages globaux Chart.js : tout en manuscrit, encre grise ---- */
    Chart.defaults.font.family = "'Patrick Hand', 'Comic Sans MS', cursive";
    Chart.defaults.font.size = 13;
    Chart.defaults.color = '#2a2f3a';

    var easeOutCubic = function (t) { return 1 - Math.pow(1 - t, 3); };

    /* Récupère les points écran (x,y) d'un dataset, en ignorant les trous */
    function pointsOf(chart, datasetIndex) {
        var meta = chart.getDatasetMeta(datasetIndex);
        if (!meta || meta.hidden || !meta.data) return [];
        var pts = [];
        meta.data.forEach(function (el) {
            if (el && isFinite(el.x) && isFinite(el.y)) pts.push([el.x, el.y]);
        });
        return pts;
    }

    /* Tracé de secours si rough.js n'a pas chargé : simple ligne encre */
    function fallbackLine(ctx, pts, color, dashed) {
        if (pts.length < 2) return;
        ctx.save();
        ctx.beginPath();
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.lineWidth = 3;
        ctx.strokeStyle = color;
        if (dashed) ctx.setLineDash([8, 6]);
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
        ctx.stroke();
        ctx.restore();
    }

    /* Dessine les datasets « à la main » sur le canvas du graphique */
    function drawByHand(chart) {
        var area = chart.chartArea;
        if (!area) return;
        var ctx = chart.ctx;
        var progress = chart.$cahierProgress;
        if (progress === undefined) progress = prefersReduced ? 1 : 0;

        var rc = (typeof rough !== 'undefined') ? rough.canvas(chart.canvas) : null;

        // Repérage des datasets par leurs marqueurs posés dans la config
        var capitalIdx = -1, portfolioIdx = -1;
        chart.data.datasets.forEach(function (ds, i) {
            if (ds.cahierDash) capitalIdx = i;
            if (ds.cahierFill) portfolioIdx = i;
        });
        if (portfolioIdx === -1) portfolioIdx = chart.data.datasets.length - 1;
        if (capitalIdx === -1) capitalIdx = 0;

        var capitalPts = pointsOf(chart, capitalIdx);
        var portfolioPts = pointsOf(chart, portfolioIdx);

        // Révélation progressive : on découpe de gauche vers la droite
        ctx.save();
        ctx.beginPath();
        ctx.rect(area.left - 4, area.top - 20,
                 (area.right - area.left + 8) * progress, area.bottom - area.top + 24);
        ctx.clip();

        if (rc) {
            // 1) Aire sous la courbe du portefeuille, hachurée légèrement
            if (portfolioPts.length >= 2) {
                var poly = portfolioPts.slice();
                poly.push([portfolioPts[portfolioPts.length - 1][0], area.bottom]);
                poly.push([portfolioPts[0][0], area.bottom]);
                try {
                    rc.polygon(poly, {
                        stroke: 'none',
                        fill: 'rgba(39,64,139,0.16)',
                        fillStyle: 'hachure',
                        hachureGap: 7,
                        fillWeight: 1,
                        roughness: 1.4,
                        seed: 42
                    });
                } catch (e) {}
            }
            // 2) Ligne du capital investi : crayon gris pointillé
            if (capitalPts.length >= 2) {
                try {
                    rc.linearPath(capitalPts, {
                        stroke: PENCIL, strokeWidth: 2.5,
                        roughness: 1.3, bowing: 1.2,
                        strokeLineDash: [9, 7], seed: 7
                    });
                } catch (e) { fallbackLine(ctx, capitalPts, PENCIL, true); }
            }
            // 3) Ligne du portefeuille : stylo bleu appuyé, par-dessus
            if (portfolioPts.length >= 2) {
                try {
                    rc.linearPath(portfolioPts, {
                        stroke: INK_BLUE, strokeWidth: 3.2,
                        roughness: 1.2, bowing: 1.6, seed: 21
                    });
                } catch (e) { fallbackLine(ctx, portfolioPts, INK_BLUE, false); }
            }
        } else {
            fallbackLine(ctx, capitalPts, PENCIL, true);
            fallbackLine(ctx, portfolioPts, INK_BLUE, false);
        }

        ctx.restore();

        // Démarrage (une fois) de l'animation d'écriture
        if (chart.$cahierProgress === undefined && !prefersReduced) {
            chart.$cahierProgress = 0;
            var start = performance.now();
            var duration = 1500;
            var step = function (now) {
                var t = Math.min(1, (now - start) / duration);
                chart.$cahierProgress = easeOutCubic(t);
                chart.draw();           // redessine -> repasse ici avec le nouveau progress
                if (t < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
        } else if (chart.$cahierProgress === undefined) {
            chart.$cahierProgress = 1; // reduced-motion : tout de suite complet
        }
    }

    /* Plugin Chart.js : on dessine par-dessus les axes, sous les tooltips */
    Chart.register({
        id: 'cahierRough',
        afterDatasetsDraw: function (chart) {
            if (!chart.canvas || chart.canvas.id !== 'portfolioEvolutionChart') return;
            drawByHand(chart);
        }
    });
})();
