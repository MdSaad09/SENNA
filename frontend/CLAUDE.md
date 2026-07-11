# frontend/ — React 18 + R3F 8

- The pins are law: react 18.3 with @react-three/fiber ^8, drei ^9, and three at the
  exact version in package.json. Never upgrade to React 19 / R3F 9 here — it is the
  most common R3F install failure (spec 5.9.1).
- One canvas mounted at a time. Views are routes, and navigating unmounts (F-28).
- 22 cars means one InstancedMesh with per-instance colour. Drei Html labels: four,
  maximum — selected car plus podium; everyone else is instanced sprite text.
- Every number on screen came from the API. No client-side physics, ever
  (5.1, invariant 2). The dev overlay traces each figure to its API response id.
- Generic liveries only — team colour plus three-letter driver codes; no sponsor or
  team marks (F-29), and the unofficial-project footer stays (R-07).
- Handle webglcontextlost / webglcontextrestored with the reload overlay (E-18). Bloom
  sits behind the quality toggle, default off below the GPU heuristic.
- The perf budget (5.10.3) is a test target, not an aspiration: <= 150 draw calls in
  replay, <= 4 Html labels, 45 fps floor on a GTX 1660-class trace.
