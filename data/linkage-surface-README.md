# linkage-surface summary data

These rows are compact evidence for the linkage-surface audit introduced in REPORT section 26 (McPort 0.2.7). The JSON and CSV are deterministic: no timestamps, no host paths in the CSV, no third-party mod jars, Mojang jars, or official mappings are redistributed.

Scope is deliberately narrow: CONSTANT_MethodHandle (JVMS 4.4.8 / 5.4.3.5), CONSTANT_Dynamic and InvokeDynamic bootstrap edges (JVMS 4.7.23 / 5.4.3.6), plus framework-resolved annotation class literals (JVMS 4.7.16.1). Framework class literals are reported as FRAMEWORK_UNRESOLVED and never treated as a silent PASS.

The canonical command shape is in spec.example.json. The CSV header is data/linkage-surface-summary.csv; each invocation appends one row. Status names follow tools/linkage_surface.py exactly.
