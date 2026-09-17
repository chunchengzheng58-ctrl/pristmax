# Pristmax public website

Independent static product website. No API connection, file upload, analytics, external fonts or CDN dependencies.

Preview from repository root:

```powershell
python -m http.server 8780 --bind 127.0.0.1 --directory site
```

Open http://127.0.0.1:8780 . Product console remains separate in `unified/web`; do not deploy the repository root as the public site.

Before public release: confirm repository URL, license, platform support and release artifacts/checksums. Replace pending-release status only when real artifacts exist. No fabricated download links or savings figures.

Brand: selected provisional three-surface mark. Colors #173D58 ink, #477F9F glacier, #F4F9FC paper. Serif typography for editorial headings; lining/tabular sans-serif figures for metrics.


## GitHub Pages

Public repository: https://github.com/chunchengzheng58-ctrl/pristmax
Pages: https://chunchengzheng58-ctrl.github.io/pristmax/

`.github/workflows/pages.yml` publishes only `site/` when it changes on main. Pages source must be GitHub Actions. All asset URLs are relative so the /pristmax/ prefix works. The old docs/CNAME is not part of the published artifact. Existing jiangchenghehe.top remains served by Nginx until a deliberate DNS migration.

The site is static; Pages does not run the Python product/API. Do not upload customer data, backend configs, or credentials to this directory. Pending release badges remain until a real release exists. Current repository license restrictions must be reconciled separately before claiming standard open-source licensing.

UI repair 2026-09-17: removed broken ../design.js and third-party scrolling dependency, added matching home.css, mobile menu and direct GitHub links. Product backend edits were deliberately excluded.
