# PPT Master native runtime

`python -B runner.py PROJECT OUTPUT [--validate-only]`

Reads `PROJECT/svg_output/*.svg` in filename order and optional `notes/<same-stem>.md`.
SVG pages use the `0 0 1280 720` viewBox. Only self-contained basic SVG is accepted;
images must be embedded PNG/JPEG data URLs. No shell, network, image generation,
external file references, templates, or model credentials are used.

Optional `plan.json` has `pages`, matching the SVG page order and count. A page may
provide `chart: {title, unit, categories: [string], values: [number], box: [x,y,w,h]}`.
These explicit values produce an editable PowerPoint column chart and embedded
workbook. The adapter never supplies missing numeric data.
Optional `plan.design` supplies the platform's `font`, `background`, `ink`,
`muted`, and `accent` (`#RRGGBB`) values for charts. Chart titles use 24 pt;
axis labels, data labels, and unit titles use 20 pt with explicit font/colors.

Stdout is one JSON object. Exit 0 reports validated sources, exact source/runtime
hashes, upstream checker warnings, actual slide/shape/connector/chart/image/media
counts and the resulting file hash. Exit 1 reports an error and retains an existing
output file. `--validate-only` creates no output. It checks SVG/chart inputs; the
actual native conversion is still required to establish export success.

The unmodified upstream files in `upstream/` match commit
`d6f6cdfa97eaafd73b9cc2b0343b94a9f3998fc4` of
https://github.com/hugohe3/ppt-master (2026-06-08), under the included MIT license.
`SOURCES.json` records every exact-byte SHA256 and verified upstream Git blob SHA1.
Only the exporter/checker dependency closure is included (about 420 KB), with no
template/icon assets or external service integrations. Dependencies: python-pptx
and its installed dependencies, Pillow for checking embedded image input.

The adapter forces upstream native DrawingML mode, disables raster compatibility
mode, and fails on unsupported conversion. It then promotes upstream `Line` shapes
to equivalent editable OOXML connectors and optionally inserts explicit native
charts. This post-processing lives in the adapter, leaving upstream files intact.
No whole-slide bitmap fallback is used. Counts describe file structure, not visual
quality or content approval.

Run `python -B test_runtime.py` for native text/path/shapes, connectors, notes,
multiple pages, embedded pictures, an editable chart/workbook, and input rejection.
