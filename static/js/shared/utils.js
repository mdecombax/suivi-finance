/**
 * Fonctions utilitaires partagées
 * Ce fichier contient toutes les fonctions communes utilisées sur plusieurs pages
 */

// ============================================================================
// FORMATAGE
// ============================================================================

/**
 * Formate un nombre en devise EUR
 * @param {number} value - Valeur à formater
 * @param {Object} options - Options de formatage
 * @returns {string} Valeur formatée
 */
function formatCurrency(value, options = {}) {
    const {
        minimumFractionDigits = 0,
        maximumFractionDigits = 0,
        currency = 'EUR'
    } = options;

    return new Intl.NumberFormat('fr-FR', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits,
        maximumFractionDigits
    }).format(value);
}

/**
 * Formate un nombre en pourcentage
 * @param {number} value - Valeur à formater (0.1 = 10%)
 * @param {Object} options - Options de formatage
 * @returns {string} Valeur formatée
 */
function formatPercentage(value, options = {}) {
    const {
        minimumFractionDigits = 1,
        maximumFractionDigits = 1,
        showSign = false
    } = options;

    const formatted = new Intl.NumberFormat('fr-FR', {
        style: 'percent',
        minimumFractionDigits,
        maximumFractionDigits
    }).format(value);

    if (showSign && value > 0) {
        return '+' + formatted;
    }
    return formatted;
}

/**
 * Formate un nombre avec séparateurs de milliers
 * @param {number} value - Valeur à formater
 * @param {number} decimals - Nombre de décimales
 * @returns {string} Valeur formatée
 */
function formatNumber(value, decimals = 2) {
    return new Intl.NumberFormat('fr-FR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(value);
}

/**
 * Formate une date en format français
 * @param {Date|string} date - Date à formater
 * @param {Object} options - Options de formatage Intl
 * @returns {string} Date formatée
 */
function formatDate(date, options = {}) {
    const defaultOptions = {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        ...options
    };

    const dateObj = typeof date === 'string' ? new Date(date) : date;
    return new Intl.DateTimeFormat('fr-FR', defaultOptions).format(dateObj);
}

// ============================================================================
// MESSAGES ET NOTIFICATIONS
// ============================================================================

/**
 * Affiche un message de notification
 * @param {string} message - Message à afficher
 * @param {string} type - Type de message ('success', 'error', 'info', 'warning')
 * @param {Object} options - Options supplémentaires
 */
function showMessage(message, type = 'info', options = {}) {
    const {
        containerId = 'messageContainer',
        duration = 3000,
        autoHide = type === 'success' || type === 'info'
    } = options;

    // Chercher le container de messages
    let container = document.getElementById(containerId);

    // Si pas de container spécifique, créer un container flottant
    if (!container) {
        container = document.getElementById('globalMessageContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'globalMessageContainer';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                max-width: 400px;
            `;
            document.body.appendChild(container);
        }
    }

    // Créer l'élément de message
    const messageEl = document.createElement('div');
    messageEl.className = `message ${type} animate-fadeInDown`;
    messageEl.innerHTML = message;

    // Styles selon le type
    const styles = {
        success: 'background: rgba(76,175,80,0.15); border: 1px solid rgba(76,175,80,0.3); color: #81c784;',
        error: 'background: rgba(244,67,54,0.15); border: 1px solid rgba(244,67,54,0.3); color: #e57373;',
        info: 'background: rgba(130,196,255,0.15); border: 1px solid rgba(130,196,255,0.3); color: #82c4ff;',
        warning: 'background: rgba(255,193,7,0.15); border: 1px solid rgba(255,193,7,0.3); color: #ffd54f;'
    };

    messageEl.style.cssText = `
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.9rem;
        ${styles[type] || styles.info}
    `;

    container.appendChild(messageEl);

    // Auto-hide si configuré
    if (autoHide) {
        setTimeout(() => {
            messageEl.style.opacity = '0';
            messageEl.style.transform = 'translateX(20px)';
            setTimeout(() => messageEl.remove(), 300);
        }, duration);
    }

    return messageEl;
}

/**
 * Efface tous les messages
 * @param {string} containerId - ID du container
 */
function clearMessages(containerId = 'messageContainer') {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = '';
    }
}

// ============================================================================
// VALIDATION
// ============================================================================

/**
 * Valide un code ISIN
 * @param {string} isin - Code ISIN à valider
 * @returns {boolean} True si valide
 */
function validateISIN(isin) {
    if (!isin) return false;
    const isinRegex = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;
    return isinRegex.test(isin.toUpperCase());
}

/**
 * Valide une adresse email
 * @param {string} email - Email à valider
 * @returns {boolean} True si valide
 */
function validateEmail(email) {
    if (!email) return false;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// ============================================================================
// API CLIENT
// ============================================================================

/**
 * Effectue une requête API authentifiée
 * @param {string} endpoint - URL de l'endpoint (ex: '/api/portfolio')
 * @param {Object} options - Options de la requête
 * @returns {Promise<Object>} Réponse JSON
 */
async function apiRequest(endpoint, options = {}) {
    const {
        method = 'GET',
        body = null,
        headers = {}
    } = options;

    // Récupérer le token d'authentification
    const token = await getAuthToken();

    if (!token) {
        throw new Error('Non authentifié');
    }

    const requestOptions = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            ...headers
        }
    };

    if (body && method !== 'GET') {
        requestOptions.body = JSON.stringify(body);
    }

    const response = await fetch(endpoint, requestOptions);

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Erreur HTTP ${response.status}`);
    }

    return response.json();
}

/**
 * Raccourci pour GET authentifié
 */
async function apiGet(endpoint) {
    return apiRequest(endpoint, { method: 'GET' });
}

/**
 * Raccourci pour POST authentifié
 */
async function apiPost(endpoint, body) {
    return apiRequest(endpoint, { method: 'POST', body });
}

/**
 * Raccourci pour DELETE authentifié
 */
async function apiDelete(endpoint) {
    return apiRequest(endpoint, { method: 'DELETE' });
}

// ============================================================================
// UTILITAIRES DOM
// ============================================================================

/**
 * Affiche un élément
 * @param {string|HTMLElement} element - ID ou élément
 */
function showElement(element) {
    const el = typeof element === 'string' ? document.getElementById(element) : element;
    if (el) el.style.display = '';
}

/**
 * Masque un élément
 * @param {string|HTMLElement} element - ID ou élément
 */
function hideElement(element) {
    const el = typeof element === 'string' ? document.getElementById(element) : element;
    if (el) el.style.display = 'none';
}

/**
 * Bascule la visibilité d'un élément
 * @param {string|HTMLElement} element - ID ou élément
 */
function toggleElement(element) {
    const el = typeof element === 'string' ? document.getElementById(element) : element;
    if (el) {
        el.style.display = el.style.display === 'none' ? '' : 'none';
    }
}

// ============================================================================
// UTILITAIRES DIVERS
// ============================================================================

/**
 * Debounce une fonction
 * @param {Function} func - Fonction à debouncer
 * @param {number} wait - Délai en ms
 * @returns {Function} Fonction debouncée
 */
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Retourne la date d'aujourd'hui au format YYYY-MM-DD
 * @returns {string}
 */
function getTodayISO() {
    return new Date().toISOString().split('T')[0];
}

/**
 * Récupère le type de compte depuis le localStorage
 * @returns {string} 'pea' ou 'cto'
 */
function getAccountType() {
    return localStorage.getItem('accountType') || 'pea';
}

/**
 * Définit le type de compte dans le localStorage
 * @param {string} type - 'pea' ou 'cto'
 */
function setAccountType(type) {
    localStorage.setItem('accountType', type);
}

// Exposer toutes les fonctions globalement
window.formatCurrency = formatCurrency;
window.formatPercentage = formatPercentage;
window.formatNumber = formatNumber;
window.formatDate = formatDate;
window.showMessage = showMessage;
window.clearMessages = clearMessages;
window.validateISIN = validateISIN;
window.validateEmail = validateEmail;
window.apiRequest = apiRequest;
window.apiGet = apiGet;
window.apiPost = apiPost;
window.apiDelete = apiDelete;
window.showElement = showElement;
window.hideElement = hideElement;
window.toggleElement = toggleElement;
window.debounce = debounce;
window.getTodayISO = getTodayISO;
window.getAccountType = getAccountType;
window.setAccountType = setAccountType;
