# cutout-extra

Background-removed cut-outs (`<stem>.png`, 520x520 transparent PNG) for players whose only photo in this repo still had its studio or arena background, so head-uniform excluded them ("no transparency") and they had no face-fill headshot. Made from `face2/<stem>.png` with [rembg](https://github.com/danielgatis/rembg) (MIT) and its u2net model (Apache-2.0) plus rembg's alpha matting (pymatting, MIT), run locally: no paid service, no key. Only the main blob is kept.

`<stem>.webp` is each cut-out framed exactly like `head-uniform-480/` (same MediaPipe eye landmarks, eye line, eye distance and hair fix), with its record in `.hashes.json`. `scripts/build_face_fill.py` reads this folder as its third source, after head-uniform-sharp and head-uniform-480.

Built by `scripts/build_cutout_extra.py` (Oct 28 2026: 467-jason-kidd, 77141-dennis-johnson, 77480-slater-martin, 920-ac-green). The framing step reruns in `.github/workflows/cutout-extra.yml` when a cut-out changes. Nothing outside this folder is written.
