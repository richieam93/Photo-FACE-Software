/* ========================================================================
   PHOTO SOFTWARE - HAUPT-JAVASCRIPT
   ======================================================================== */

'use strict';

// ========================================
// GLOBALE VARIABLEN
// ========================================

const App = {
    version: '1.0.0',
    debug: true,
    apiBaseUrl: window.location.origin,
    
    // State
    state: {
        isLoading: false,
        currentUser: null,
        cache: new Map()
    },
    
    // Config
    config: {
        toastDuration: 3000,
        apiTimeout: 30000,
        cacheExpiry: 300000, // 5 Minuten
        maxFileSize: 10 * 1024 * 1024, // 10 MB
        allowedImageTypes: ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
    }
};

// ========================================
// API HELPER
// ========================================

/**
 * Führt API-Request aus
 * @param {string} endpoint - API Endpunkt
 * @param {object} options - Fetch Options
 * @returns {Promise<object>} Response Data
 */
async function api(endpoint, options = {}) {
    // Loading State setzen
    App.state.isLoading = true;
    
    // Default Headers
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    // Volle URL bauen
    const url = endpoint.startsWith('http') 
        ? endpoint 
        : `${App.apiBaseUrl}${endpoint}`;
    
    try {
        // Request mit Timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), App.config.apiTimeout);
        
        const response = await fetch(url, {
            headers,
            signal: controller.signal,
            ...options
        });
        
        clearTimeout(timeoutId);
        
        // Response parsen
        let data;
        const contentType = response.headers.get('content-type');
        
        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            data = await response.text();
        }
        
        // Fehlerbehandlung
        if (!response.ok) {
            const errorMessage = data.detail || data.message || `HTTP Error ${response.status}`;
            throw new Error(errorMessage);
        }
        
        App.state.isLoading = false;
        return data;
        
    } catch (error) {
        App.state.isLoading = false;
        
        if (error.name === 'AbortError') {
            throw new Error('Request timeout - Server antwortet nicht');
        }
        
        console.error('API Error:', error);
        throw error;
    }
}

/**
 * GET Request
 */
async function apiGet(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return api(url, { method: 'GET' });
}

/**
 * POST Request
 */
async function apiPost(endpoint, data = {}) {
    return api(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

/**
 * PUT Request
 */
async function apiPut(endpoint, data = {}) {
    return api(endpoint, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
}

/**
 * DELETE Request
 */
async function apiDelete(endpoint) {
    return api(endpoint, { method: 'DELETE' });
}

// ========================================
// TOAST NOTIFICATIONS
// ========================================

/**
 * Zeigt Toast-Benachrichtigung
 * @param {string} message - Nachricht
 * @param {string} type - success|error|warning|info
 * @param {number} duration - Anzeigedauer in ms
 */
function showToast(message, type = 'info', duration = null) {
    duration = duration || App.config.toastDuration;
    
    // Container holen oder erstellen
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    // Toast erstellen
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    // Icon basierend auf Typ
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
    `;
    
    container.appendChild(toast);
    
    // Auto-Remove
    setTimeout(() => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
    }, duration);
    
    // Click to dismiss
    toast.addEventListener('click', () => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
    });
}

/**
 * Zeigt Erfolgs-Toast
 */
function showSuccess(message, duration = null) {
    showToast(message, 'success', duration);
}

/**
 * Zeigt Fehler-Toast
 */
function showError(message, duration = null) {
    showToast(message, 'error', duration);
}

/**
 * Zeigt Warnung-Toast
 */
function showWarning(message, duration = null) {
    showToast(message, 'warning', duration);
}

/**
 * Zeigt Info-Toast
 */
function showInfo(message, duration = null) {
    showToast(message, 'info', duration);
}

// ========================================
// MODAL HANDLING
// ========================================

/**
 * Öffnet Modal
 * @param {string} modalId - ID des Modals
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) {
        console.error(`Modal mit ID "${modalId}" nicht gefunden`);
        return;
    }
    
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    // ESC zum Schließen
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            closeModal(modalId);
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
}

/**
 * Schließt Modal
 * @param {string} modalId - ID des Modals
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    modal.classList.remove('active');
    document.body.style.overflow = '';
}

/**
 * Schließt Modal bei Klick auf Hintergrund
 */
function closeModalOnBackground(event, modalId) {
    if (event.target.id === modalId) {
        closeModal(modalId);
    }
}

// ========================================
// LOADING OVERLAY
// ========================================

/**
 * Zeigt Loading Overlay
 * @param {string} message - Optionale Nachricht
 */
function showLoading(message = 'Lädt...') {
    let overlay = document.getElementById('loading-overlay');
    
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content">
                <div class="spinner spinner-lg"></div>
                <p class="loading-message">${escapeHtml(message)}</p>
            </div>
        `;
        document.body.appendChild(overlay);
    } else {
        overlay.querySelector('.loading-message').textContent = message;
    }
    
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * Versteckt Loading Overlay
 */
function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// ========================================
// DATUMS-/ZEIT-FUNKTIONEN
// ========================================

/**
 * Formatiert Timestamp für Anzeige
 * @param {string} timestamp - ISO Timestamp
 * @returns {string} Formatiertes Datum
 */
function formatTime(timestamp) {
    if (!timestamp) return '-';
    
    try {
        const date = new Date(timestamp);
        
        // Prüfen ob gültiges Datum
        if (isNaN(date.getTime())) return timestamp;
        
        // Lokalisiertes Format
        return date.toLocaleString('de-CH', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (error) {
        console.error('Fehler beim Formatieren des Datums:', error);
        return timestamp;
    }
}

/**
 * Formatiert Datum ohne Zeit
 */
function formatDate(timestamp) {
    if (!timestamp) return '-';
    
    try {
        const date = new Date(timestamp);
        return date.toLocaleDateString('de-CH', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    } catch (error) {
        return timestamp;
    }
}

/**
 * Gibt relative Zeit zurück (z.B. "vor 5 Minuten")
 */
function formatRelativeTime(timestamp) {
    if (!timestamp) return '-';
    
    try {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);
        
        if (days > 7) return formatDate(timestamp);
        if (days > 0) return `vor ${days} Tag${days > 1 ? 'en' : ''}`;
        if (hours > 0) return `vor ${hours} Stunde${hours > 1 ? 'n' : ''}`;
        if (minutes > 0) return `vor ${minutes} Minute${minutes > 1 ? 'n' : ''}`;
        return 'gerade eben';
    } catch (error) {
        return timestamp;
    }
}

// ========================================
// STRING UTILITIES
// ========================================

/**
 * Escaped HTML-Sonderzeichen
 * @param {string} text - Text
 * @returns {string} Escaped Text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Kürzt Text auf Maximallänge
 */
function truncate(text, maxLength = 100, suffix = '...') {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength - suffix.length) + suffix;
}

/**
 * Kapitalisiert ersten Buchstaben
 */
function capitalize(text) {
    if (!text) return '';
    return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Slug aus Text erstellen
 */
function slugify(text) {
    return text
        .toLowerCase()
        .replace(/[äöü]/g, match => ({ 'ä': 'ae', 'ö': 'oe', 'ü': 'ue' }[match]))
        .replace(/ß/g, 'ss')
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .trim();
}

// ========================================
// ZAHL-FORMATIERUNG
// ========================================

/**
 * Formatiert Zahl mit Tausender-Trennzeichen
 */
function formatNumber(number, decimals = 0) {
    return new Intl.NumberFormat('de-CH', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(number);
}

/**
 * Formatiert Preis
 */
function formatPrice(price, currency = 'CHF') {
    return new Intl.NumberFormat('de-CH', {
        style: 'currency',
        currency: currency
    }).format(price);
}

/**
 * Formatiert Dateigröße
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Formatiert Prozent
 */
function formatPercent(value, decimals = 1) {
    return `${value.toFixed(decimals)}%`;
}

// ========================================
// DATEI-HANDLING
// ========================================

/**
 * Validiert Bilddatei
 * @param {File} file - Datei
 * @returns {object} {valid: boolean, error: string}
 */
function validateImageFile(file) {
    // Typ prüfen
    if (!App.config.allowedImageTypes.includes(file.type)) {
        return {
            valid: false,
            error: `Ungültiger Dateityp. Erlaubt: ${App.config.allowedImageTypes.join(', ')}`
        };
    }
    
    // Größe prüfen
    if (file.size > App.config.maxFileSize) {
        return {
            valid: false,
            error: `Datei zu groß. Maximum: ${formatFileSize(App.config.maxFileSize)}`
        };
    }
    
    return { valid: true, error: null };
}

/**
 * Liest Datei als Data URL
 */
function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/**
 * Lädt Bild
 */
function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
    });
}

/**
 * Komprimiert Bild
 */
async function compressImage(file, maxWidth = 1920, quality = 0.85) {
    const dataUrl = await readFileAsDataURL(file);
    const img = await loadImage(dataUrl);
    
    // Neue Dimensionen berechnen
    let width = img.width;
    let height = img.height;
    
    if (width > maxWidth) {
        height = Math.round(height * maxWidth / width);
        width = maxWidth;
    }
    
    // Canvas erstellen
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, width, height);
    
    // Als Blob zurückgeben
    return new Promise((resolve) => {
        canvas.toBlob(resolve, 'image/jpeg', quality);
    });
}

// ========================================
// LOCAL STORAGE
// ========================================

/**
 * Speichert Daten in LocalStorage
 */
function setStorage(key, value) {
    try {
        const data = JSON.stringify(value);
        localStorage.setItem(key, data);
        return true;
    } catch (error) {
        console.error('LocalStorage Fehler:', error);
        return false;
    }
}

/**
 * Holt Daten aus LocalStorage
 */
function getStorage(key, defaultValue = null) {
    try {
        const data = localStorage.getItem(key);
        return data ? JSON.parse(data) : defaultValue;
    } catch (error) {
        console.error('LocalStorage Fehler:', error);
        return defaultValue;
    }
}

/**
 * Löscht aus LocalStorage
 */
function removeStorage(key) {
    try {
        localStorage.removeItem(key);
        return true;
    } catch (error) {
        console.error('LocalStorage Fehler:', error);
        return false;
    }
}

/**
 * Leert LocalStorage
 */
function clearStorage() {
    try {
        localStorage.clear();
        return true;
    } catch (error) {
        console.error('LocalStorage Fehler:', error);
        return false;
    }
}

// ========================================
// SESSION STORAGE
// ========================================

/**
 * Speichert Daten in SessionStorage
 */
function setSession(key, value) {
    try {
        const data = JSON.stringify(value);
        sessionStorage.setItem(key, data);
        return true;
    } catch (error) {
        console.error('SessionStorage Fehler:', error);
        return false;
    }
}

/**
 * Holt Daten aus SessionStorage
 */
function getSession(key, defaultValue = null) {
    try {
        const data = sessionStorage.getItem(key);
        return data ? JSON.parse(data) : defaultValue;
    } catch (error) {
        console.error('SessionStorage Fehler:', error);
        return defaultValue;
    }
}

/**
 * Löscht aus SessionStorage
 */
function removeSession(key) {
    try {
        sessionStorage.removeItem(key);
        return true;
    } catch (error) {
        console.error('SessionStorage Fehler:', error);
        return false;
    }
}

// ========================================
// FORMULAR-UTILITIES
// ========================================

/**
 * Holt Formular-Daten als Object
 */
function getFormData(formElement) {
    const formData = new FormData(formElement);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        // Array-Handling für Checkboxen etc.
        if (data[key]) {
            if (Array.isArray(data[key])) {
                data[key].push(value);
            } else {
                data[key] = [data[key], value];
            }
        } else {
            data[key] = value;
        }
    }
    
    return data;
}

/**
 * Setzt Formular-Daten
 */
function setFormData(formElement, data) {
    for (const [key, value] of Object.entries(data)) {
        const field = formElement.elements[key];
        
        if (!field) continue;
        
        if (field.type === 'checkbox') {
            field.checked = Boolean(value);
        } else if (field.type === 'radio') {
            const radio = formElement.querySelector(`input[name="${key}"][value="${value}"]`);
            if (radio) radio.checked = true;
        } else {
            field.value = value;
        }
    }
}

/**
 * Validiert Formular
 */
function validateForm(formElement) {
    const errors = [];
    const fields = formElement.querySelectorAll('[required]');
    
    fields.forEach(field => {
        if (!field.value.trim()) {
            errors.push({
                field: field.name,
                message: `${field.name} ist erforderlich`
            });
            field.classList.add('error');
        } else {
            field.classList.remove('error');
        }
    });
    
    return {
        valid: errors.length === 0,
        errors
    };
}

// ========================================
// DEBOUNCE / THROTTLE
// ========================================

/**
 * Debounce Funktion
 * Führt Funktion erst nach Wartezeit aus
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
 * Throttle Funktion
 * Begrenzt Ausführungsrate
 */
function throttle(func, limit = 300) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ========================================
// ARRAY UTILITIES
// ========================================

/**
 * Entfernt Duplikate aus Array
 */
function unique(array) {
    return [...new Set(array)];
}

/**
 * Gruppiert Array nach Kriterium
 */
function groupBy(array, key) {
    return array.reduce((result, item) => {
        const group = typeof key === 'function' ? key(item) : item[key];
        (result[group] = result[group] || []).push(item);
        return result;
    }, {});
}

/**
 * Sortiert Array
 */
function sortBy(array, key, order = 'asc') {
    return [...array].sort((a, b) => {
        const aVal = typeof key === 'function' ? key(a) : a[key];
        const bVal = typeof key === 'function' ? key(b) : b[key];
        
        if (aVal < bVal) return order === 'asc' ? -1 : 1;
        if (aVal > bVal) return order === 'asc' ? 1 : -1;
        return 0;
    });
}

/**
 * Chunk Array in kleinere Arrays
 */
function chunk(array, size) {
    const chunks = [];
    for (let i = 0; i < array.length; i += size) {
        chunks.push(array.slice(i, i + size));
    }
    return chunks;
}

// ========================================
// DOM UTILITIES
// ========================================

/**
 * Erstellt Element aus HTML String
 */
function createElement(html) {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    return template.content.firstChild;
}

/**
 * Prüft ob Element im Viewport
 */
function isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}

/**
 * Scrollt zu Element
 */
function scrollToElement(element, offset = 0) {
    const elementPosition = element.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - offset;
    
    window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
    });
}

/**
 * Kopiert Text in Zwischenablage
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showSuccess('In Zwischenablage kopiert');
        return true;
    } catch (error) {
        console.error('Clipboard Fehler:', error);
        showError('Kopieren fehlgeschlagen');
        return false;
    }
}

// ========================================
// FARB-UTILITIES
// ========================================

/**
 * Konvertiert RGB zu Hex
 */
function rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(x => {
        const hex = x.toString(16);
        return hex.length === 1 ? '0' + hex : hex;
    }).join('');
}

/**
 * Konvertiert Hex zu RGB
 */
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

/**
 * Berechnet Farb-Kontrast (Hell/Dunkel)
 */
function getColorBrightness(hex) {
    const rgb = hexToRgb(hex);
    if (!rgb) return 128;
    
    // YIQ Formel
    return (rgb.r * 299 + rgb.g * 587 + rgb.b * 114) / 1000;
}

/**
 * Gibt passende Text-Farbe zurück
 */
function getContrastColor(backgroundColor) {
    const brightness = getColorBrightness(backgroundColor);
    return brightness > 128 ? '#000000' : '#ffffff';
}

// ========================================
// CACHE UTILITIES
// ========================================

/**
 * Setzt Cache-Eintrag
 */
function setCache(key, value, expiry = null) {
    const expiryTime = expiry || App.config.cacheExpiry;
    App.state.cache.set(key, {
        value,
        expires: Date.now() + expiryTime
    });
}

/**
 * Holt Cache-Eintrag
 */
function getCache(key) {
    const cached = App.state.cache.get(key);
    
    if (!cached) return null;
    
    // Prüfen ob abgelaufen
    if (Date.now() > cached.expires) {
        App.state.cache.delete(key);
        return null;
    }
    
    return cached.value;
}

/**
 * Löscht Cache-Eintrag
 */
function deleteCache(key) {
    App.state.cache.delete(key);
}

/**
 * Leert gesamten Cache
 */
function clearCache() {
    App.state.cache.clear();
}

// ========================================
// URL UTILITIES
// ========================================

/**
 * Parst URL Query Parameter
 */
function parseQueryString() {
    const params = {};
    const queryString = window.location.search.substring(1);
    const pairs = queryString.split('&');
    
    pairs.forEach(pair => {
        const [key, value] = pair.split('=');
        if (key) {
            params[decodeURIComponent(key)] = decodeURIComponent(value || '');
        }
    });
    
    return params;
}

/**
 * Baut Query String aus Object
 */
function buildQueryString(params) {
    return Object.entries(params)
        .filter(([_, value]) => value != null)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join('&');
}

/**
 * Aktualisiert URL ohne Reload
 */
function updateUrl(params, replace = false) {
    const url = new URL(window.location);
    
    Object.entries(params).forEach(([key, value]) => {
        if (value == null) {
            url.searchParams.delete(key);
        } else {
            url.searchParams.set(key, value);
        }
    });
    
    if (replace) {
        window.history.replaceState({}, '', url);
    } else {
        window.history.pushState({}, '', url);
    }
}

// ========================================
// BROWSER DETECTION
// ========================================

/**
 * Erkennt Browser und Plattform
 */
const Browser = {
    isChrome: /Chrome/.test(navigator.userAgent) && /Google Inc/.test(navigator.vendor),
    isFirefox: /Firefox/.test(navigator.userAgent),
    isSafari: /Safari/.test(navigator.userAgent) && /Apple/.test(navigator.vendor),
    isEdge: /Edg/.test(navigator.userAgent),
    isMobile: /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent),
    isIOS: /iPad|iPhone|iPod/.test(navigator.userAgent),
    isAndroid: /Android/.test(navigator.userAgent)
};

// ========================================
// INITIALISIERUNG
// ========================================

/**
 * App Initialisierung
 */
function initApp() {
    // Debug Info
    if (App.debug) {
        console.log(`🚀 Photo Software v${App.version}`);
        console.log('Browser:', Browser);
    }
    
    // Service Worker registrieren (optional)
    if ('serviceWorker' in navigator && !App.debug) {
        navigator.serviceWorker.register('/sw.js').catch(() => {
            // Silent fail
        });
    }
    
    // Globale Error Handler
    window.addEventListener('error', (event) => {
        console.error('Global Error:', event.error);
        if (App.debug) {
            showError('Ein Fehler ist aufgetreten');
        }
    });
    
    // Unhandled Promise Rejections
    window.addEventListener('unhandledrejection', (event) => {
        console.error('Unhandled Promise Rejection:', event.reason);
    });
    
    // Online/Offline Events
    window.addEventListener('online', () => {
        showSuccess('Verbindung wiederhergestellt');
    });
    
    window.addEventListener('offline', () => {
        showWarning('Keine Internetverbindung');
    });
    
    // Loading State für Fetch Requests
    let activeRequests = 0;
    const originalFetch = window.fetch;
    
    window.fetch = function(...args) {
        activeRequests++;
        
        return originalFetch.apply(this, args).finally(() => {
            activeRequests--;
        });
    };
}

// ========================================
// DOM READY
// ========================================

// Initialisierung wenn DOM geladen
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

// ========================================
// EXPORTS (für Module)
// ========================================

// Falls als Modul verwendet
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        App,
        api, apiGet, apiPost, apiPut, apiDelete,
        showToast, showSuccess, showError, showWarning, showInfo,
        openModal, closeModal,
        formatTime, formatDate, formatRelativeTime,
        formatNumber, formatPrice, formatFileSize, formatPercent,
        validateImageFile, readFileAsDataURL, loadImage, compressImage,
        setStorage, getStorage, removeStorage,
        setSession, getSession, removeSession,
        debounce, throttle,
        escapeHtml, truncate, capitalize,
        Browser
    };
}

console.log('✅ app.js geladen');