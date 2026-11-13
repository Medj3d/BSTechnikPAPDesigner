"""Assembler für den PIC16F887 (Schulvorlage start.asm).

Aufbau und Befehle werden immer geprüft. Sind ``gpasm`` und ``gpsim`` (gputils) installiert – im Linux-Workflow der
Fall –, wird der erzeugte Code zusätzlich übersetzt und im Simulator ausgeführt; die Werte der Variablen müssen dann
genau stimmen (8 Bit ohne Vorzeichen).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

from app.analysis.ast import Action, Block, Break, DoWhileLoop, If, LimitLoop, Loop, Program, WhileLoop
from app.codegen.generators import LANGUAGES, generate
from app.codegen.pic_asm import PicAsmGenerator, ascii_comment, symbol

_counter = [0]


def act(text, kind="process"):
    _counter[0] += 1
    return Action(kind=kind, text=text, element_id=f"e{_counter[0]}")


def when(condition, then, otherwise=None):
    _counter[0] += 1
    return If(condition=condition, element_id=f"i{_counter[0]}", then_block=Block([act(then)]),
              else_block=Block([act(otherwise)] if otherwise else []))


def program(*stmts, name="Test"):
    return Program(name=name, start_id="s", end_id="x", end_text="Ende", body=Block(list(stmts)))


def asm(*stmts) -> str:
    return PicAsmGenerator([program(*stmts)]).generate()


# ------------------------------------------------------------------ Aufbau
def test_assembler_is_the_default_code_language():
    assert list(LANGUAGES)[0] == "asm"
    from app.codegen.dialog import CodeDialog, EXTENSIONS
    import inspect
    assert inspect.signature(CodeDialog.__init__).parameters["language"].default == "asm"
    assert EXTENSIONS["asm"][0] == ".asm"


def test_layout_follows_the_school_template():
    code = asm(act("x = 5"), act("Ausgabe x", "output"))
    for part in ("; Projektname\t    : Test", "; Prozessor\t    : 16F887 / 4 Mhz", "; Beschaltung PORTD : Ausgabe",
                 "\tlist\tp=16F887", "\t#include\t<p16f887.inc>", "\terrorlevel -302", "\terrorlevel -305",
                 "\t__CONFIG    _CONFIG1, 0x20E4", "\t__CONFIG    _CONFIG2, 0xFFFF", "\tcblock\t0x20", "\tendc",
                 "\torg\t0x00", "; Hardwarekonfiguration - (setup)", "; Hauptprogramm - (loop)",
                 "; Unterprogramme - (Funktionen)", "\nmain\n", "\nende\n"):
        assert part in code, part
    assert code.rstrip().endswith("end")
    assert code.index("cblock") < code.index("org") < code.index("\nmain\n") < code.index("\nende\n")
    # jeder Schritt steht als Kommentar über seinen Befehlen
    assert "\t; x = 5\n\tMOVLW\td'5'\n\tMOVWF\tx" in code
    assert "\tMOVF\tx, W\n\tMOVWF\tPORTD" in code and "CLRF\tTRISD" in code


def test_short_forms_and_bits():
    code = asm(act("zahl = 0"), act("zahl = zahl + 1"), act("zahl = zahl - 1"), act("PORTD.0 = 1"),
               act("PORTC,7 = 0"), act("warte 100 ms"), act("warte 2 s"))
    assert "\tCLRF\tzahl" in code and "\tINCF\tzahl, F" in code and "\tDECF\tzahl, F" in code
    assert "\tCLRF\tv_z" in asm(act("z = 0"))   # Z ist ein STATUS-Bit des Assemblers
    assert "\tBSF\tPORTD, 0" in code and "\tBCF\tPORTC, 7" in code
    assert "\tMOVLW\td'100'\n\tCALL\twarte_ms" in code and "\nwarte_ms\n" in code
    assert "\tCALL\twarte_s" in code and "\nwarte_s\n" in code


def test_names_are_valid_for_mpasm():
    assert symbol("Größe") == "Groesse" and symbol("2tes") == "v_2tes"
    code = asm(act("w = 3"), act("c = w + 1"), act("Länge = 4"))
    # W, C sind Kurzformen des Assemblers – die Variablen heißen dort anders
    assert "\tv_w\n" in code and "\tv_c\n" in code and "\tLaenge\n" in code
    assert "MOVWF\tw\n" not in code


def test_what_cannot_be_translated_is_marked():
    code = asm(act('name = "Anna"'), act("x = 2,5"), act("Ausgabe „Hallo“", "output"), act("y = 300"))
    assert code.count("TODO") >= 4
    when_text = asm(when("Taster gedrückt?", "x = 1"))
    assert "BTFSC\tPORTB, 0" in when_text or "BTFSS\tPORTB, 0" in when_text
    assert "als Bit-Test formulieren" in when_text


def test_comments_stay_readable_in_old_mplab():
    assert ascii_comment("a ≠ b, „Text“ – x ≤ 3") == 'a <> b, "Text" - x <= 3'
    assert ascii_comment("Größe") == "Größe"   # Umlaute kennt Windows-1252
    code = asm(when("a ≠ 3", "a = 1"))
    code.encode("cp1252")


def test_ports_are_configured_as_they_are_used():
    # einzelnes Bit gesetzt -> nur dieses Bit ist Ausgang; „Ausgabe an PORTC“ -> TRISC = 0
    code = asm(act("PORTD.0 = 1"))
    assert "\tMOVLW\tb'11111110'\n\tMOVWF\tTRISD" in code and "\tCLRF\tPORTD" in code
    code = asm(act("x = 3"), act("Ausgabe x an PORTC", "output"))
    assert "\tCLRF\tTRISC" in code and "TRISD" not in code and "; Beschaltung PORTC : Ausgabe" in code
    code = asm(act("Eingabe x von PORTA", "input"), act("Ausgabe x", "output"))
    assert "\tMOVLW\tb'11111111'\n\tMOVWF\tTRISA" in code and "\tCLRF\tTRISD" in code
    assert "; Beschaltung PORTA : Eingabe" in code and "; TODO" not in code   # Eingaben sind Zahlen
    assert "\tMOVF\tPORTA, W" in code and "\tMOVF\tx, W\n\tMOVWF\tPORTD" in code
    # ohne Ports kein leeres „BANKSEL TRISx“, aber immer zurück zu Bank 0 (ANSEL liegt in Bank 3)
    code = asm(act("x = 3"))
    assert "BANKSEL\tTRIS" not in code and "\tBANKSEL\tPORTA" in code


def test_registers_of_other_banks_get_banksel():
    code = asm(act("TRISB = 15"), act("OPTION_REG.7 = 0"), act("x = TRISB + 1"), when("TRISB.0", "y = 1"))
    assert "\tMOVLW\td'15'\n\tBANKSEL\tTRISB\n\tMOVWF\tTRISB\n\tBANKSEL\tPORTA" in code
    assert "\tBANKSEL\tOPTION_REG\n\tBCF\tOPTION_REG, 7\n\tBANKSEL\tPORTA" in code
    assert "\tBANKSEL\tTRISB\n\tMOVF\tTRISB, W\n\tBANKSEL\tPORTA" in code
    # Bit-Test über eine Kopie in Bank 0, damit der Sprung nicht in Bank 1 landet
    assert "\tMOVWF\thilf1\n\tBTFSS\thilf1, 0" in code
    # Bank-0-Register bleiben ohne BANKSEL
    assert "BANKSEL\tPORTD\n" not in asm(act("PORTD = 1"))


def test_xor_and_bit_masks_in_conditions():
    code = asm(act("a = 7"), act("x = a ^ 6"), when("(a & 3) = 3", "y = 1"), act("Ausgabe a & 3", "output"))
    assert "\tXORLW\td'6'" in code and "**" not in code
    assert "; TODO" not in code and "\tANDLW\td'3'" in code


def test_own_labels_are_not_used_as_variables():
    code = asm(act("ende = 3"), act("mul8 = ende * 2"), act("main = 1"), act("warte_ms = 2"), act("sonst_1 = 4"),
               act("hilf1 = 5"))
    for name in ("ende", "mul8", "main", "warte_ms", "sonst_1", "hilf1"):
        assert f"\tv_{name}\n" in code, name
    assert "\nende\n" in code and "\nmul8\n" in code


def test_traced_lines_point_to_blocks():
    from app.codegen.generators import generate_traced
    prog = program(act("x = 5"), when("x > 3", "y = 1", "y = 2"))
    code, ids = generate_traced([prog], "asm")
    assert code == generate([prog], "asm")
    lines = code.split("\n")
    rows = [row for row, eid in enumerate(ids) if eid == prog.body.statements[0].element_id]
    assert rows and any("MOVWF\tx" in lines[row] for row in rows)


# ------------------------------------------------------------------ im Simulator
CASES = {
    "rechnen": (program(act("a = 7"), act("b = 5"), act("c = a + b"), act("d = a - b"), act("e = a * b"),
                        act("f = a / b"), act("g = a mod b"), act("h = (a + b) * 2 - c"), act("w = b - a"),
                        act("q = a << 2"), act("r = 200 >> 3"), act("t = a & 6"), act("u = a | 8"),
                        act("k = 100 / (a - 2)"), act("m = a * b * 2 + 1"), act("n = 255 + 1"),
                        act("o = (a - b) * (a + b)"), act("p = 0"), act("p = p + 1"), act("s = 9 - a")),
                dict(c=12, d=2, e=35, f=1, g=2, h=12, w=254, q=28, r=25, t=6, u=15, k=20, m=71, n=0, o=24, p=1,
                     s=2)),
    "vergleiche": (program(act("a = 7"), act("b = 5"),
                           when("a > b", "x1 = 1", "x1 = 2"), when("a < b", "x2 = 1", "x2 = 2"),
                           when("a >= 7", "x3 = 1", "x3 = 2"), when("a <= 6", "x4 = 1", "x4 = 2"),
                           when("a = 7", "x5 = 1", "x5 = 2"), when("a ≠ b", "x6 = 1", "x6 = 2"),
                           when("a > 3 und b < 6", "x7 = 1", "x7 = 2"), when("a < 3 oder b = 5", "x8 = 1", "x8 = 2"),
                           when("nicht (a = 7)", "x9 = 1", "x9 = 2"), when("b <= 5", "y1 = 1", "y1 = 2"),
                           when("b >= 6", "y2 = 1", "y2 = 2"), when("3 < a", "y3 = 1"),
                           when("a - b > 1", "y4 = 1", "y4 = 2"), when("a = b", "y5 = 1", "y5 = 2"),
                           when("a > 7", "y6 = 1", "y6 = 2"), when("a < 3 oder b > 9", "y7 = 1", "y7 = 2"),
                           when("a > 3 und b > 9", "y8 = 1", "y8 = 2")),
                   dict(x1=1, x2=2, x3=1, x4=2, x5=1, x6=1, x7=1, x8=1, x9=2, y1=1, y2=2, y3=1, y4=1, y5=2, y6=2,
                        y7=2, y8=2)),
    "schleifen": (program(act("s = 0"), act("i = 1"),
                          WhileLoop(condition="i <= 10", element_id="w1",
                                    body=Block([act("s = s + i"), act("i = i + 1")])),
                          act("p = 0"),
                          LimitLoop(header="Für j = 1 bis 5", footer="", begin_id="l1", end_id="l2",
                                    body=Block([act("p = p + j")])),
                          act("n = 0"),
                          LimitLoop(header="3 mal", footer="", begin_id="l3", end_id="l4",
                                    body=Block([act("n = n + 2")])),
                          act("k = 0"),
                          DoWhileLoop(condition="k >= 10", element_id="d1", body=Block([act("k = k + 3")]),
                                      negate=True),
                          act("z = 0"),
                          LimitLoop(header="Für v = 10 bis 2 Schritt -2", footer="", begin_id="l5", end_id="l6",
                                    body=Block([act("z = z + 1")])),
                          act("g = 0"),
                          Loop(element_id="o1", body=Block([act("g = g + 1"),
                                                            If(condition="g = 4", element_id="o2",
                                                               then_block=Block([Break(element_id="o3")]),
                                                               else_block=Block([]))])),
                          act("h = 0"),
                          LimitLoop(header="solange h < 6", footer="", begin_id="l7", end_id="l8",
                                    body=Block([act("h = h + 4")]))),
                  dict(s=55, i=11, p=15, n=6, k=12, z=5, g=4, h=8)),
    # 8 Bit ohne Vorzeichen: Zählschleifen bis 0 und bis 255 und Schritte über die Grenze enden trotzdem
    "grenzen": (program(act("c1 = 0"),
                        LimitLoop(header="Für i = 10 bis 0 Schritt -1", footer="", begin_id="g1", end_id="g2",
                                  body=Block([act("c1 = c1 + 1")])),
                        act("c2 = 0"),
                        LimitLoop(header="Für j = 250 bis 255", footer="", begin_id="g3", end_id="g4",
                                  body=Block([act("c2 = c2 + 1")])),
                        act("c3 = 0"),
                        LimitLoop(header="Für k = 9 bis 0 Schritt -2", footer="", begin_id="g5", end_id="g6",
                                  body=Block([act("c3 = c3 + 1")])),
                        act("c4 = 0"),
                        LimitLoop(header="Für m = 3 bis 1", footer="", begin_id="g7", end_id="g8",
                                  body=Block([act("c4 = c4 + 1")])),
                        act("c5 = 0"),
                        LimitLoop(header="Für q = 240 bis 255 Schritt 7", footer="", begin_id="g9", end_id="g10",
                                  body=Block([act("c5 = c5 + 1")]))),
                dict(c1=11, c2=6, c3=5, c4=0, c5=3)),
    # Bitoperationen, Register anderer Bänke, Ports und Namen, die der Erzeuger selbst benutzt
    "register": (program(act("a = 7"), act("x = a ^ 6"), when("(a & 3) = 3", "y = 1", "y = 2"),
                         act("PR2 = 77"), act("PR2.1 = 1"), act("o = PR2"), when("PR2.0", "b = 4", "b = 9"),
                         act("PORTA.1 = 1"), act("Ausgabe a an PORTC", "output"),
                         act("Ausgabe a & 3 an PORTB", "output"), act("ende = 3"), act("mul8 = ende * 2")),
                 dict(x=1, y=1, o=79, b=4, ende=3, mul8=6, PORTA=2, PORTB=3, PORTC=7)),
    "bits": (program(act("PORTD.0 = 1"), act("PORTD.3 = 1"), act("PORTD.3 = 0"),
                     when("PORTD.0 = 1", "y = 4", "y = 9"), when("PORTD.0 = 0", "q = 4", "q = 9"),
                     when("PORTD.0", "r = 4", "r = 9"), when("PORTD.3 ≠ 0", "s = 4", "s = 9"),
                     act("Ausgabe y", "output"), act("warte 2 ms")),
             dict(y=4, q=9, r=4, s=9, PORTD=4)),
    "unterprogramm": ([program(act("x = 3"), act("verdoppeln", "subprogram"), act("verdoppeln", "subprogram"),
                               act("y = x + 1")),
                       program(act("x = x * 2"), name="verdoppeln")],
                      dict(x=12, y=13)),
}

needs_gputils = pytest.mark.skipif(not (shutil.which("gpasm") and shutil.which("gpsim")),
                                   reason="gputils/gpsim nicht installiert")


@needs_gputils
@pytest.mark.parametrize("name", list(CASES))
def test_generated_code_runs_correctly_in_the_simulator(name, tmp_path):
    prog, expected = CASES[name]
    generator = PicAsmGenerator(prog if isinstance(prog, list) else [prog])
    code = generator.generate()
    (tmp_path / "prog.asm").write_text(code, encoding="cp1252")
    block = code.split("cblock\t0x20")[1].split("endc")[0].split()
    address = {var: (5 + "ABCDE".index(var[-1]) if var.startswith("PORT") else 0x20 + block.index(generator.var(var)))
               for var in expected}
    # „dump“ zeigt den Speicher in gpsim 0.31 (Ubuntu 22.04, GitHub-Runner) und 0.32 gleich („x 0x22“ nur in 0.32)
    (tmp_path / "prog.stc").write_text("break e ende\nrun\ndump\nquit\n")
    assembled = subprocess.run(["gpasm", "-o", "prog.hex", "prog.asm"], cwd=tmp_path, capture_output=True, text=True)
    assert assembled.returncode == 0 and "Error" not in assembled.stdout, assembled.stdout
    result = subprocess.run(["gpsim", "-i", "-s", "prog.cod", "-c", "prog.stc"], cwd=tmp_path, capture_output=True,
                            text=True, timeout=120)
    output = result.stdout + result.stderr
    assert "Hit a Breakpoint" in output, output[-2000:]
    memory = {}
    for row in re.finditer(r"^([0-9a-f]{4}):\s+((?:[0-9a-f-]{2} ){16})", output, re.MULTILINE):
        for offset, cell in enumerate(row.group(2).split()):
            if cell != "--":
                memory[int(row.group(1), 16) + offset] = int(cell, 16)
    for var, want in expected.items():
        assert memory.get(address[var]) == want, (var, memory.get(address[var]), want)


@needs_gputils
def test_examples_assemble_without_errors(qapp, tmp_path):
    from app.analysis.structure import structure_diagram
    from app.document import DiagramDocument
    from app.fileformat.serializer import load_diagram

    folder = os.path.join(os.path.dirname(__file__), os.pardir, "assets", "examples")
    for index, name in enumerate(sorted(os.listdir(folder))):
        document = DiagramDocument(load_diagram(os.path.join(folder, name)).diagram)
        code = generate(structure_diagram(document.flow_graph()), "asm", document.meta.name)
        path = tmp_path / f"beispiel{index}.asm"
        path.write_text(code, encoding="cp1252")
        result = subprocess.run(["gpasm", "-o", f"beispiel{index}.hex", path.name], cwd=tmp_path,
                                capture_output=True, text=True)
        assert result.returncode == 0 and "Error" not in result.stdout, (name, result.stdout)
