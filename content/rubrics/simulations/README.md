# Simulation rubrics — reserved

The `rubric_ref` paths in `content/personas/*.yaml` point here
(`rubrics/simulations/<persona>.yaml`). Those files do not exist yet:
simulation scoring runs today from the inline `scoring.criteria` in each
persona file (see `platform/grading/simulation/engine.py`
`conclude_and_score_simulation`), with a built-in fallback when a persona
lists none.

When the simulation content track (C5) promotes scoring to file-based
rubrics, author them at exactly these paths so the existing refs resolve
without touching the persona files. Until then, do not invent files here
to "complete" the directory — an unreferenced rubric is worse than a
reserved path, because the engine would ignore it while readers assume it
grades.
