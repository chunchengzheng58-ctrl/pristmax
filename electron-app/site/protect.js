/**
 * Pristmax Code Protection
 *
 * Anti-theft protection for website source code
 * Note: This cannot fully prevent determined attackers,
 * but adds friction for casual copying.
 */

(function() {
    'use strict';

    // ============================================
    // 1. Disable Right Click Context Menu
    // ============================================
    document.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        return false;
    });

    // ============================================
    // 2. Disable Common Shortcut Keys
    // ============================================
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + U - View Source
        if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
            e.preventDefault();
            return false;
        }
        // Ctrl/Cmd + S - Save Page
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            return false;
        }
        // Ctrl/Cmd + P - Print
        if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
            e.preventDefault();
            return false;
        }
        // Ctrl/Cmd + Shift + I - Developer Tools
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'I') {
            e.preventDefault();
            return false;
        }
        // F12 - Developer Tools
        if (e.key === 'F12') {
            e.preventDefault();
            return false;
        }
        // Ctrl/Cmd + Shift + J - Console
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'J') {
            e.preventDefault();
            return false;
        }
        // Ctrl/Cmd + A - Select All (optional, can be annoying)
        // if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        //     e.preventDefault();
        //     return false;
        // }
    });

    // ============================================
    // 3. Disable Drag and Drop
    // ============================================
    document.addEventListener('dragstart', function(e) {
        e.preventDefault();
        return false;
    });

    // ============================================
    // 4. Disable Copy (Ctrl/Cmd + C)
    // ============================================
    document.addEventListener('copy', function(e) {
        // Allow copying in input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return true;
        }
        e.preventDefault();
        return false;
    });

    // ============================================
    // 5. Anti-Debugger Protection
    // Detects when DevTools is opened
    // ============================================
    (function() {
        const threshold = 160;
        const check = function() {
            const widthThreshold = window.outerWidth - window.innerWidth > threshold;
            const heightThreshold = window.outerHeight - window.innerHeight > threshold;

            if ((widthThreshold || heightThreshold) && window.console && window.console.log) {
                console.clear();
                console.log('%c⚠️', 'font-size: 50px; color: red;');
                console.log('%cPristmax - All Rights Reserved', 'font-size: 20px; color: #333;');
                console.log('%cUnauthorized copying or reproduction of this website content is prohibited.', 'font-size: 14px; color: #666;');
            }
        };

        setInterval(check, 1000);

        // Also check on resize
        window.addEventListener('resize', check);
    })();

    // ============================================
    // 6. Disable Image Saving
    // ============================================
    document.addEventListener('mousedown', function(e) {
        if (e.target.tagName === 'IMG') {
            e.preventDefault();
            return false;
        }
    });

    // ============================================
    // 7. CSS Protection Layer
    // Add to body to prevent selection
    // ============================================
    const style = document.createElement('style');
    style.textContent = `
        body {
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
            user-select: none;
        }
        input, textarea {
            -webkit-user-select: text;
            -moz-user-select: text;
            -ms-user-select: text;
            user-select: text;
        }
        /* Hide content if JS is disabled */
        .no-js { display: none !important; }
    `;
    document.head.appendChild(style);

    // ============================================
    // 8. Obfuscate Email Addresses
    // ============================================
    const obfuscateEmails = function() {
        const emailLinks = document.querySelectorAll('a[href^="mailto:"]');
        emailLinks.forEach(function(link) {
            const email = link.getAttribute('href').replace('mailto:', '');
            // Keep as is but add hover effect
            link.title = 'Pristmax - All Rights Reserved';
        });
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', obfuscateEmails);
    } else {
        obfuscateEmails();
    }

    // ============================================
    // 9. Console Warning on Load
    // ============================================
    console.log('%c⚠️ Pristmax - Code Protection Active', 'color: #666; font-size: 14px;');
    console.log('%cUnauthorized copying or reproduction of this website content is prohibited.', 'color: #999; font-size: 12px;');

})();
