/**
 * Configuration Firebase centralisée
 * Ce fichier doit être chargé en premier sur toutes les pages
 */

// Configuration Firebase (une seule source de vérité)
const FIREBASE_CONFIG = {
    apiKey: "AIzaSyBFrk8tZVEuM0LeQ0D8kJ7N2Bt-KyuQv0I",
    authDomain: "suivi-financ.firebaseapp.com",
    projectId: "suivi-financ",
    storageBucket: "suivi-financ.firebasestorage.app",
    messagingSenderId: "959011615445",
    appId: "1:959011615445:web:993be6cee77fc6cedae85c",
    measurementId: "G-8QXCJ8J23S"
};

/**
 * Initialise Firebase si pas déjà fait
 * Compatible avec le SDK compat (utilisé par toutes les pages)
 */
function initializeFirebase() {
    if (typeof firebase === 'undefined') {
        console.error('Firebase SDK not loaded. Make sure to include firebase-app-compat.js before this script.');
        return false;
    }

    if (!firebase.apps.length) {
        firebase.initializeApp(FIREBASE_CONFIG);
    }

    // Exposer globalement pour compatibilité avec le code existant
    window.firebaseAuth = firebase.auth();
    window.firebaseDb = firebase.firestore ? firebase.firestore() : null;

    return true;
}

// Exposer globalement
window.FIREBASE_CONFIG = FIREBASE_CONFIG;
window.initializeFirebase = initializeFirebase;
