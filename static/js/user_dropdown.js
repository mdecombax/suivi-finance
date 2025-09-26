/**
 * Module centralisé pour la gestion du dropdown utilisateur
 * Utilisé par toutes les pages pour maintenir la cohérence
 */

// Variables d'état
let isUserMenuOpen = false;

/**
 * Initialise l'interface utilisateur avec les informations de l'utilisateur authentifié
 * @param {Object} user - Objet utilisateur Firebase
 */
function updateUserInterface(user) {
    if (!user) return;

    // Afficher le container de l'avatar
    const avatarContainer = document.getElementById('userAvatarContainer');
    if (avatarContainer) {
        avatarContainer.style.display = 'block';
    }

    // Afficher le lien projections si présent sur la page
    const projectionsLink = document.getElementById('projectionsLink');
    if (projectionsLink) {
        projectionsLink.style.display = 'inline-block';
    }

    // Mettre à jour les initiales de l'utilisateur
    const userInitial = user.email ? user.email.charAt(0).toUpperCase() : 'U';
    const userInitialEl = document.getElementById('userInitial');
    const userInitialLargeEl = document.getElementById('userInitialLarge');

    if (userInitialEl) userInitialEl.textContent = userInitial;
    if (userInitialLargeEl) userInitialLargeEl.textContent = userInitial;

    // Mettre à jour l'email dans le dropdown
    const userEmailEl = document.getElementById('userEmailDropdown');
    if (userEmailEl) {
        userEmailEl.textContent = user.email || 'user@example.com';
    }
}

/**
 * Bascule l'affichage du menu utilisateur
 */
function toggleUserMenu() {
    const dropdown = document.getElementById('userDropdown');
    if (!dropdown) return;

    isUserMenuOpen = !isUserMenuOpen;
    if (isUserMenuOpen) {
        dropdown.classList.add('show');
    } else {
        dropdown.classList.remove('show');
    }
}

/**
 * Fonction pour afficher les fonctionnalités à venir
 * @param {string} feature - Nom de la fonctionnalité
 */
function showComingSoon(feature) {
    // Vérifier si la fonction showMessage existe sur la page
    if (typeof showMessage === 'function') {
        showMessage(`${feature} - Fonctionnalité à venir`, 'info');
    } else {
        alert(`${feature} - Fonctionnalité à venir`);
    }
}

/**
 * Fonction de déconnexion
 */
async function logout() {
    try {
        if (window.signOut && window.firebaseAuth) {
            await window.signOut(window.firebaseAuth);
        }
        window.location.href = '/';
    } catch (error) {
        console.error('Erreur de déconnexion:', error);
    }
}

/**
 * Initialise les événements du dropdown utilisateur
 */
function initUserDropdownEvents() {
    // Fermer le menu utilisateur en cliquant à l'extérieur
    document.addEventListener('click', (e) => {
        const userAvatarContainer = document.getElementById('userAvatarContainer');
        if (isUserMenuOpen && userAvatarContainer && !userAvatarContainer.contains(e.target)) {
            toggleUserMenu();
        }
    });
}

// Exposer les fonctions globalement
window.updateUserInterface = updateUserInterface;
window.toggleUserMenu = toggleUserMenu;
window.showComingSoon = showComingSoon;
window.logout = logout;
window.initUserDropdownEvents = initUserDropdownEvents;

// Initialiser automatiquement les événements quand le DOM est prêt
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUserDropdownEvents);
} else {
    initUserDropdownEvents();
}