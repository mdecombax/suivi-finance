/**
 * Module d'authentification centralisé
 * Gère l'état d'authentification pour toutes les pages
 */

// État global d'authentification
const AuthState = {
    currentUser: null,
    authToken: null,
    isInitialized: false,
    onAuthChangeCallbacks: []
};

/**
 * Initialise l'authentification et écoute les changements d'état
 * @param {Object} options - Options de configuration
 * @param {boolean} options.requireAuth - Si true, redirige vers / si non connecté
 * @param {Function} options.onAuthenticated - Callback appelé quand l'utilisateur est connecté
 * @param {Function} options.onUnauthenticated - Callback appelé quand l'utilisateur n'est pas connecté
 */
function initAuth(options = {}) {
    const {
        requireAuth = true,
        onAuthenticated = null,
        onUnauthenticated = null
    } = options;

    // S'assurer que Firebase est initialisé
    if (typeof initializeFirebase === 'function') {
        initializeFirebase();
    }

    const auth = window.firebaseAuth || firebase.auth();

    auth.onAuthStateChanged(async (user) => {
        if (user) {
            // Utilisateur connecté
            AuthState.currentUser = user;
            try {
                AuthState.authToken = await user.getIdToken();
            } catch (error) {
                console.error('Erreur lors de la récupération du token:', error);
            }
            AuthState.isInitialized = true;

            // Mettre à jour l'interface utilisateur si la fonction existe
            if (typeof window.updateUserInterface === 'function') {
                window.updateUserInterface(user);
            }

            // Appeler le callback onAuthenticated
            if (onAuthenticated) {
                onAuthenticated(user, AuthState.authToken);
            }

            // Notifier tous les listeners
            AuthState.onAuthChangeCallbacks.forEach(cb => cb(user, AuthState.authToken));

        } else {
            // Utilisateur non connecté
            AuthState.currentUser = null;
            AuthState.authToken = null;
            AuthState.isInitialized = true;

            if (onUnauthenticated) {
                onUnauthenticated();
            } else if (requireAuth) {
                // Redirection par défaut si authentification requise
                window.location.href = '/';
            }
        }
    });
}

/**
 * Récupère le token d'authentification actuel (le rafraîchit si nécessaire)
 * @returns {Promise<string|null>} Le token ou null si non connecté
 */
async function getAuthToken() {
    if (!AuthState.currentUser) {
        return null;
    }

    try {
        // Toujours récupérer un token frais
        AuthState.authToken = await AuthState.currentUser.getIdToken(true);
        return AuthState.authToken;
    } catch (error) {
        console.error('Erreur lors du rafraîchissement du token:', error);
        return AuthState.authToken; // Retourner l'ancien token en fallback
    }
}

/**
 * Récupère l'utilisateur actuel
 * @returns {Object|null} L'utilisateur Firebase ou null
 */
function getCurrentUser() {
    return AuthState.currentUser;
}

/**
 * Vérifie si l'utilisateur est connecté
 * @returns {boolean}
 */
function isAuthenticated() {
    return AuthState.currentUser !== null;
}

/**
 * Déconnecte l'utilisateur
 * @returns {Promise<void>}
 */
async function logout() {
    try {
        const auth = window.firebaseAuth || firebase.auth();
        await auth.signOut();
        window.location.href = '/';
    } catch (error) {
        console.error('Erreur de déconnexion:', error);
        throw error;
    }
}

/**
 * Ajoute un callback à appeler lors des changements d'authentification
 * @param {Function} callback - Fonction appelée avec (user, token)
 */
function onAuthChange(callback) {
    AuthState.onAuthChangeCallbacks.push(callback);

    // Si déjà initialisé, appeler immédiatement
    if (AuthState.isInitialized) {
        callback(AuthState.currentUser, AuthState.authToken);
    }
}

// Exposer globalement
window.AuthState = AuthState;
window.initAuth = initAuth;
window.getAuthToken = getAuthToken;
window.getCurrentUser = getCurrentUser;
window.isAuthenticated = isAuthenticated;
window.logout = logout;
window.onAuthChange = onAuthChange;
