// Only use this encoding for HTML text and quoted attributes, never JavaScript.
window.escapeHtml = function(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};

// Keep ordinary relative/HTTP(S) links, without allowing executable URL schemes.
window.safeUrl = function(value) {
    if (!value) return '';
    try {
        const url = new URL(String(value), document.baseURI);
        return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch {
        return '';
    }
};
