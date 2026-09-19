# Footer continuous composition — 2026-09-18

Latest version supersedes the six-panel layout below. Built-in imagegen recomposed supplied reference paintings into landscape-continuous.webp (2172 × 724), removing screenshot UI and all lettering, harmonizing ridges, river and pigment textures. This is AI-assisted recomposition of supplied references, not literal stitching. One image moves as a whole so scroll effects cannot split the joins. Publish landscape-continuous.webp before HTML. Earlier six-panel assets are no longer used by the homepage.

## Final prompt

Intelligently composite the supplied supplied blue-and-gold Chinese landscape paintings into ONE seamless horizontal panoramic painting, 3:1 aspect ratio. The inputs are phone screenshots: remove ALL phone interface, margins, ALL typography, signatures, logos, watermarks and text from the artwork. Preserve their specific intense ultramarine/cobalt mineral blue pigment, brilliant rich gold leaf mountains and gold fine hand-drawn outlines, flattened ornamental gongbi brushwork and textured paper. This must look like the supplied PAINTINGS, absolutely not a photorealistic grey mountain render. Integrate their pavilions, slender gold pine trees, layered ridges and river into a single continuous coherent landscape with one winding connected river across the lower third, naturally connected mountain ridgelines and mist across ALL transitions. Repaint joins intelligently: no vertical seams, no six columns, no duplicated repeated motifs, no blur strips. Arrange a few pavilions at varied distances within the panorama and connect them with riverbanks and paths. Dense fine hand-painted texture, flat decorative gold mountain silhouettes against ultramarine, luxurious blue and gold throughout. Full bleed landscape edge to edge, no border or phone UI. The top edge has a narrow deep indigo sky transitioning into gold ridges, not large empty space. Final image contains ZERO letters or text anywhere. Use the actual visual motifs and paint treatment of the supplied images and harmonize their scales into a single long handscroll.

## Superseded implementation

Supersedes generated pristine-shanshui artwork. Uses the six user-supplied WHYSL screenshots as requested, converted to WebP for delivery (about 2.6 MB total). Artist lettering remains in the source images. These are supplied reference artworks, not original Pristmax artwork or imagegen output.

The browser crops only the phone UI through overflow-hidden frames. Six overlapping masked panels form a blue/gold panorama. Scroll progress controls each panel's upward translation, scale and opacity, with staggered timing; scrolling back reverses it. On phones the panorama also pans horizontally. Reduced-motion uses a static composition. Without JS the artwork is visible.

Sources: six codex-clipboard JPG files supplied in the conversation. Original generated asset is no longer referenced by the homepage. To update this composition, edit site/index.html, site/motion.css and site/motion.js. Publish all six assets/landscape-panel-*.webp before updating HTML. Publish site/ only. GitHub Pages builds via existing workflow; server mirror is /var/www/pristmax. Do not deploy backend directories.

Validation: desktop 1440x1000 and mobile 390x844, image loads, no horizontal overflow, scroll transforms change, reduced motion disables movement.
