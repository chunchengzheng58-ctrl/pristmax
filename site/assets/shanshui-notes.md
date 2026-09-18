# Footer supplied-art composition — 2026-09-18

Supersedes generated pristine-shanshui artwork. Uses the six user-supplied WHYSL screenshots as requested, converted to WebP for delivery (about 2.6 MB total). Artist lettering remains in the source images. These are supplied reference artworks, not original Pristmax artwork or imagegen output.

The browser crops only the phone UI through overflow-hidden frames. Six overlapping masked panels form a blue/gold panorama. Scroll progress controls each panel's upward translation, scale and opacity, with staggered timing; scrolling back reverses it. On phones the panorama also pans horizontally. Reduced-motion uses a static composition. Without JS the artwork is visible.

Sources: six codex-clipboard JPG files supplied in the conversation. Original generated asset is no longer referenced by the homepage. To update this composition, edit site/index.html, site/motion.css and site/motion.js. Publish all six assets/landscape-panel-*.webp before updating HTML. Publish site/ only. GitHub Pages builds via existing workflow; server mirror is /var/www/pristmax. Do not deploy backend directories.

Validation: desktop 1440x1000 and mobile 390x844, image loads, no horizontal overflow, scroll transforms change, reduced motion disables movement.
