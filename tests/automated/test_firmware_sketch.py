"""Guards on the ESP32 sketch that a Python test can check without a
compiler.

These exist because the Arduino builder does not compile a .ino as
plain C++. It rewrites the file first, and one of its rewrites turns
valid C++ into a sketch that will not build - with an error pointing at
a line that is perfectly fine.
"""

import re
from pathlib import Path

import pytest

SKETCH = (Path(__file__).resolve().parents[2]
          / "firmware" / "assistive_node" / "assistive_node.ino")

FUNCTION_DEFINITION = re.compile(
    r"^((?:inline\s+|static\s+)?[A-Za-z_][\w:]*\s*[*&]?\s+)"
    r"([A-Za-z_]\w*)\s*\(([^;{)]*)\)\s*\{",
    re.MULTILINE,
)

TYPE_DEFINITION = re.compile(r"^(?:struct|enum)\s+(\w+)", re.MULTILINE)


@pytest.fixture(scope="module")
def sketch():
    if not SKETCH.exists():
        pytest.skip("firmware sketch is not present")
    return SKETCH.read_text(encoding="utf-8")


def test_prototypes_cannot_outrun_the_types_they_name(sketch):
    """The builder injects a prototype for every function in the sketch,
    placing them all immediately above the FIRST function definition it
    finds. So every user-defined type named in any function signature
    must be declared above that first function - otherwise a prototype
    refers to a type that does not exist yet and the sketch fails with

        error: 'Device' does not name a type

    against a line that is perfectly valid C++.

    Only types actually named in a signature matter; `Completed` is
    declared lower down and is fine, because nothing takes one as an
    argument.
    """

    functions = list(FUNCTION_DEFINITION.finditer(sketch))
    assert functions, "no function definitions found - has the sketch moved?"
    first = functions[0]

    declared = {m.group(1): m.start() for m in TYPE_DEFINITION.finditer(sketch)}
    assert declared, "no struct/enum definitions found - has the sketch moved?"

    for function in functions:
        signature = function.group(1) + function.group(3)
        for name in re.findall(r"\b[A-Z]\w+\b", signature):
            if name not in declared or declared[name] < first.start():
                continue
            pytest.fail(
                f"{function.group(2)}() names '{name}', which is declared at "
                f"line {sketch[:declared[name]].count(chr(10)) + 1}, below the "
                f"first function {first.group(2)}() at line "
                f"{sketch[:first.start()].count(chr(10)) + 1}. Every prototype "
                f"is injected above that line, so this will not compile. "
                f"Move {first.group(2)}() below '{name}'."
            )


def test_relay_kinds_do_not_share_actions(sketch):
    """A light must refuse TV actions and a TV must refuse light ones.

    Both are the same pin electrically, so only the device table
    distinguishes them. When one RELAY kind handled both, sleep_light
    answered "success" to TV_ON and the application committed a state
    change for hardware that never moved.
    """

    body = sketch[sketch.index("case RELAY_LIGHT:"):sketch.index("case BUZZER:")]
    light, tv = body.split("case RELAY_TV:")

    assert "TV_ON" not in light and "TV_OFF" not in light, \
        "RELAY_LIGHT accepts a TV action"
    assert "LIGHT_ON" not in tv and "LIGHT_OFF" not in tv, \
        "RELAY_TV accepts a light action"


def test_json_document_type_works_on_both_arduinojson_majors(sketch):
    """Library Manager installs ArduinoJson 7, which removed
    StaticJsonDocument; v6 has no plain JsonDocument. The sketch must
    pick per version rather than pinning one and breaking the other.
    """

    assert "ARDUINOJSON_VERSION_MAJOR" in sketch
    assert "JsonDocument name" in sketch
    assert "StaticJsonDocument<capacity> name" in sketch
    assert re.search(r"^\s*StaticJsonDocument<\d+>\s+doc;", sketch, re.M) is None, \
        "a raw StaticJsonDocument survives; it will not compile against v7"
