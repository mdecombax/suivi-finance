/**
 * Module centralisé pour la gestion de la modale des paramètres
 * Utilisé par toutes les pages pour maintenir la cohérence
 */

/**
 * Ouvre la modale des paramètres
 */
function openSettings() {
    // Mettre à jour l'état actuel dans les paramètres
    const currentAccountType = localStorage.getItem('accountType') || 'pea';
    const accountTypeRadios = document.querySelectorAll('input[name="settings_account_type"]');
    if (accountTypeRadios.length > 0) {
        accountTypeRadios.forEach(radio => {
            radio.checked = radio.value === currentAccountType;
        });
    }

    // Mettre à jour l'état de l'option "Afficher les détails par défaut"
    const showDetailedKpisCheckbox = document.getElementById('showDetailedKpis');
    if (showDetailedKpisCheckbox) {
        const showDetailedKpisDefault = localStorage.getItem('showDetailedKpisDefault') === 'true';
        showDetailedKpisCheckbox.checked = showDetailedKpisDefault;
    }

    // Afficher la modale
    const settingsPopup = document.getElementById('settingsPopup');
    if (settingsPopup) {
        settingsPopup.classList.add('show');
    }

    // Fermer le menu flottant s'il existe
    if (typeof toggleFloatingMenu === 'function') {
        toggleFloatingMenu();
    }
}

/**
 * Ferme la modale des paramètres
 */
function closeSettings() {
    const settingsPopup = document.getElementById('settingsPopup');
    if (settingsPopup) {
        settingsPopup.classList.remove('show');
    }
}

/**
 * Change le type de compte et recharge les données
 * @param {string} accountType - Type de compte ('pea' ou 'cto')
 */
function changeAccountType(accountType) {
    // Sauvegarder dans le localStorage
    localStorage.setItem('accountType', accountType);

    // Mettre à jour l'état des boutons radio
    const accountTypeRadios = document.querySelectorAll('input[name="settings_account_type"]');
    if (accountTypeRadios.length > 0) {
        accountTypeRadios.forEach(radio => {
            radio.checked = radio.value === accountType;
        });
    }

    // Appeler selectAccountType s'il existe (page index)
    if (typeof selectAccountType === 'function') {
        selectAccountType(accountType);
    }

    // Recharger les données du portefeuille si la fonction existe (page index)
    if (typeof loadPortfolioData === 'function') {
        loadPortfolioData();
    } else {
        // Sur les autres pages, afficher un message et recharger la page
        if (typeof showMessage === 'function') {
            showMessage('Type de compte modifié. Rechargez la page pour voir les changements.', 'info');
        }
    }
}

/**
 * Bascule l'option d'affichage des détails par défaut
 */
function toggleDetailedKpisDefault() {
    const showDetailedKpisCheckbox = document.getElementById('showDetailedKpis');
    if (showDetailedKpisCheckbox) {
        const isChecked = showDetailedKpisCheckbox.checked;
        localStorage.setItem('showDetailedKpisDefault', isChecked);

        // Afficher un message de confirmation si la fonction existe
        if (typeof showMessage === 'function') {
            const message = isChecked
                ? 'Les détails seront affichés par défaut'
                : 'Les détails seront masqués par défaut';
            showMessage(message, 'info');
        }
    }
}

/**
 * Réinitialise toutes les données de l'application
 */
function resetData() {
    const confirmMessage = 'Attention ! Cette action supprimera toutes vos données locales. Cette action est irréversible. Continuer ?';

    if (confirm(confirmMessage)) {
        // Effacer toutes les données
        localStorage.clear();

        alert('Données locales réinitialisées. La page va se recharger.');
        window.location.reload();
    }
}

// Exposer les fonctions globalement
window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.changeAccountType = changeAccountType;
window.toggleDetailedKpisDefault = toggleDetailedKpisDefault;
window.resetData = resetData;

// Fermer la modale en cliquant sur l'overlay
document.addEventListener('click', (e) => {
    const settingsPopup = document.getElementById('settingsPopup');
    if (settingsPopup && e.target === settingsPopup) {
        closeSettings();
    }
});

// Fermer la modale avec la touche Échap
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeSettings();
    }
});
