"""Generate deterministic synthetic fixtures for REPORT section 26 gate scenarios.

This module only imports the repository self-contained linkage-surface regression
helpers; it does not read Mojang jars, official mappings or third-party mod jars.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEST = ROOT / "tools" / "test_linkage_surface.py"


def load():
    spec = importlib.util.spec_from_file_location("mcport_linkage_fixture", str(TEST))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: linkage_fixtures.py OUT_DIR")
    x = load()
    d = pathlib.Path(sys.argv[1])
    d.mkdir(parents=True, exist_ok=True)
    x.write_lines(d / "decl.tsv", x.SIMPLE_DECL)
    x.write_lines(d / "decl2.tsv", [
        "C\tnet/minecraft/A",
        "C\tnet/minecraft/B",
        "M\tnet/minecraft/B\tmoved\t(Lnet/minecraft/B;)V",
    ])
    x.write_lines(d / "map.tsv", ["C\tnet/minecraft/Old\tnet/minecraft/B"])
    x.write_lines(d / "badmap.tsv", ["C\tnet/minecraft/Old\tnet/minecraft/Missing"])
    x.mkjar(d / "good.jar", {"t/Fixture.class": x.build_simple()})
    x.mkjar(d / "framework.jar", {"t/Fixture.class": x.build_framework()})
    x.mkjar(d / "dynamic.jar", {"t/Fixture.class": x.build_dynamic()})
    x.mkjar(d / "third.jar", {"t/Fixture.class": x.build_third_party()})
    x.mkjar(d / "rename.jar", {"t/Fixture.class": x.build_rename()})
    x.mkjar(d / "full.jar", {"t/Fixture.class": x.build_full()})
    x.mkjar(d / "empty.jar", {"t/Fixture.class": x.build_empty()})
    print("FIXTURES_OK")


if __name__ == "__main__":
    sys.exit(main())
