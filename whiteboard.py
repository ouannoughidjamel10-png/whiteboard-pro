#!/usr/bin/env python3
"""Interactive Whiteboard - professional drawing app with vector infinite canvas."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import pickle
import random
import sys
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk, colorchooser, filedialog, messagebox, simpledialog

try:
    import sympy as sp

    HAS_SYMPY = True
except Exception:  # pragma: no cover
    HAS_SYMPY = False

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import imageio

    HAS_IMAGEIO = True
except Exception:  # pragma: no cover
    HAS_IMAGEIO = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    HAS_ARABIC_SHAPING = True
except Exception:  # pragma: no cover
    HAS_ARABIC_SHAPING = False

try:
    import pymupdf as _pymupdf

    HAS_PYMUPDF = True
except Exception:  # pragma: no cover
    try:
        import fitz as _pymupdf

        HAS_PYMUPDF = True
    except Exception:
        _pymupdf = None
        HAS_PYMUPDF = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as _rl_canvas
    from reportlab.pdfbase import pdfmetrics as _rl_metrics
    from reportlab.pdfbase.ttfonts import TTFont as _RLTTFont

    HAS_REPORTLAB = True
except Exception:  # pragma: no cover
    HAS_REPORTLAB = False

from PIL import Image, ImageDraw, ImageFont, ImageTk


DEFAULT_FG = "#000000"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
UNDO_LIMIT = 30
GRID_SIZE = 20
MAX_ZOOM = 10.0
MIN_ZOOM = 0.05
REC_FPS = 30

FONT_CANDIDATES = [
    "segoeui.ttf",
    "arial.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
    "FreeSans.ttf",
    "NotoSans-Regular.ttf",
]

BG_LABELS = {
    "plain": "Whiteboard",
    "grid": "Coordinate grid",
    "dots": "Dot grid",
    "lined": "Lined",
    "iso": "Isometric",
    "dark": "Blackboard",
    "image": "Image",
}

THEMES = {
    "light": {
        "bg": (255, 255, 255),
        "fg": "#000000",
        "ui_bg": "#f5f5f5",
        "ui_fg": "#000000",
        "accent": "#2196f3",
        "select": "#bbdefb",
        "button": "#ffffff",
        "button_active": "#e3f2fd",
        "grid": "#e0e0e0",
        "axis": "#b0b0b0",
    },
    "dark": {
        "bg": (38, 50, 56),
        "fg": "#ffffff",
        "ui_bg": "#263238",
        "ui_fg": "#eceff1",
        "accent": "#29b6f6",
        "select": "#1565c0",
        "button": "#37474f",
        "button_active": "#455a64",
        "grid": "#455a64",
        "axis": "#78909c",
    },
}


PERIODIC_TABLE: list[tuple[str, str, int]] = [
    ("H", "Hydrogen", 1), ("He", "Helium", 2), ("Li", "Lithium", 3), ("Be", "Beryllium", 4),
    ("B", "Boron", 5), ("C", "Carbon", 6), ("N", "Nitrogen", 7), ("O", "Oxygen", 8),
    ("F", "Fluorine", 9), ("Ne", "Neon", 10), ("Na", "Sodium", 11), ("Mg", "Magnesium", 12),
    ("Al", "Aluminium", 13), ("Si", "Silicon", 14), ("P", "Phosphorus", 15), ("S", "Sulfur", 16),
    ("Cl", "Chlorine", 17), ("Ar", "Argon", 18), ("K", "Potassium", 19), ("Ca", "Calcium", 20),
    ("Sc", "Scandium", 21), ("Ti", "Titanium", 22), ("V", "Vanadium", 23), ("Cr", "Chromium", 24),
    ("Mn", "Manganese", 25), ("Fe", "Iron", 26), ("Co", "Cobalt", 27), ("Ni", "Nickel", 28),
    ("Cu", "Copper", 29), ("Zn", "Zinc", 30), ("Ga", "Gallium", 31), ("Ge", "Germanium", 32),
    ("As", "Arsenic", 33), ("Se", "Selenium", 34), ("Br", "Bromine", 35), ("Kr", "Krypton", 36),
]


def hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert a hex colour string to an RGBA tuple."""
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (r, g, b, alpha)


def _image_to_bytes(img: Image.Image) -> bytes:
    """Serialize a PIL image to PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: list[int], radius: int, fill, outline=None, width: int = 1) -> None:
    """Draw a rounded rectangle on an image."""
    x1, y1, x2, y2 = xy
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline, width=width)


def _shape_bidi_text(text: str) -> str:
    """Reshape and reorder Arabic text line by line so PIL renders it correctly."""
    if not HAS_ARABIC_SHAPING or not text:
        return text
    out_lines = []
    for line in text.split("\n"):
        try:
            out_lines.append(get_display(arabic_reshaper.reshape(line)))
        except Exception:
            out_lines.append(line)
    return "\n".join(out_lines)


def _to_jsonable(value):
    """Recursively convert tuples to lists so the value becomes JSON serialisable."""
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _copy_value(value):
    """Fast structural copy for plain object payloads (dict/list/tuple/primitives)."""
    if isinstance(value, dict):
        return {k: _copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_copy_value(v) for v in value)
    return value


def _copy_objects(objects: list[dict]) -> list[dict]:
    """Deep-copy a list of board objects without deepcopy's memo overhead."""
    return [{k: _copy_value(v) for k, v in obj.items()} for obj in objects]


class TextDialog(simpledialog.Dialog):
    """Simple multi-line text dialog with size and font selection."""

    def __init__(self, parent: tk.Tk, title: str = "Text") -> None:
        self.text = ""
        self.size = 24
        self.font_path = FONT_CANDIDATES[0]
        super().__init__(parent, title)

    def body(self, master: tk.Frame) -> tk.Text:
        tk.Label(master, text="Text:").grid(row=0, column=0, sticky="nw")
        self.text_widget = tk.Text(master, width=30, height=4, wrap=tk.WORD)
        self.text_widget.grid(row=0, column=1, sticky="ew")

        tk.Label(master, text="Size:").grid(row=1, column=0, sticky="w", pady=6)
        self.size_var = tk.IntVar(value=self.size)
        tk.Spinbox(master, from_=8, to=120, textvariable=self.size_var, width=6).grid(
            row=1, column=1, sticky="w", pady=6
        )

        tk.Label(master, text="Font file:").grid(row=2, column=0, sticky="w")
        self.font_var = tk.StringVar(value=self.font_path)
        ttk.Combobox(
            master,
            textvariable=self.font_var,
            values=FONT_CANDIDATES,
            state="readonly",
            width=20,
        ).grid(row=2, column=1, sticky="ew")
        return self.text_widget

    def apply(self) -> None:
        self.text = self.text_widget.get("1.0", tk.END).strip()
        self.size = self.size_var.get()
        self.font_path = self.font_var.get()


ATOMIC_MASSES: dict[str, float] = {
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "S": 32.06, "Cl": 35.45, "K": 39.098,
    "Ca": 40.078, "Fe": 55.845, "Cu": 63.546, "Zn": 65.38, "Ag": 107.87,
    "Ba": 137.33, "P": 30.974, "I": 126.90, "Mn": 54.938,
}


def molar_mass(formula: str) -> float:
    """Molar mass (g/mol) for parenthesis-free formulas like H2SO4 or C2H5OH."""
    import re
    total = 0.0
    for symbol, count in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        if not symbol:
            continue
        total += ATOMIC_MASSES[symbol] * (int(count) if count else 1)
    return total


CHEMISTRY_EQUATIONS: dict[str, list[tuple[str, str]]] = {
    "Combustion": [
        ("CH4 + 2 O2 -> CO2 + 2 H2O", "methane combustion"),
        ("C3H8 + 5 O2 -> 3 CO2 + 4 H2O", "propane combustion"),
        ("C2H6 + 7/2 O2 -> 2 CO2 + 3 H2O", "ethane combustion"),
        ("C2H5OH + 3 O2 -> 2 CO2 + 3 H2O", "ethanol combustion"),
        ("2 C4H10 + 13 O2 -> 8 CO2 + 10 H2O", "butane combustion"),
    ],
    "Synthesis": [
        ("2 H2 + O2 -> 2 H2O", "water synthesis"),
        ("N2 + 3 H2 <-> 2 NH3", "Haber process"),
        ("2 Mg + O2 -> 2 MgO", "magnesium oxide"),
        ("Fe + S -> FeS", "iron sulfide"),
        ("H2 + Cl2 -> 2 HCl", "hydrogen chloride"),
        ("CaO + H2O -> Ca(OH)2", "slaked lime"),
    ],
    "Decomposition": [
        ("2 H2O2 -> 2 H2O + O2", "peroxide decomposition"),
        ("CaCO3 -> CaO + CO2", "limestone calcination"),
        ("2 KClO3 -> 2 KCl + 3 O2", "potassium chlorate"),
        ("2 NaHCO3 -> Na2CO3 + H2O + CO2", "baking soda decomposition"),
    ],
    "Neutralisation": [
        ("HCl + NaOH -> NaCl + H2O", "strong acid + strong base"),
        ("H2SO4 + 2 NaOH -> Na2SO4 + 2 H2O", "sulfuric acid neutralisation"),
        ("CH3COOH + NaOH -> CH3COONa + H2O", "acetic acid neutralisation"),
        ("2 HNO3 + Ca(OH)2 -> Ca(NO3)2 + 2 H2O", "nitric acid + lime"),
    ],
    "Precipitation": [
        ("AgNO3 + NaCl -> AgCl(v) + NaNO3", "silver chloride precipitate"),
        ("BaCl2 + Na2SO4 -> BaSO4(v) + 2 NaCl", "barium sulfate precipitate"),
        ("Pb(NO3)2 + 2 KI -> PbI2(v) + 2 KNO3", "golden rain"),
        ("CaCl2 + Na2CO3 -> CaCO3(v) + 2 NaCl", "calcium carbonate"),
    ],
    "Redox / Displacement": [
        ("Zn + CuSO4 -> ZnSO4 + Cu", "zinc displaces copper"),
        ("Fe + CuSO4 -> FeSO4 + Cu", "iron displaces copper"),
        ("2 Na + Cl2 -> 2 NaCl", "sodium chloride formation"),
        ("Zn + 2 HCl -> ZnCl2 + H2", "metal + acid hydrogen"),
        ("CuO + H2 -> Cu + H2O", "copper oxide reduction"),
    ],
}


def _random_polynomial(x, degree: int, max_coeff: int = 6):
    terms = []
    for i in range(degree + 1):
        c = random.randint(-max_coeff, max_coeff)
        if c == 0:
            continue
        terms.append(c * x**i)
    if not terms:
        terms.append(x)
    return sp.Add(*terms)


# ------------------------------------------------------------------ math typography
_SUP_MAP = str.maketrans({
    "0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074",
    "5": "\u2075", "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079",
})


def _sup_int(n: int) -> str:
    return ("\u207b" + str(-n).translate(_SUP_MAP)) if n < 0 else str(n).translate(_SUP_MAP)


def _u_num(v) -> str:
    try:
        return f"{float(v):g}"
    except Exception:
        return str(v)


def _u(e) -> str:
    """Render a SymPy expression as clean single-line Unicode math (x² − 3x/2 + √5)."""
    try:
        if isinstance(e, str):
            return e
        if isinstance(e, sp.Symbol):
            return str(e)
        if isinstance(e, sp.Integer):
            return str(e.p)
        if isinstance(e, sp.Rational):
            return f"{e.p}/{e.q}"
        if isinstance(e, (sp.Float, float, int)):
            return _u_num(e)
        if isinstance(e, sp.Pow):
            base, expo = e.args
            if isinstance(expo, sp.Integer):
                bs = _u(base)
                if isinstance(base, sp.Add) or (isinstance(base, sp.Mul) and
                                                (base.could_extract_minus_sign() or len(base.free_symbols) > 1)):
                    bs = f"({bs})"
                return f"{bs}{_sup_int(expo.p)}"
            return f"{_u(base)}^({_u(expo)})"
        if isinstance(e, sp.Mul):
            coeff, tail = e.as_coeff_Mul()
            nums, dens = [], []
            for fct in sp.Mul.make_args(tail):
                if isinstance(fct, sp.Pow) and isinstance(fct.exp, sp.Integer) and fct.exp < 0:
                    d = _u(fct.base)
                    if -fct.exp.p != 1:
                        d += _sup_int(-fct.exp.p)
                    dens.append(d)
                else:
                    nums.append(_u(fct))
            if coeff == 1:
                cs = ""
            elif coeff == -1:
                cs = "-"
            else:
                cs = _u_num(coeff)
            out = cs
            if nums:
                joined = "\u00b7".join(nums)
                if out in ("", "-"):
                    out += joined
                else:
                    out += joined if joined[:1].isdigit() is False else "\u00b7" + joined
            if dens:
                out = (out or "1") + "/" + "/".join(dens)
            return out or "1"
        if isinstance(e, sp.Add):
            parts = []
            for i, term in enumerate(sp.Add.make_args(e)):
                ts = _u(term)
                if i == 0:
                    parts.append(ts)
                elif ts.startswith("-") and not ts.startswith("-\u00b7"):
                    parts.append(" \u2212 " + ts[1:])
                else:
                    parts.append(" + " + ts)
            return "".join(parts)
        name = getattr(getattr(e, "func", None), "__name__", "")
        args = list(getattr(e, "args", []))
        if name == "sqrt":
            return "\u221a(" + _u(args[0]) + ")"
        if name == "log":
            return "ln(" + _u(args[0]) + ")"
        if name == "exp":
            return "e^(" + _u(args[0]) + ")"
        if name in ("sin", "cos", "tan"):
            return f"{name}({_u(args[0])})"
        if name == "Abs":
            return "|" + _u(args[0]) + "|"
        return str(e)
    except Exception:
        return str(e)


# Bilingual instruction templates: topic -> {"en": fmt, "ar": fmt}
_QT = {
    "deriv": {"en": "Find the derivative of:", "ar": "أشتق الدالة الآتية:"},
    "quad": {"en": "Solve the equation:", "ar": "احل المعادلة الآتية:"},
    "integ": {"en": "Evaluate the definite integral from {a} to {b}:", "ar": "احسب التكامل المحدد من {a} إلى {b} للدالة:"},
    "proj": {"en": "A projectile is launched at {v0} m/s at angle {angle}°.\nFind flight time, range and max height.",
             "ar": "يُطلق مقذوف بسرعة ابتدائية {v0} m/s وبزاوية {angle}°.\nاحسب زمن الطيران والمدى وأقصى ارتفاع."},
    "lin": {"en": "Solve for x:", "ar": "أوجد قيمة x:"},
    "sys": {"en": "Solve the system:", "ar": "حل جملة المعادلتين الآتيتين:"},
    "fact": {"en": "Factorise completely:", "ar": "حلّل العبارة الآتية تحليلاً كاملاً:"},
    "arith": {"en": "Arithmetic sequence with a\u2081 = {a1} and d = {d}. Find a_{{{n}}} and S_{{{n}}}.",
              "ar": "متتالية حسابية حدها الأول a\u2081 = {a1} وأساسها d = {d}.\nاحسب الحد ذي الرتبة {n} والمجموع الجزئي S_{{{n}}}."},
    "pct_of": {"en": "Calculate {p}% of {n}.", "ar": "احسب {p}% من العدد {n}."},
    "pct_chg": {"en": "A price of {n} is {word} by {p}%. Find the new price.",
                "ar": "سعر قدره {n} {word} بنسبة {p}%.\nأوجد السعر الجديد."},
    "trig": {"en": "Give the exact value of {fn}({angle}°).", "ar": "أعط القيمة الدقيقة لـ {fn}({angle}°)."},
    "geo_rect": {"en": "Rectangle of width {w} cm and height {h} cm. Find its area and perimeter.",
                 "ar": "مستطيل عرضه {w} cm وطوله {h} cm.\nاحسب مساحته ومحيطه."},
    "geo_tri": {"en": "Triangle of base {b} cm and height {h} cm. Find its area.",
                "ar": "مثلث قاعدته {b} cm وارتفاعه {h} cm.\nاحسب مساحته."},
    "ohm": {"en": "A resistor R = {r} Ω carries I = {i} A. Find V.", "ar": "مقاومة R = {r} Ω يمر بها تيار I = {i} A.\nاحسب التوتر V."},
    "ke": {"en": "Find the kinetic energy of mass {m} kg moving at {v} m/s.",
           "ar": "احسب الطاقة الحركية لجسم كتلته {m} kg وسرعته {v} m/s."},
    "dens": {"en": "Density ρ = {rho} g/cm³, volume {vol} cm³. Find the mass.",
             "ar": "كتلة حجمية ρ = {rho} g/cm³ وحجم {vol} cm³.\nاحسب الكتلة."},
    "bal": {"en": "Balance the equation (coefficients in order):", "ar": "وازن المعادلة الآتية (المعاملات بالترتيب):"},
    "molar": {"en": "Calculate the molar mass M({f}).", "ar": "احسب الكتلة المولية M({f}) بوحدة g/mol."},
    "mol_tomol": {"en": "How many moles in {mass} g of {f}? (M = {M} g/mol)",
                  "ar": "عدد المولات في {mass} g من المادة {f}؟ (M = {M} g/mol)"},
    "mol_tomass": {"en": "Mass of {n} mol of {f}? (M = {M} g/mol)",
                   "ar": "احسب كتلة {n} mol من المادة {f}. (M = {M} g/mol)"},
    "molar_n": {"en": "{n} mol of {f} dissolved to make {V} L solution. Find C (mol/L).",
                "ar": "أُذيب {n} mol من {f} في ماء لتحضير محلول حجمه {V} L.\nاحسب التركيز المولي C."},
    "molar_m": {"en": "Prepare {V} L of {f} at C = {c} mol/L. Find required mass.",
                "ar": "لتحضير محلول حجمه {V} L وتركيزه C = {c} mol/L من {f},\nاحسب الكتلة اللازمة من {f}."},
    "ph_acid": {"en": "Strong acid with [H\u207a] = {a}×10\u207b{b} mol/L. Find pH.",
                "ar": "محلول حمض قوي تركيز أيوناته [H\u207a] = {a}×10\u207b{b} mol/L.\nاحسب pH المحلول."},
    "ph_base": {"en": "Strong base with [OH\u207b] = {a}×10\u207b{b} mol/L. Find pH.",
                "ar": "محلول أساس قوي تركيز أيوناته [OH\u207b] = {a}×10\u207b{b} mol/L.\nاحسب pH المحلول."},
    "boyle": {"en": "Gas occupies {v1} L at P = {p1} atm (T constant). Find P at {v2} L.",
              "ar": "غاز يحتل حجم {v1} L تحت ضغط {p1} atm (ثبوت T).\nاحسب الضغط عندما يصبح الحجم {v2} L."},
    "charles": {"en": "At T1 = {t1} K volume is {v1} L (P constant). Find V at T2 = {t2} K.",
                "ar": "عند T1 = {t1} K كان الحجم {v1} L (ثبوت P).\nاحسب الحجم عند T2 = {t2} K."},
    "ideal": {"en": "PV = nRT with R = {R}. Given n = {n}, T = {t} K, P = {p} atm → find V.",
              "ar": "باستخدام PV = nRT حيث R = {R}:\nn = {n} mol ، T = {t} K ، P = {p} atm → احسب V."},
    "stoi": {"en": "For: {rxn}\nFrom {g} g of {gv}, find theoretical mass of {tg}.",
             "ar": "بالنسبة للتفاعل:\n  {rxn}\nانطلاقاً من {g} g من المادة {gv},\nاحسب الكتلة النظرية المتكونة من {tg}."},
}


def _L(key: str, lang: str) -> str:
    return _QT[key][lang if lang in ("en", "ar") else "en"]


def _gen_poly_derivative(level, x, lang="en"):
    expr = _random_polynomial(x, 1 + level)
    sol = sp.diff(expr, x)

    def verify():
        if sp.degree(expr) < 1:
            return False
        return sp.simplify(sp.diff(expr, x) - sol) == 0

    q = f"{_L('deriv', lang)}\n{_u(expr)}"
    return (q, f"f'(x) = {_u(sol)}", verify)


def _gen_quadratic(level, x, lang="en"):
    a = random.choice([1, -1] + ([2, -2, 3] if level >= 2 else []))
    r1 = random.randint(-6, 6) or 1
    r2 = random.randint(-6, 6) or 2
    b, c = -a * (r1 + r2), a * r1 * r2
    expr = a * x**2 + b * x + c
    sol = sp.solve(expr, x)

    def verify():
        for s in sol:
            if sp.simplify(expr.subs(x, s)) != 0:
                return False
        return len(set(sol)) >= 2

    q = f"{_L('quad', lang)}\n{_u(expr)} = 0"
    roots = " , ".join(_u(s) for s in sorted(sol))
    return (q, f"x \u2208 {{{roots}}}", verify)


def _gen_integral(level, x, lang="en"):
    expr = _random_polynomial(x, level)
    a, b = sorted(random.randint(0, 5) for _ in range(2))
    val = sp.integrate(expr, (x, a, b))
    F = sp.integrate(expr, x)

    def verify():
        if sp.simplify(sp.diff(F, x) - expr) != 0:
            return False
        return sp.simplify(val - F.subs(x, b) + F.subs(x, a)) == 0

    q = f"{_L('integ', lang).format(a=a, b=b)}\n\u222b ({_u(expr)}) dx"
    return (q, f"F(x) = {_u(F)} + C\n= {sp.simplify(val)}", verify)


def _gen_projectile(level, x=None, lang="en"):
    v0 = 15 + level * 10 + random.randint(0, 10)
    angle = random.choice([30, 45, 60]) + random.randint(-5, 5)
    theta = math.radians(angle)
    g = 9.81
    vx, vy = v0 * math.cos(theta), v0 * math.sin(theta)
    t_flight = 2 * vy / g

    def verify():
        return t_flight > 0 and vx * t_flight > 0 and vy * vy / (2 * g) > 0

    q = _L("proj", lang).format(v0=v0, angle=angle)
    return (q,
            f"T = {t_flight:.2f} s | R = {vx*t_flight:.2f} m | H = {vy*vy/(2*g):.2f} m",
            verify)


def _gen_linear_eq(level, x, lang="en"):
    a = random.randint(2, 4 + 2 * level)
    x0 = random.randint(-9, 9) or 3
    b = random.randint(-15, 15)
    c = a * x0 + b

    def verify():
        return a != 0 and a * x0 + b == c

    eq = f"{_u(a*x)} {'+' if b >= 0 else '\u2212'} {abs(b)} = {c}"
    return (f"{_L('lin', lang)}   {eq}", f"x = {x0}", verify)


def _gen_system_2x2(level, x=None, lang="en"):
    sx, sy = random.randint(-8, 8) or 2, random.randint(-8, 8) or 3
    a1, b1 = random.randint(1, 4), random.randint(1, 4)
    a2, b2 = random.randint(1, 4), random.randint(-4, 4) or 5
    c1, c2 = a1 * sx + b1 * sy, a2 * sx + b2 * sy

    def eq_str(av, bv, cv):
        return f"{av}x {'+' if bv >= 0 else '\u2212'} {abs(bv)}y = {cv}"

    def verify():
        det = a1 * b2 - a2 * b1
        if det == 0:
            return False
        return a1 * sx + b1 * sy == c1 and a2 * sx + b2 * sy == c2

    q = f"{_L('sys', lang)}\n  {eq_str(a1, b1, c1)}\n  {eq_str(a2, b2, c2)}"
    return (q, f"x = {sx} , y = {sy}", verify)


def _gen_factor(level, x, lang="en"):
    r1 = random.randint(-7, 7) or 1
    r2 = random.randint(-7, 7) or 2
    if r1 == r2:
        r2 += 1
    poly = sp.expand((x - r1) * (x - r2))

    def verify():
        return sp.simplify(sp.expand((x - r1) * (x - r2)) - poly) == 0

    q = f"{_L('fact', lang)}   {_u(poly)}"
    facs = f"(x {'\u2212' if r1 >= 0 else '+'} {abs(r1)})(x {'\u2212' if r2 >= 0 else '+'} {abs(r2)})"
    return (q, facs, verify)


def _gen_arith_seq(level, x=None, lang="en"):
    a1 = random.randint(-10, 20) or 2
    d = random.randint(-9, 12) or 3
    n = random.randint(5, 12 + 4 * level)
    an = a1 + (n - 1) * d
    sn = n * (2 * a1 + (n - 1) * d) // 2

    def verify():
        return an == a1 + (n - 1) * d and sn == n * (2 * a1 + (n - 1) * d) // 2

    q = _L("arith", lang).format(a1=a1, d=d, n=n)
    return (q, f"a(n) = {an} | S(n) = {sn}", verify)


def _gen_percentage(level, x=None, lang="en"):
    p = random.choice([5, 10, 15, 20, 25, 40, 50, 60, 75])
    n = random.randint(2, 30) * 100 + random.randint(0, 99)
    val = round(n * p / 100, 2)
    mode = random.choice(["of", "increase", "decrease"])

    def verify():
        expected = {"of": val,
                    "increase": round(n * (1 + p / 100), 2),
                    "decrease": round(n * (1 - p / 100), 2)}[mode]
        return expected > 0

    if mode == "of":
        return (_L("pct_of", lang).format(p=p, n=n), f"= {val}", verify)
    new_v = round(n * (1 + p / 100), 2) if mode == "increase" else round(n * (1 - p / 100), 2)
    word_en = "increased" if mode == "increase" else "decreased"
    word_ar = "ارتفع" if mode == "increase" else "انخفض"
    word = word_en if lang == "en" else word_ar
    return (_L("pct_chg", lang).format(n=n, word=word, p=p), f"= {new_v}", verify)


_TRIG_TABLE = {
    "sin": ["0", "1/2", "\u221a2/2", "\u221a3/2", "1"],
    "cos": ["1", "\u221a3/2", "\u221a2/2", "1/2", "0"],
    "tan": ["0", "\u221a3/3", "1", "\u221a3", "undefined"],
}


def _gen_trig_values(level, x=None, lang="en"):
    angle = random.choice([0, 30, 45, 60, 90])
    fn = random.choice(["sin", "cos", "tan"])
    idx = [0, 30, 45, 60, 90].index(angle)
    value = _TRIG_TABLE[fn][idx]

    def verify():
        return value == _TRIG_TABLE[fn][idx] and angle in (0, 30, 45, 60, 90)

    return (_L("trig", lang).format(fn=fn, angle=angle),
            f"{fn}({angle}\u00b0) = {value}", verify)


def _gen_geometry(level, x=None, lang="en"):
    shape = random.choice(["rectangle", "triangle"])
    if shape == "rectangle":
        w, h = random.randint(3, 15), random.randint(3, 15)

        def verify():
            return w * h > 0 and 2 * (w + h) > 0

        return (_L("geo_rect", lang).format(w=w, h=h),
                f"A = {w*h} cm\u00b2 | P = {2*(w+h)} cm", verify)
    base, hgt = random.randint(4, 20), random.randint(3, 18)

    def verify():
        return base * hgt / 2 > 0

    return (_L("geo_tri", lang).format(b=base, h=hgt),
            f"A = {base*hgt/2:g} cm\u00b2", verify)


def _gen_physics_quick(level, x=None, lang="en"):
    kind = random.choice(["ohm", "ke", "density"])
    if kind == "ohm":
        i = round(random.uniform(0.5, 5.0), 1)
        r = random.randint(2, 60)
        ans = round(i * r, 2)

        def verify():
            return abs(i * r - ans) < 1e-6

        return (_L("ohm", lang).format(r=r, i=i), f"V = {ans:g} V", verify)
    if kind == "ke":
        m = random.randint(1, 50)
        v = random.randint(2, 20)
        ans = round(0.5 * m * v * v, 1)

        def verify():
            return abs(0.5 * m * v * v - ans) < 0.05

        return (_L("ke", lang).format(m=m, v=v), f"KE = {ans:g} J", verify)
    rho = round(random.uniform(0.5, 19.0), 2)
    vol = random.randint(10, 500)
    ans = round(rho * vol, 1)

    def verify():
        return abs(rho * vol - ans) <= 0.05

    return (_L("dens", lang).format(rho=rho, vol=vol), f"m = {ans:g} g", verify)


# ------------------------------------------------------------------ chemistry generators
_BALANCE_POOL = [
    ("__ H2 + __ O2 -> __ H2O", "2, 1, 2"),
    ("__ CH4 + __ O2 -> __ CO2 + __ H2O", "1, 2, 1, 2"),
    ("__ Al + __ O2 -> __ Al2O3", "4, 3, 2"),
    ("__ Fe + __ Cl2 -> __ FeCl3", "2, 3, 2"),
    ("__ C3H8 + __ O2 -> __ CO2 + __ H2O", "1, 5, 3, 4"),
    ("__ N2 + __ H2 -> __ NH3", "1, 3, 2"),
    ("__ Zn + __ HCl -> __ ZnCl2 + __ H2", "1, 2, 1, 1"),
    ("__ NaHCO3 -> __ Na2CO3 + __ H2O + __ CO2", "2, 1, 1, 1"),
    ("__ C2H6 + __ O2 -> __ CO2 + __ H2O", "2, 7, 4, 6"),
    ("__ KClO3 -> __ KCl + __ O2", "2, 2, 3"),
    ("__ H2SO4 + __ NaOH -> __ Na2SO4 + __ H2O", "1, 2, 1, 2"),
    ("__ Mg + __ HCl -> __ MgCl2 + __ H2", "1, 2, 1, 1"),
]


def _gen_balance(level, x=None, lang="en"):
    skeleton, coeffs = random.choice(_BALANCE_POOL)

    def verify():
        return skeleton.count("__") == len(coeffs.split(","))

    q = f"{_L('bal', lang)}\n" + skeleton.replace("__", "?")
    return (q, f"Coefficients: {coeffs}", verify)


_COMMON_MOLAR = ["H2O", "CO2", "NaCl", "CH4", "NH3", "H2SO4", "CaCO3",
                 "NaOH", "MgO", "Al2O3", "Fe2O3", "CuSO4", "KCl", "AgNO3",
                 "BaCl2", "C2H5OH", "C3H8", "KMnO4", "HNO3", "ZnSO4"]


def _gen_molar_mass(level, x=None, lang="en"):
    formula = random.choice(_COMMON_MOLAR)
    M = molar_mass(formula)

    def verify():
        return abs(molar_mass(formula) - M) < 1e-6 and M > 0

    digits = 1 if level < 3 else 2
    return (_L("molar", lang).format(f=formula),
            f"M = {round(M, digits)} g/mol", verify)


def _gen_mole_conversion(level, x=None, lang="en"):
    formula = random.choice(_COMMON_MOLAR[:12])
    M = molar_mass(formula)
    direction = random.choice(["to_mol", "to_mass"])
    if level <= 2:
        mass = round(M * random.randint(1, 8), 2)
    else:
        mass = round(random.uniform(1.0, 120.0), 2)
    n = mass / M

    def verify():
        return abs(n * M - mass) < 0.01 and n > 0

    if direction == "to_mol":
        return (_L("mol_tomol", lang).format(mass=mass, f=formula, M=f"{M:.1f}"),
                f"n = m/M = {round(n, 3):g} mol", verify)
    moles = round(random.uniform(0.2, 4.0), 2)
    m_ans = round(moles * M, 2)

    def verify2():
        return abs(m_ans / M - moles) < 0.005 and m_ans > 0

    return (_L("mol_tomass", lang).format(n=moles, f=formula, M=f"{M:.1f}"),
            f"m = n\u00b7M = {m_ans:g} g", verify2)


def _gen_molarity(level, x=None, lang="en"):
    formula = random.choice(["NaCl", "HCl", "NaOH", "H2SO4", "KCl", "CuSO4"])
    M_molar = molar_mass(formula)
    volume_l = round(random.choice([0.25, 0.5, 1.0, 1.5, 2.0, 2.5]), 2)
    if level >= 3:
        moles = round(random.uniform(0.05, 2.0), 3)
        conc = moles / volume_l

        def verify():
            return abs(conc * volume_l - moles) < 1e-6 and conc > 0

        return (_L("molar_n", lang).format(n=moles, f=formula, V=volume_l),
                f"C = n/V = {round(conc, 3):g} mol/L", verify)
    conc = round(random.uniform(0.1, 2.5), 2)
    moles = conc * volume_l
    mass = round(moles * M_molar, 2)

    def verify2():
        return abs(round(mass / M_molar / volume_l, 2)) == conc and mass > 0

    return (_L("molar_m", lang).format(V=volume_l, f=formula, c=conc),
            f"m = C\u00b7V\u00b7M = {mass:g} g", verify2)


def _gen_ph(level, x=None, lang="en"):
    kind = random.choice(["acid", "base"])
    b = random.randint(1, 4 if level <= 2 else 5)
    a_coef = random.randint(1, 9)
    conc = a_coef * (10 ** (-b))
    if kind == "acid":
        ph = round(-math.log10(conc), 2)

        def verify():
            return abs(-math.log10(conc) - ph) < 0.005 and 0 < ph < 14

        return (_L("ph_acid", lang).format(a=a_coef, b=b),
                f"pH = \u2212log[H\u207a] = {ph}", verify)
    poh = round(-math.log10(conc), 2)
    ph = round(14 - poh, 2)

    def verify2():
        return abs((14 - poh) - ph) < 0.005 and 0 < ph < 14

    return (_L("ph_base", lang).format(a=a_coef, b=b),
            f"pOH = {poh}  \u2192  pH = {ph}", verify2)


_GAS_R = 0.08206


def _gen_gas_laws(level, x=None, lang="en"):
    mode = random.choice(["boyle", "charles", "ideal"]) if level >= 2 else random.choice(["boyle", "charles"])
    if mode == "boyle":
        p1 = round(random.uniform(0.5, 4.0), 2)
        v1 = round(random.uniform(1.0, 10.0), 2)
        v2 = round(random.uniform(0.5, v1), 2)
        p2 = p1 * v1 / v2

        def verify():
            return abs(p2 * v2 - p1 * v1) < 1e-9 and p2 > 0

        return (_L("boyle", lang).format(v1=v1, p1=p1, v2=v2),
                f"P2 = P1\u00b7V1/V2 = {round(p2, 3):g} atm", verify)
    if mode == "charles":
        t1 = random.randint(250, 350)
        v1 = round(random.uniform(1.0, 8.0), 2)
        t2 = random.randint(300, 420)
        v2 = v1 * t2 / t1

        def verify2():
            return abs(v2 / v1 - t2 / t1) < 1e-9 and v2 > 0

        return (_L("charles", lang).format(t1=t1, v1=v1, t2=t2),
                f"V2 = V1\u00b7T2/T1 = {round(v2, 2):g} L", verify2)
    n = round(random.uniform(0.2, 3.0), 2)
    T = random.randint(273, 400)
    P = round(random.uniform(0.5, 5.0), 2)
    V = n * _GAS_R * T / P

    def verify3():
        return abs(P * V - n * _GAS_R * T) < 1e-9 and V > 0

    return (_L("ideal", lang).format(R=_GAS_R, n=n, t=T, p=P),
            f"V = nRT/P = {round(V, 2):g} L", verify3)


_STOICH_POOL = [
    {"rxn": "CH4 + 2 O2 -> CO2 + 2 H2O", "given": ("CH4", 16.04), "target": ("CO2", 44.01), "ratio": 1},
    {"rxn": "2 H2 + O2 -> 2 H2O", "given": ("H2", 2.016), "target": ("H2O", 18.02), "ratio": 1},
    {"rxn": "N2 + 3 H2 -> 2 NH3", "given": ("H2", 2.016), "target": ("NH3", 17.03), "ratio": 2 / 3},
    {"rxn": "Zn + CuSO4 -> ZnSO4 + Cu", "given": ("Zn", 65.38), "target": ("Cu", 63.55), "ratio": 1},
    {"rxn": "CaCO3 -> CaO + CO2", "given": ("CaCO3", 100.09), "target": ("CO2", 44.01), "ratio": 1},
]


def _gen_stoichiometry(level, x=None, lang="en"):
    rxn = random.choice(_STOICH_POOL)
    grams = round(random.uniform(2.0, 40.0), 2) if level >= 3 else float(random.randint(4, 40))
    product_mass = grams / rxn["given"][1] * rxn["ratio"] * rxn["target"][1]

    def verify():
        back = product_mass / (rxn["target"][1] * rxn["ratio"]) * rxn["given"][1]
        return abs(back - grams) < 0.01 and product_mass > 0

    q = _L("stoi", lang).format(rxn=rxn["rxn"], g=grams,
                                gv=rxn["given"][0], tg=rxn["target"][0])
    a_txt = (f"n({rxn['given'][0]}) = {grams}/{rxn['given'][1]:g}\n"
             f"n({rxn['target'][0]}) = n\u00b7{round(rxn['ratio'], 3):g}\n"
             f"m = {round(product_mass, 2):g} g")
    return (q, a_txt, verify)


WORKSHEET_TOPICS: dict[str, callable] = {
    "Polynomial derivative": _gen_poly_derivative,
    "Quadratic equation": _gen_quadratic,
    "Definite integral": _gen_integral,
    "Projectile problem": _gen_projectile,
    "Linear equation": _gen_linear_eq,
    "System 2×2": _gen_system_2x2,
    "Factorisation": _gen_factor,
    "Arithmetic sequence": _gen_arith_seq,
    "Percentages": _gen_percentage,
    "Trig exact values": _gen_trig_values,
    "Geometry basics": _gen_geometry,
    "Physics quick problems": _gen_physics_quick,
    "Balance equations (Chem)": _gen_balance,
    "Molar mass (Chem)": _gen_molar_mass,
    "Mole conversions (Chem)": _gen_mole_conversion,
    "Molarity (Chem)": _gen_molarity,
    "pH calculations (Chem)": _gen_ph,
    "Gas laws (Chem)": _gen_gas_laws,
    "Stoichiometry (Chem)": _gen_stoichiometry,
}


def generate_problem_raw(topic: str, level: int, lang: str = "en") -> tuple[str, str, callable | None]:
    """Generate one problem with an optional self-verification closure."""
    if not HAS_SYMPY:
        return ("SymPy not available", "Install SymPy.", None)
    gen = WORKSHEET_TOPICS.get(topic)
    if gen is None:
        return ("Unknown topic", "", None)
    try:
        return gen(max(1, min(5, level)), sp.Symbol("x"), lang)
    except Exception as exc:
        return (f"Generator error: {exc}", "", None)


def generate_problem(topic: str, level: int) -> tuple[str, str]:
    """Backward-compatible two-tuple generation."""
    q, a, _vf = generate_problem_raw(topic, level)
    return q, a


def generate_verified_questions(topics: list[str], per_topic: int, level: int,
                                lang: str = "en",
                                max_attempts_factor: int = 8) -> list[tuple[str, str, str]]:
    """Generate unique, self-verified questions; silently skips rejects."""
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for topic in topics:
        got = 0
        attempts = 0
        limit = max(per_topic, 1) * max_attempts_factor
        while got < per_topic and attempts < limit:
            attempts += 1
            q, a, vf = generate_problem_raw(topic, level, lang)
            if not q or not a or q.startswith("Generator error"):
                continue
            if vf is not None:
                try:
                    if not vf():
                        continue
                except Exception:
                    continue
            sig = hashlib.md5(q.encode("utf-8")).hexdigest()
            if sig in seen:
                continue
            seen.add(sig)
            out.append((topic, q, a))
            got += 1
    return out


class MathDialog(simpledialog.Dialog):
    """Dialog for symbolic math operations."""

    def __init__(self, parent: tk.Tk | None = None, title: str = "Math Assistant") -> None:
        self.ok = False
        self.expr = ""
        self.operation = "Derivative"
        self.scale = 30.0
        self.plot = True
        super().__init__(parent, title)

    def body(self, master: tk.Frame) -> tk.Entry:
        tk.Label(master, text="f(x) =").grid(row=0, column=0, sticky="w")
        self.expr_entry = tk.Entry(master, width=40)
        self.expr_entry.grid(row=0, column=1, sticky="ew")
        self.expr_entry.insert(0, "x**2 - 4*x + 3")

        tk.Label(master, text="Operation:").grid(row=1, column=0, sticky="w")
        self.op_var = tk.StringVar(value="Derivative")
        ttk.Combobox(
            master,
            textvariable=self.op_var,
            values=["Derivative", "Integral", "Simplify", "Solve", "Table of variations", "Plot"],
            state="readonly",
            width=20,
        ).grid(row=1, column=1, sticky="ew")

        tk.Label(master, text="Scale:").grid(row=2, column=0, sticky="w")
        self.scale_var = tk.DoubleVar(value=30.0)
        tk.Spinbox(master, from_=5, to=200, textvariable=self.scale_var, width=8).grid(
            row=2, column=1, sticky="w"
        )

        self.plot_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            master, text="Plot result on board (when applicable)", variable=self.plot_var
        ).grid(row=3, columnspan=2, sticky="w")

        return self.expr_entry

    def apply(self) -> None:
        self.expr = self.expr_entry.get().strip()
        self.operation = self.op_var.get()
        self.scale = self.scale_var.get()
        self.plot = self.plot_var.get()
        self.ok = True


class PhysicsDialog(simpledialog.Dialog):
    """Dialog for projectile motion simulation parameters."""

    def __init__(self, parent: tk.Tk | None = None, title: str = "Projectile Motion") -> None:
        self.ok = False
        self.v0 = 25.0
        self.angle = 45.0
        self.h0 = 0.0
        self.g = 9.81
        self.scale = 3.0
        super().__init__(parent, title)

    def body(self, master: tk.Frame) -> tk.Entry:
        tk.Label(master, text="Initial velocity (m/s):").grid(row=0, column=0, sticky="w")
        self.v0_var = tk.DoubleVar(value=25.0)
        self.v0_entry = tk.Entry(master, textvariable=self.v0_var, width=10)
        self.v0_entry.grid(row=0, column=1, sticky="w")

        tk.Label(master, text="Launch angle (°):").grid(row=1, column=0, sticky="w")
        self.angle_var = tk.DoubleVar(value=45.0)
        tk.Entry(master, textvariable=self.angle_var, width=10).grid(row=1, column=1, sticky="w")

        tk.Label(master, text="Initial height (m):").grid(row=2, column=0, sticky="w")
        self.h0_var = tk.DoubleVar(value=0.0)
        tk.Entry(master, textvariable=self.h0_var, width=10).grid(row=2, column=1, sticky="w")

        tk.Label(master, text="Gravity (m/s²):").grid(row=3, column=0, sticky="w")
        self.g_var = tk.DoubleVar(value=9.81)
        tk.Entry(master, textvariable=self.g_var, width=10).grid(row=3, column=1, sticky="w")

        tk.Label(master, text="Scale (px/m):").grid(row=4, column=0, sticky="w")
        self.scale_var = tk.DoubleVar(value=3.0)
        tk.Entry(master, textvariable=self.scale_var, width=10).grid(row=4, column=1, sticky="w")

        return self.v0_entry

    def apply(self) -> None:
        self.v0 = self.v0_var.get()
        self.angle = self.angle_var.get()
        self.h0 = self.h0_var.get()
        self.g = self.g_var.get()
        self.scale = self.scale_var.get()
        self.ok = True


class ExerciseDialog(simpledialog.Dialog):
    """Dialog to generate random exercises with solutions."""

    def __init__(self, parent: tk.Tk | None = None, title: str = "Exercise Generator") -> None:
        self.ok = False
        self.topic = "Polynomial derivative"
        self.level = 1
        self.generated = ""
        super().__init__(parent, title)

    def body(self, master: tk.Frame) -> ttk.Combobox:
        tk.Label(master, text="Topic:").grid(row=0, column=0, sticky="w")
        self.topic_var = tk.StringVar(value="Polynomial derivative")
        self.topic_combo = ttk.Combobox(
            master,
            textvariable=self.topic_var,
            values=["Polynomial derivative", "Quadratic equation", "Definite integral", "Projectile problem"],
            state="readonly",
            width=25,
        )
        self.topic_combo.grid(row=0, column=1, sticky="ew")

        tk.Label(master, text="Level:").grid(row=1, column=0, sticky="w")
        self.level_var = tk.IntVar(value=1)
        tk.Spinbox(master, from_=1, to=3, textvariable=self.level_var, width=5).grid(
            row=1, column=1, sticky="w"
        )

        tk.Button(master, text="Generate", command=self._generate).grid(
            row=2, column=0, columnspan=2, pady=4
        )

        tk.Label(master, text="Problem & solution:").grid(row=3, column=0, sticky="nw")
        self.text = tk.Text(master, width=50, height=12, wrap=tk.WORD)
        self.text.grid(row=3, column=1, sticky="nsew")
        master.grid_rowconfigure(3, weight=1)
        master.grid_columnconfigure(1, weight=1)
        self._generate()
        return self.topic_combo

    def _generate(self) -> None:
        problem, solution = generate_problem(self.topic_var.get(), self.level_var.get())
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, f"PROBLEM:\n{problem}\n\nSOLUTION:\n{solution}")

    def apply(self) -> None:
        self.topic = self.topic_var.get()
        self.level = self.level_var.get()
        self.generated = self.text.get("1.0", tk.END).strip()
        self.ok = True


WORKSHEET_LANGS = {
    "en": {
        "title": "Worksheet", "school": "School:", "teacher": "Teacher:", "class": "Class:",
        "date": "Date:", "questions": "Questions", "name_field": "Name:", "answer_key": "ANSWER KEY",
        "page": "Page",
    },
    "ar": {
        "title": "ورقة عمل", "school": "الثانوية:", "teacher": "الأستاذ:", "class": "القسم:",
        "date": "التاريخ:", "questions": "أسئلة", "name_field": "الاسم:", "answer_key": "تصحيح",
        "page": "صفحة",
    },
}


def _has_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


class WorksheetDialog(simpledialog.Dialog):
    """Configure and generate a full worksheet (questions + answer key)."""

    def __init__(self, parent: tk.Tk | None = None, title: str = "Worksheet Maker") -> None:
        self.ok = False
        self.action = "cancel"          # 'insert' | 'pdf' | 'cancel'
        self.meta: dict = {}
        self.questions: list[tuple[str, str, str]] = []
        super().__init__(parent, title)

    def body(self, master: tk.Frame) -> tk.Widget:
        master.grid_columnconfigure(1, weight=1)
        row = 0
        ttk.Label(master, text="Language:").grid(row=row, column=0, sticky="w")
        self.lang_var = tk.StringVar(value="العربية")
        lang_combo = ttk.Combobox(
            master, textvariable=self.lang_var, values=["العربية", "English"],
            state="readonly", width=12,
        )
        lang_combo.grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(master, text="Title:").grid(row=row, column=0, sticky="w")
        self.title_var = tk.StringVar(value="")
        ttk.Entry(master, textvariable=self.title_var, width=34).grid(row=row, column=1, sticky="ew")

        meta_frame = ttk.Labelframe(master, text="Header")
        meta_frame.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=4)
        for i in range(4):
            meta_frame.grid_columnconfigure(1 + 2 * i, weight=1)
        self.school_var = tk.StringVar()
        self.teacher_var = tk.StringVar()
        self.class_var = tk.StringVar()
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        for i, (lbl, var) in enumerate([
            ("School", self.school_var), ("Teacher", self.teacher_var),
            ("Class", self.class_var), ("Date", self.date_var),
        ]):
            ttk.Label(meta_frame, text=f"{lbl}:").grid(row=0, column=2 * i, sticky="w", padx=(6, 2))
            ttk.Entry(meta_frame, textvariable=var, width=14).grid(row=0, column=2 * i + 1, sticky="ew", padx=(0, 6))

        topics_frame = ttk.Labelframe(master, text="Topics")
        topics_frame.grid(row=row + 2, column=0, columnspan=2, sticky="ew", pady=4)
        self.topic_vars: dict[str, tk.BooleanVar] = {}
        for i, name in enumerate(WORKSHEET_TOPICS):
            var = tk.BooleanVar(value=i < 3)   # sensible default: first three
            self.topic_vars[name] = var
            cb = tk.Checkbutton(topics_frame, text=name, variable=var)
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=6, pady=1)
        ttk.Button(topics_frame, text="Select all / none", command=self._toggle_all).grid(
            row=len(WORKSHEET_TOPICS) // 3 + 1, column=0, columnspan=3, pady=(2, 4),
        )

        opts = ttk.Frame(master)
        opts.grid(row=row + 3, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        ttk.Label(opts, text="Per topic:").pack(side=tk.LEFT)
        self.count_var = tk.IntVar(value=2)
        tk.Spinbox(opts, from_=1, to=10, width=4, textvariable=self.count_var).pack(side=tk.LEFT, padx=(2, 14))
        ttk.Label(opts, text="Difficulty (1-5):").pack(side=tk.LEFT)
        self.level_var = tk.IntVar(value=2)
        tk.Spinbox(opts, from_=1, to=5, width=4, textvariable=self.level_var).pack(side=tk.LEFT, padx=2)
        ttk.Label(opts, text="Seed (reproducible):").pack(side=tk.LEFT, padx=(14, 0))
        self.seed_var = tk.StringVar()
        ttk.Entry(opts, textvariable=self.seed_var, width=10).pack(side=tk.LEFT, padx=2)

        return lang_combo

    def _toggle_all(self) -> None:
        any_off = any(not v.get() for v in self.topic_vars.values())
        for v in self.topic_vars.values():
            v.set(any_off)

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ttk.Button(box, text="Insert on board", command=lambda: self._done("insert")).pack(
            side=tk.LEFT, padx=6, pady=6,
        )
        ttk.Button(box, text="Export PDF…", command=lambda: self._done("pdf")).pack(
            side=tk.LEFT, padx=6, pady=6,
        )
        ttk.Button(box, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=6, pady=6)
        self.bind("<Return>", lambda e: self._done("insert"))
        self.bind("<Escape>", lambda e: self.cancel())
        box.configure(padding="6")
        box.pack()

    def _done(self, action: str) -> None:
        if not self.apply_config():
            return
        self.action = action
        self.ok = True
        self.destroy()

    def apply_config(self) -> bool:
        selected = [t for t, v in self.topic_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("Worksheet Maker", "Select at least one topic.")
            return False
        count = max(1, min(10, int(self.count_var.get())))
        level = max(1, min(5, int(self.level_var.get())))
        seed_text = self.seed_var.get().strip()
        if seed_text:
            try:
                random.seed(int(seed_text))
            except ValueError:
                random.seed(seed_text)
            meta_seed = seed_text
        else:
            meta_seed = str(random.randrange(10**8))
            random.seed(int(meta_seed))
        lang_code = "ar" if self.lang_var.get().startswith("العربية") else "en"
        title = self.title_var.get().strip() or WORKSHEET_LANGS[lang_code]["title"]
        self.meta = {
            "lang": lang_code,
            "title": title,
            "school": self.school_var.get().strip(),
            "teacher": self.teacher_var.get().strip(),
            "klass": self.class_var.get().strip(),
            "date": self.date_var.get().strip(),
            "seed": meta_seed,
        }
        questions = generate_verified_questions(selected, count, level, lang=lang_code)
        expected = len(selected) * count
        if not questions:
            messagebox.showwarning("Worksheet Maker", "No valid questions could be generated.")
            return False
        if len(questions) < expected:
            messagebox.showwarning(
                "Worksheet Maker",
                f"Only {len(questions)}/{expected} unique verified questions were produced "
                "(topic combinations are limited).",
            )
        self.questions = questions
        return True

    def apply(self) -> None:      # not used; custom buttons handle everything
        pass


class ChemistryLibraryDialog(simpledialog.Dialog):
    """Browsable library of balanced chemical equations, insertable on the board."""

    def __init__(self, parent: tk.Tk | None = None, app: "WhiteboardApp" | None = None) -> None:
        self.app = app
        self.selected: str | None = None
        super().__init__(parent, title="Chemistry Library")

    def body(self, master: tk.Frame) -> tk.Widget:
        master.grid_columnconfigure(0, weight=1)
        master.grid_rowconfigure(1, weight=1)

        ttk.Label(master, text="Category:").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.cat_var = tk.StringVar(value=list(CHEMISTRY_EQUATIONS.keys())[0])
        combo = ttk.Combobox(
            master, textvariable=self.cat_var,
            values=list(CHEMISTRY_EQUATIONS.keys()), state="readonly",
        )
        combo.grid(row=1, column=0, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        self.listbox = tk.Listbox(master, width=52, height=14, font=("Consolas", 11))
        self.listbox.grid(row=2, column=0, sticky="nsew", pady=4)

        btns = ttk.Frame(master)
        btns.grid(row=3, column=0, sticky="ew")
        ttk.Button(btns, text="Insert on board", command=self._insert).pack(side=tk.LEFT)
        ttk.Button(btns, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._insert())
        self._refresh()
        return self.listbox

    def _refresh(self) -> None:
        self.listbox.delete(0, tk.END)
        for eq, name in CHEMISTRY_EQUATIONS.get(self.cat_var.get(), []):
            self.listbox.insert(tk.END, f"{eq}    [{name}]")

    def _insert(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        eq, _name = CHEMISTRY_EQUATIONS[self.cat_var.get()][sel[0]]
        if self.app:
            self.app.insert_chem_equation(f"{eq}\n({self.cat_var.get()})")
        self.destroy()

    def apply(self) -> None:
        pass


class PeriodicTableDialog(simpledialog.Dialog):
    """Mini periodic table picker."""

    def __init__(self, parent: tk.Tk | None = None, app: "WhiteboardApp" | None = None) -> None:
        self.app = app
        super().__init__(parent, title="Periodic Table")

    def body(self, master: tk.Frame) -> tk.Widget:
        cols = 8
        for idx, (symbol, name, number) in enumerate(PERIODIC_TABLE):
            row = idx // cols
            col = idx % cols
            b = tk.Button(
                master, text=symbol, width=4,
                command=lambda s=symbol, n=name, z=number: self._select(s, n, z)
            )
            b.grid(row=row, column=col, padx=1, pady=1)
        return master

    def _select(self, symbol: str, name: str, number: int) -> None:
        if self.app:
            self.app.insert_element_info(symbol, name, number)
        self.destroy()

    def apply(self) -> None:
        pass


class AICopilotDialog(simpledialog.Dialog):
    """Rule-based lesson assistant that suggests an outline for a topic."""

    OUTLINES: dict[str, list[str]] = {
        "derivative": [
            "1. Definition: rate of change and limit of difference quotient",
            "2. Notation: f'(x), dy/dx, Leibniz and Lagrange forms",
            "3. Basic rules: power, sum, product, quotient, chain",
            "4. Common derivatives: polynomial, exponential, logarithm, trigonometric",
            "5. Applications: tangents, optimization, related rates",
            "6. Practice: compute f'(x) for 5 examples",
        ],
        "integral": [
            "1. Definition: antiderivative and area under a curve",
            "2. Notation: ∫ f(x) dx and ∫_a^b f(x) dx",
            "3. Basic rules: power rule, linearity, substitution",
            "4. Common integrals: polynomial, e^x, 1/x, sin/cos",
            "5. Definite integrals: fundamental theorem and area",
            "6. Applications: area, volume, center of mass",
            "7. Practice: solve 5 integration problems",
        ],
        "projectile": [
            "1. Kinematic equations in 2D (horizontal and vertical)",
            "2. Initial velocity components: v0·cosθ, v0·sinθ",
            "3. Trajectory shape: parabola",
            "4. Key formulas: range, max height, flight time",
            "5. Worked example with given v0 and angle",
            "6. Interactive simulation on the whiteboard",
            "7. Exercises: vary angle, height and gravity",
        ],
        "lens": [
            "1. Thin lens types: converging and diverging",
            "2. Principal axis, focal points, optical center",
            "3. Lens equation: 1/f = 1/do + 1/di",
            "4. Magnification: m = -di/do",
            "5. Ray diagrams: three principal rays",
            "6. Image properties: real/virtual, upright/inverted",
            "7. Practice: draw ray diagram for f and object distance",
        ],
        "rc circuit": [
            "1. Series RC circuit components and symbols",
            "2. Capacitor charging and discharging equations",
            "3. Time constant τ = R·C",
            "4. Voltage and current as functions of time",
            "5. Steady-state and transient analysis",
            "6. Plot capacitor voltage vs. time",
            "7. Practice: calculate τ for given R and C",
        ],
        "dna": [
            "1. Structure: double helix of nucleotides",
            "2. Base pairing: A-T, C-G",
            "3. Sugar-phosphate backbone",
            "4. Hydrogen bonds between bases",
            "5. Replication overview",
            "6. Draw DNA helix on the whiteboard",
            "7. Quiz: name the complementary base",
        ],
        "general": [
            "1. State the learning objective",
            "2. Present key definitions and formulas",
            "3. Show one worked example",
            "4. Use an interactive whiteboard diagram",
            "5. Give a short exercise",
            "6. Summarize the lesson",
        ],
    }

    def __init__(self, parent: tk.Tk | None = None, app: "WhiteboardApp" | None = None) -> None:
        self.app = app
        self.outline = ""
        super().__init__(parent, title="AI Lesson Copilot")

    def body(self, master: tk.Frame) -> tk.Widget:
        tk.Label(master, text="Lesson topic (math/physics/chemistry):").grid(row=0, column=0, sticky="w")
        self.topic_var = tk.StringVar(value="derivative")
        self.topic_combo = ttk.Combobox(
            master,
            textvariable=self.topic_var,
            values=list(self.OUTLINES.keys()),
            state="readonly",
            width=25,
        )
        self.topic_combo.grid(row=0, column=1, sticky="ew", padx=4)
        tk.Button(master, text="Generate", command=self._generate).grid(row=0, column=2, padx=4)
        tk.Label(master, text="Suggested outline:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.text = tk.Text(master, width=60, height=14, wrap=tk.WORD)
        self.text.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=4)
        master.grid_rowconfigure(2, weight=1)
        master.grid_columnconfigure(1, weight=1)
        self._generate()
        return self.topic_combo

    def _generate(self) -> None:
        topic = self.topic_var.get().lower().strip()
        if not topic:
            topic = "general"
        # Fuzzy match topic keywords to outline templates
        matched = "general"
        for key in self.OUTLINES:
            if key in topic or any(kw in topic for kw in key.split()):
                matched = key
                break
        if matched == "general" and topic:
            # Try keyword matching for broader terms
            topic_map = {
                "deriv": "derivative", "differentiation": "derivative",
                "integral": "integral", "integration": "integral",
                "projectile": "projectile", "motion": "projectile",
                "lens": "lens", "optics": "lens",
                "rc": "rc circuit", "circuit": "rc circuit", "capacitor": "rc circuit",
                "dna": "dna", "helix": "dna", "biology": "dna",
            }
            for kw, key in topic_map.items():
                if kw in topic:
                    matched = key
                    break
        outline = f"Lesson: {topic}\n\n" + "\n".join(self.OUTLINES[matched])
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, outline)
        self.outline = outline

    def apply(self) -> None:
        self.outline = self.text.get("1.0", tk.END).strip()
        if self.app and self.outline:
            self.app._snapshot()
            obj = {
                "type": "text",
                "pos": (self.app.pan_x + 30 / self.app.zoom, self.app.pan_y + 30 / self.app.zoom),
                "text": self.outline,
                "size": 16 / self.app.zoom,
                "color": self.app.fg_color,
                "font_path": FONT_CANDIDATES[0],
            }
            self.app._append_object(obj)
            self.app.render()


class RecordingDialog(simpledialog.Dialog):
    """Settings for MP4 recording resolution, FPS and quality."""

    PRESETS: dict[str, tuple[int, int]] = {
        "720p (HD)": (1280, 720),
        "1080p (Full HD)": (1920, 1080),
        "2K": (2560, 1440),
        "4K (Ultra HD)": (3840, 2160),
        "8K": (7680, 4320),
    }

    def __init__(self, parent: tk.Tk | None = None, title: str = "Recording Settings") -> None:
        self.ok = False
        self.preset = "1080p (Full HD)"
        self.resolution: tuple[int, int] = self.PRESETS[self.preset]
        self.fps = 30
        self.quality = 8
        super().__init__(parent, title)

    def body(self, master: tk.Frame) -> tk.Widget:
        tk.Label(master, text="Resolution:").grid(row=0, column=0, sticky="w", pady=4)
        self.preset_var = tk.StringVar(value=self.preset)
        self.preset_combo = ttk.Combobox(master, values=list(self.PRESETS.keys()), state="readonly", textvariable=self.preset_var, width=18)
        self.preset_combo.grid(row=0, column=1, sticky="w", padx=4)

        tk.Label(master, text="FPS:").grid(row=1, column=0, sticky="w", pady=4)
        self.fps_var = tk.IntVar(value=self.fps)
        tk.Spinbox(master, from_=10, to=120, textvariable=self.fps_var, width=6).grid(row=1, column=1, sticky="w", padx=4)

        tk.Label(master, text="Quality (1-10):").grid(row=2, column=0, sticky="w", pady=4)
        self.quality_var = tk.IntVar(value=self.quality)
        tk.Spinbox(master, from_=1, to=10, textvariable=self.quality_var, width=6).grid(row=2, column=1, sticky="w", padx=4)

        return self.preset_combo

    def apply(self) -> None:
        self.preset = self.preset_var.get()
        self.resolution = self.PRESETS.get(self.preset, (1920, 1080))
        self.fps = self.fps_var.get()
        self.quality = self.quality_var.get()
        self.ok = True


# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

def _make_icon(name: str, size: int = 22, color: str = "#000000") -> ImageTk.PhotoImage:
    """Generate a small icon image for toolbars."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    c = color
    r = s // 2
    pad = 3
    if name == "pen":
        draw.polygon([(s - 2, 2), (s - 4, 8), (s - 8, 8), (2, s - 2), (4, s - 4), (s - 8, 4)], fill=c)
    elif name == "highlighter":
        _draw_rounded_rect(draw, [2, s // 2, s - 2, s - 2], 2, fill=c)
        draw.polygon([(s - 6, 2), (s - 2, 8), (2, s - 2)], fill=c)
    elif name == "eraser":
        draw.polygon([(2, s - 4), (6, 2), (s - 2, 2), (s - 2, 6), (s - 6, s - 2)], fill=c)
    elif name == "hand":
        draw.line([(s // 2, s - 2), (s // 2, 6)], fill=c, width=2)
        for x in [s // 2 - 4, s // 2, s // 2 + 4]:
            draw.line([(x, 4), (x, 10)], fill=c, width=2)
        draw.ellipse([s // 2 - 4, 2, s // 2 - 1, 5], fill=c)
    elif name == "line":
        draw.line([(pad, s - pad), (s - pad, pad)], fill=c, width=2)
    elif name == "arrow":
        draw.line([(pad, s - pad), (s - pad - 4, pad + 4)], fill=c, width=2)
        draw.polygon([(s - pad, pad), (s - pad - 6, pad), (s - pad - 2, pad + 6)], fill=c)
    elif name == "rect":
        draw.rectangle([pad, pad, s - pad, s - pad], outline=c, width=2)
    elif name == "oval":
        draw.ellipse([pad, pad, s - pad, s - pad], outline=c, width=2)
    elif name == "polygon":
        pts = [(s // 2, pad), (s - pad, s // 2 + 2), (s // 2 + 3, s - pad), (pad, s // 2)]
        draw.polygon(pts, outline=c, fill=None)
        for i in range(len(pts)):
            p = pts[i]
            draw.ellipse([p[0] - 1, p[1] - 1, p[0] + 1, p[1] + 1], fill=c)
    elif name == "ruler":
        draw.rectangle([pad, s // 3, s - pad, 2 * s // 3], outline=c, width=2)
        for x in range(pad, s - pad, 4):
            h = 3 if (x - pad) % 12 == 0 else 2
            draw.line([(x, s // 3 + 1), (x, s // 3 + h)], fill=c, width=1)
    elif name == "protractor":
        draw.arc([pad, pad, s - pad, s - pad], start=180, end=360, fill=c, width=2)
        draw.line([(s // 2, s // 2), (s - pad, s // 2)], fill=c, width=2)
    elif name == "compass":
        draw.ellipse([pad, pad, s - pad, s - pad], outline=c, width=2)
        draw.line([(s // 2, s // 2), (s - pad - 1, pad + 1)], fill=c, width=2)
        draw.line([(s // 2 - 3, s // 2), (s // 2 + 3, s // 2)], fill=c, width=1)
        draw.line([(s // 2, s // 2 - 3), (s // 2, s // 2 + 3)], fill=c, width=1)
    elif name == "measure":
        draw.line([(pad, s - pad), (s - pad, pad)], fill=c, width=2)
        draw.text((s // 2 - 3, s // 2 - 7), "L", fill=c)
    elif name == "text":
        draw.text((s // 2 - 4, pad - 1), "T", fill=c, font=ImageFont.load_default() if s < 16 else None)
    elif name == "new":
        draw.rounded_rectangle([pad, pad, s - pad, s - pad], radius=2, outline=c, width=2)
        draw.line([(s - pad - 4, pad + 2), (s - pad - 4, pad + 6), (s - pad - 8, pad + 6)], fill=c, width=2)
    elif name == "open":
        draw.polygon([(pad, s // 3), (s // 3, s // 3), (s // 3, pad), (2 * s // 3, pad), (s - pad, s // 3), (s - pad, s - pad), (pad, s - pad)], outline=c, fill=None, width=2)
    elif name == "save":
        draw.rounded_rectangle([pad, pad, s - pad, s - pad], radius=2, outline=c, width=2)
        draw.rounded_rectangle([pad + 3, pad + 2, s - pad - 3, s // 2 + 1], radius=1, fill=c)
        draw.line([(s // 2 - 2, s // 2 + 4), (s // 2 + 2, s // 2 + 4)], fill=c, width=2)
    elif name == "pdf":
        draw.rounded_rectangle([pad, pad, s - pad, s - pad], radius=2, outline=c, width=2)
        draw.text((pad + 1, s // 2 - 2), "PDF", fill=c, font=ImageFont.load_default())
    elif name == "undo":
        draw.arc([pad, pad, s - pad, s - pad], start=45, end=270, fill=c, width=2)
        draw.polygon([(pad + 3, pad + 3), (pad + 7, pad), (pad + 7, pad + 6)], fill=c)
    elif name == "redo":
        draw.arc([pad, pad, s - pad, s - pad], start=90, end=315, fill=c, width=2)
        draw.polygon([(s - pad - 3, pad + 3), (s - pad - 7, pad), (s - pad - 7, pad + 6)], fill=c)
    elif name == "color":
        draw.ellipse([pad, pad, s - pad, s - pad], fill=c)
        draw.ellipse([s // 2 + 1, s // 2 + 1, s - 2, s - 2], fill="#ffffff" if c != "#ffffff" else "#000000")
    elif name == "fullscreen":
        for x1, y1, x2, y2 in [(pad, pad, pad + 3, pad + 3), (s - pad - 3, pad, s - pad, pad + 3),
                               (pad, s - pad - 3, pad + 3, s - pad), (s - pad - 3, s - pad - 3, s - pad, s - pad)]:
            draw.line([(x1, y1), (x2, y2)], fill=c, width=2)
            draw.line([(x2, y1), (x2, y2)], fill=c, width=2)
            draw.line([(x1, y2), (x2, y2)], fill=c, width=2)
    elif name == "theme":
        draw.arc([pad, 2, s - pad, s - 2], start=0, end=180, fill=c, width=2)
        draw.polygon([(s - pad - 2, pad + 2), (s - 2, pad + 2), (s - pad - 2, s // 2 - 1)], fill=c)
    elif name == "zoom_in":
        draw.ellipse([pad, pad, s - pad - 2, s - pad - 2], outline=c, width=2)
        draw.line([(s - pad - 1, s - pad - 4), (s - 2, s - 2)], fill=c, width=2)
        draw.line([(s // 2 - 1, s // 2 - 3), (s // 2 - 1, s // 2 + 3)], fill=c, width=2)
        draw.line([(s // 2 - 4, s // 2), (s // 2 + 2, s // 2)], fill=c, width=2)
    elif name == "zoom_out":
        draw.ellipse([pad, pad, s - pad - 2, s - pad - 2], outline=c, width=2)
        draw.line([(s - pad - 1, s - pad - 4), (s - 2, s - 2)], fill=c, width=2)
        draw.line([(s // 2 - 4, s // 2), (s // 2 + 2, s // 2)], fill=c, width=2)
    elif name == "fit":
        draw.rectangle([pad, pad, s - pad, s - pad], outline=c, width=2)
        draw.rectangle([s // 2 - 2, s // 2 - 2, s - pad - 2, s - pad - 2], outline=c, width=2)
    elif name == "clear":
        draw.rectangle([pad, pad, s - pad, s - pad], outline=c, width=2)
        draw.line([(pad + 2, pad + 2), (s - pad - 2, s - pad - 2)], fill=c, width=2)
    elif name == "record":
        draw.ellipse([pad + 1, pad + 1, s - pad - 1, s - pad - 1], fill=c)
    elif name == "stop":
        draw.rectangle([pad + 2, pad + 2, s - pad - 2, s - pad - 2], fill=c)
    elif name == "ai":
        draw.text((pad + 1, pad - 2), "AI", fill=c, font=ImageFont.load_default())
    elif name == "dna":
        for i in range(3):
            y = pad + 3 + i * ((s - 2 * pad - 6) // 2)
            draw.arc([pad, y - 4, s - pad, y + 4], start=0, end=180, fill=c, width=1)
            draw.arc([pad, y - 4, s - pad, y + 4], start=180, end=360, fill=c, width=1)
    elif name == "lens":
        draw.ellipse([s // 2 - 3, pad, s // 2 + 3, s - pad], outline=c, width=2)
        draw.line([(pad, s // 2), (s // 2 - 3, s // 2)], fill=c, width=1)
        draw.line([(s // 2 + 3, s // 2), (s - pad, s // 2)], fill=c, width=1)
    elif name == "rc":
        draw.line([(pad, s // 2), (s // 3, s // 2)], fill=c, width=2)
        draw.rectangle([s // 3, s // 3, 2 * s // 3, 2 * s // 3], outline=c, width=2)
        draw.text((2 * s // 3 + 2, s // 2 - 6), "C", fill=c, font=ImageFont.load_default())
    elif name == "wire3d":
        draw.line([(pad, s - pad), (s // 3, s // 2)], fill=c, width=1)
        draw.line([(pad, pad), (s // 3, s // 2)], fill=c, width=1)
        draw.line([(pad, s - pad), (pad, pad)], fill=c, width=1)
        draw.line([(s // 3, s // 2), (s - pad, s // 2 - 4)], fill=c, width=1)
        draw.line([(pad, s - pad), (s - pad, s - pad)], fill=c, width=1)
        draw.line([(s - pad, s - pad), (s - pad, s // 2 - 4)], fill=c, width=1)
    elif name == "periodic":
        draw.rectangle([pad, pad, s - pad, s - pad], outline=c, width=2)
        draw.text((s // 2 - 5, s // 2 - 5), "Pt", fill=c, font=ImageFont.load_default())
    elif name == "wave":
        pts = [(pad + i, s // 2 + int(3 * math.sin(i * 0.5))) for i in range(s - 2 * pad)]
        draw.line(pts, fill=c, width=2)
    elif name == "vector":
        draw.line([(pad, s - pad), (s - pad - 6, pad + 6)], fill=c, width=2)
        draw.polygon([(s - pad, pad), (s - pad - 6, pad), (s - pad - 3, pad + 7)], fill=c)
    elif name == "molecule":
        r = 3
        draw.ellipse([s // 2 - r, s // 2 - r, s // 2 + r, s // 2 + r], fill=c)
        for dx, dy in [(-6, 4), (6, 4), (0, -7)]:
            x, y = s // 2 + dx, s // 2 + dy
            draw.ellipse([x - r, y - r, x + r, y + r], outline=c, width=2)
            draw.line([(s // 2, s // 2), (x, y)], fill=c, width=1)
    elif name == "atom":
        draw.ellipse([s // 2 - 2, s // 2 - 2, s // 2 + 2, s // 2 + 2], fill=c)
        draw.ellipse([pad, pad, s - pad, s - pad], outline=c, width=1)
    elif name == "pulley":
        draw.ellipse([s // 3, s // 4, 2 * s // 3, 3 * s // 4], outline=c, width=2)
        draw.line([(s // 2, 3 * s // 4), (s // 2, 2 * s // 3)], fill=c, width=2)
        draw.line([(pad, s - pad - 1), (s // 3, 3 * s // 4)], fill=c, width=2)
        draw.line([(2 * s // 3, 3 * s // 4), (s - pad, s - pad - 1)], fill=c, width=2)
    elif name == "incline":
        draw.polygon([(pad, s - pad), (s - pad, s - pad), (s - pad, pad + 4)], outline=c, fill=None, width=2)
        draw.rectangle([s // 2, s // 2, s // 2 + 5, s // 2 + 5], outline=c, fill=c, width=1)
    elif name == "axes":
        draw.line([(pad, s // 2), (s - pad, s // 2)], fill=c, width=2)
        draw.line([(s // 2, s - pad), (s // 2, pad)], fill=c, width=2)
        draw.polygon([(s - pad, s // 2), (s - pad - 4, s // 2 - 3), (s - pad - 4, s // 2 + 3)], fill=c)
        draw.polygon([(s // 2, pad), (s // 2 - 3, pad + 4), (s // 2 + 3, pad + 4)], fill=c)
    elif name == "image":
        draw.rectangle([pad, pad + 2, s - pad, s - pad], outline=c, width=2)
        draw.ellipse([pad + 4, pad + 5, pad + 8, pad + 9], fill=c)
        draw.polygon([(pad + 3, s - pad - 3), (s // 2, s // 2), (s - pad - 3, s - pad - 3)], fill=c)
    elif name == "select":
        draw.rectangle([pad, pad, s - pad, s - pad], outline=c, width=1)
        for cx, cy in [(pad, pad), (s - pad, pad), (pad, s - pad), (s - pad, s - pad)]:
            draw.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], fill=c)
    elif name == "pdfin":
        draw.rectangle([pad + 1, pad, s - pad - 1, s - pad], outline=c, width=2)
        draw.line([(s // 2, pad + 4), (s // 2, s // 2 + 2)], fill=c, width=2)
        draw.polygon([(s // 2 - 4, s // 2 - 1), (s // 2 + 4, s // 2 - 1), (s // 2, s // 2 + 4)], fill=c)
    else:
        draw.ellipse([pad, pad, s - pad, s - pad], outline=c, width=2)
    return ImageTk.PhotoImage(img)


class WhiteboardApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Interactive Whiteboard")
        self.root.geometry("1550x980")
        self.root.minsize(1000, 700)

        self.theme = "light"
        self.fg_color = DEFAULT_FG
        self.fill_color: str | None = None
        self.brush_size = 4
        self.tool_var = tk.StringVar(value="pen")
        self.fill_var = tk.BooleanVar(value=False)
        self.grid_size_var = tk.IntVar(value=GRID_SIZE)
        self.snap_var = tk.BooleanVar(value=False)
        self.sides_var = tk.IntVar(value=6)
        self.grid_size = GRID_SIZE
        self.bg_kind = "plain"
        self.recent_colors: list[str] = ["#000000", "#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa"]

        self.pressure_var = tk.IntVar(value=60)
        self.flow_var = tk.IntVar(value=100)
        self.sensitivity_var = tk.IntVar(value=40)

        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.viewport_w = DEFAULT_WIDTH
        self.viewport_h = DEFAULT_HEIGHT

        self.objects: list[dict] = []
        self.pages: list[dict] = []
        self.current_page_idx = 0
        self.top_button_icons: dict[ttk.Button, str] = {}

        self.layers: list[dict] = [{"name": "Layer 1", "visible": True}]
        self.current_layer = 0
        self._layer_vars: list[tk.BooleanVar] = []

        self._selected_idx: int | None = None
        self._move_start: tuple[float, float] | None = None
        self._move_orig: dict | None = None
        self._move_snapshot_done = False
        self._render_pending = False

        self.recording = False
        self._rec_writer = None
        self._rec_path: str | None = None
        self._rec_frame_count = 0
        self._rec_start_time: float | None = None
        self._rec_after_id: str | None = None
        self._rec_w: int = self.viewport_w
        self._rec_h: int = self.viewport_h
        self._rec_fps: int = REC_FPS
        self._rec_quality: int = 8

        self._new_page_dict("plain")
        self.bg_image: Image.Image | None = None
        self.style = ttk.Style(self.root)
        self._apply_theme()

        self._build_ui()
        self._bind_events()

        self._center_view()
        self._set_page(0)
        self._check_autosave()
        self.root.after(60000, self._autosave)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self._apply_theme()

        # Top toolbar
        top = ttk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=4, pady=2)

        self._add_toolbutton(top, "new", "New", self.new_board)
        self._add_toolbutton(top, "open", "Open", self.open_project)
        self._add_toolbutton(top, "save", "Save", self.save_project)
        self._add_toolbutton(top, "image", "Export Img", self.export_image)
        self._add_toolbutton(top, "pdf", "PDF", self.export_pdf)
        self._add_toolbutton(top, "pdf", "PDF All", self.export_all_pdf)
        self._add_toolbutton(top, "pdfin", "PDF In", self.import_pdf)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self._add_toolbutton(top, "undo", "Undo", self.undo)
        self._add_toolbutton(top, "redo", "Redo", self.redo)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(top, text="Color:").pack(side=tk.LEFT, padx=(6, 2))
        self.color_preview = tk.Canvas(
            top, width=24, height=24, bg=self.fg_color, highlightthickness=1,
            highlightbackground=self._theme("grid"), cursor="hand2"
        )
        self.color_preview.pack(side=tk.LEFT, padx=2)
        self.color_preview.bind("<Button-1>", lambda _e: self.pick_color())

        ttk.Label(top, text="Size:").pack(side=tk.LEFT, padx=(10, 2))
        self.size_var = tk.IntVar(value=self.brush_size)
        size_slider = ttk.Scale(top, from_=1, to=50, orient=tk.HORIZONTAL, variable=self.size_var, command=self._on_size_change, length=120)
        size_slider.pack(side=tk.LEFT, padx=2)
        self.size_label = ttk.Label(top, text=str(self.brush_size))
        self.size_label.pack(side=tk.LEFT, padx=2)

        # Zoom controls
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self._add_toolbutton(top, "zoom_out", "Zoom -", self.zoom_out)
        self.zoom_label = ttk.Label(top, text="100%")
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        self._add_toolbutton(top, "zoom_in", "Zoom +", self.zoom_in)
        self._add_toolbutton(top, "fit", "Fit", self.zoom_fit)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self._add_toolbutton(top, "theme", "Theme", self.toggle_theme)
        self._add_toolbutton(top, "fullscreen", "Full", self.toggle_fullscreen)
        self.rec_btn = self._add_toolbutton(top, "record", "REC", self.toggle_recording)

        # Page toolbar
        page_bar = ttk.Frame(self.root)
        page_bar.pack(side=tk.TOP, fill=tk.X, padx=4, pady=2)

        ttk.Button(page_bar, text="New Page", command=self.add_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(page_bar, text="< Prev", command=self.prev_page).pack(side=tk.LEFT, padx=2)
        self.page_label = ttk.Label(page_bar, text="Page 1 / 1")
        self.page_label.pack(side=tk.LEFT, padx=6)
        ttk.Button(page_bar, text="Next >", command=self.next_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(page_bar, text="Delete Page", command=self.delete_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(page_bar, text="Clear", command=self.clear).pack(side=tk.RIGHT, padx=2)

        # Left tool panel (scrollable so every feature stays reachable)
        left_outer = ttk.Frame(self.root, width=150)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left_outer.pack_propagate(False)

        self._left_canvas = tk.Canvas(left_outer, width=150, highlightthickness=0,
                                      bg=self._theme("ui_bg"))
        left_scroll = ttk.Scrollbar(left_outer, orient="vertical",
                                    command=self._left_canvas.yview)
        self._left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left = ttk.Frame(self._left_canvas)
        _left_win = self._left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _left_configure(_event=None):
            self._left_canvas.configure(scrollregion=self._left_canvas.bbox("all"))
            self._left_canvas.itemconfigure(_left_win, width=self._left_canvas.winfo_width())

        left.bind("<Configure>", _left_configure)
        self._left_canvas.bind("<Configure>", _left_configure)

        def _left_wheel(event):
            self._left_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

        def _left_enter(_event=None):
            self.root.bind_all("<MouseWheel>", _left_wheel, add="+")

        def _left_leave(_event=None):
            self.root.unbind_all("<MouseWheel>")

        left_outer.bind("<Enter>", _left_enter)
        left_outer.bind("<Leave>", _left_leave)

        ttk.Label(left, text="Tools", font=("", 10, "bold")).pack(pady=(6, 4))

        tools = [
            ("select", "Select"),
            ("pen", "Pen"),
            ("highlighter", "Highlighter"),
            ("eraser", "Eraser"),
            ("hand", "Hand"),
            ("line", "Line"),
            ("arrow", "Arrow"),
            ("rect", "Rectangle"),
            ("oval", "Oval"),
            ("polygon", "Polygon"),
            ("ruler", "Ruler"),
            ("protractor", "Protractor"),
            ("compass", "Compass"),
            ("measure", "Measure"),
            ("text", "Text"),
        ]

        tool_frame = ttk.Frame(left)
        tool_frame.pack(fill=tk.X, padx=2)

        self.tool_buttons: dict[str, tk.Radiobutton] = {}
        for icon_name, label in tools:
            rb = tk.Radiobutton(
                tool_frame,
                text=label,
                image=self.icons.get(icon_name),
                variable=self.tool_var,
                value=icon_name,
                indicatoron=False,
                compound=tk.TOP,
                cursor="hand2",
                relief=tk.RAISED,
                bd=1,
            )
            rb.pack(fill=tk.X, pady=1)
            self.tool_buttons[icon_name] = rb

        # Pen dynamics
        dyn_frame = ttk.Labelframe(left, text="Pen Dynamics")
        dyn_frame.pack(fill=tk.X, pady=8, padx=2)

        self._add_slider_row(dyn_frame, "Pressure", self.pressure_var, self._on_pressure_change)
        self._add_slider_row(dyn_frame, "Flow", self.flow_var, self._on_flow_change)
        self._add_slider_row(dyn_frame, "Sensitivity", self.sensitivity_var, self._on_sensitivity_change)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Fill option
        fill_frame = ttk.Frame(left)
        fill_frame.pack(fill=tk.X, pady=2, padx=2)
        ttk.Checkbutton(fill_frame, text="Fill", variable=self.fill_var, command=self._toggle_fill).pack(side=tk.LEFT)
        self.fill_preview = tk.Canvas(
            fill_frame, width=20, height=20, bg="white",
            highlightthickness=1, highlightbackground=self._theme("grid"), cursor="hand2"
        )
        self.fill_preview.pack(side=tk.LEFT, padx=4)
        self.fill_preview.bind("<Button-1>", lambda _e: self.pick_fill_color())

        # Recent colors
        ttk.Label(left, text="Recent colors", font=("", 9, "bold")).pack(pady=(4, 2))
        self.recent_frame = ttk.Frame(left)
        self.recent_frame.pack(fill=tk.X, pady=2, padx=2)
        self._build_recent_palette()

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Math / View panel
        math_frame = ttk.Labelframe(left, text="Math / View")
        math_frame.pack(fill=tk.X, pady=4, padx=2)

        ttk.Label(math_frame, text="Background:").pack(anchor=tk.W, pady=(4, 0), padx=4)
        self.bg_combo = ttk.Combobox(
            math_frame, values=list(BG_LABELS.values()), state="readonly", width=16
        )
        self.bg_combo.set(BG_LABELS["plain"])
        self.bg_combo.bind("<<ComboboxSelected>>", self._on_bg_change)
        self.bg_combo.pack(fill=tk.X, pady=2, padx=4)

        ttk.Checkbutton(math_frame, text="Snap to grid", variable=self.snap_var).pack(anchor=tk.W, pady=2, padx=4)

        sides_frame = ttk.Frame(math_frame)
        sides_frame.pack(fill=tk.X, pady=2, padx=4)
        ttk.Label(sides_frame, text="Sides:").pack(side=tk.LEFT)
        tk.Spinbox(sides_frame, from_=3, to=30, width=5, textvariable=self.sides_var).pack(side=tk.LEFT, padx=4)

        grid_frame = ttk.Frame(math_frame)
        grid_frame.pack(fill=tk.X, pady=2, padx=4)
        ttk.Label(grid_frame, text="Grid:").pack(side=tk.LEFT)
        tk.Spinbox(grid_frame, from_=5, to=100, width=5, textvariable=self.grid_size_var, command=self._on_grid_size_change).pack(side=tk.LEFT, padx=4)

        ttk.Button(math_frame, text="Graph Function", command=lambda: self.root.event_generate("<<PlotGraph>>", when="tail")).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Math Assistant", command=self.math_assistant).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Projectile", command=self.projectile_sim).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Exercise", command=self.generate_exercise).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Worksheet Maker", command=self.open_worksheet_generator).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="AI Copilot", command=self.ai_copilot).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Periodic Table", command=self.open_periodic_table).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Chemistry Library", command=self.open_chemistry_library).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="DNA Helix", command=self.insert_dna).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="Thin Lens", command=self.insert_lens).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="RC Circuit", command=self.insert_rc_circuit).pack(fill=tk.X, pady=2, padx=4)
        ttk.Button(math_frame, text="3D Shape", command=self.insert_3d_shape).pack(fill=tk.X, pady=2, padx=4)

        # Layers panel
        layers_frame = ttk.Labelframe(left, text="Layers")
        layers_frame.pack(fill=tk.X, pady=4, padx=2)

        layer_row = ttk.Frame(layers_frame)
        layer_row.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(layer_row, text="+", width=3, command=self.add_layer).pack(side=tk.LEFT)
        ttk.Button(layer_row, text="-", width=3, command=self.delete_layer).pack(side=tk.LEFT, padx=2)
        self.layer_combo = ttk.Combobox(layer_row, state="readonly", width=10)
        self.layer_combo.bind("<<ComboboxSelected>>", self._on_active_layer_change)
        self.layer_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.layer_vis_frame = ttk.Frame(layers_frame)
        self.layer_vis_frame.pack(fill=tk.X, padx=4, pady=(2, 4))
        self._rebuild_layer_ui()

        # Science tools panel
        science_frame = ttk.Labelframe(left, text="Physics / Chemistry")
        science_frame.pack(fill=tk.X, pady=4, padx=2)

        science_tools = [
            ("wave", "Wave", self.insert_wave),
            ("vector", "Vector", self.insert_vector),
            ("molecule", "Molecule", self.insert_molecule),
            ("atom", "Atom", self.insert_atom),
            ("pulley", "Pulley", self.insert_pulley),
            ("incline", "Incline", self.insert_incline),
            ("axes", "Axes", self.insert_axes),
        ]
        self.science_button_icons: dict[tk.Widget, str] = {}
        for icon_name, label, cmd in science_tools:
            btn = ttk.Button(science_frame, image=self.icons.get(icon_name), text=label, compound=tk.LEFT, command=cmd)
            btn.pack(fill=tk.X, pady=1, padx=2)
            self.science_button_icons[btn] = icon_name

        # Canvas
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.canvas = tk.Canvas(
            canvas_frame, bg=self._hex(self._theme("bg")), cursor="crosshair", highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.photo = ImageTk.PhotoImage(Image.new("RGBA", (self.viewport_w, self.viewport_h), self._theme("bg") + (255,)))
        self.canvas_image = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        self._apply_tool_button_theme()

        # Status bar
        self.status_bar = ttk.Frame(self.root)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=2)
        self.status_zoom = ttk.Label(self.status_bar, text="100%")
        self.status_zoom.pack(side=tk.LEFT, padx=4)
        ttk.Separator(self.status_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        self.status_page = ttk.Label(self.status_bar, text="Page 1 / 1")
        self.status_page.pack(side=tk.LEFT, padx=4)
        ttk.Separator(self.status_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        self.status_rec = ttk.Label(self.status_bar, text="", foreground="#e53935")
        self.status_rec.pack(side=tk.LEFT, padx=4)
        self.status_msg = ttk.Label(self.status_bar, text="Ready")
        self.status_msg.pack(side=tk.RIGHT, padx=4)

    def _add_toolbutton(self, parent: tk.Widget, icon_name: str, text: str, command) -> ttk.Button:
        btn = ttk.Button(parent, image=self.icons.get(icon_name), text=text, compound=tk.LEFT, command=command)
        btn.pack(side=tk.LEFT, padx=1)
        self.top_button_icons[btn] = icon_name
        return btn

    def _add_slider_row(self, parent: tk.Widget, label: str, var: tk.IntVar, command) -> None:
        f = ttk.Frame(parent)
        f.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(f, text=label, width=11).pack(side=tk.LEFT)
        lbl = ttk.Label(f, text=f"{var.get()}%")
        lbl.pack(side=tk.RIGHT)
        sc = ttk.Scale(f, from_=0, to=100, orient=tk.HORIZONTAL, variable=var, command=lambda v, l=lbl: self._update_slider_label(v, l))
        sc.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        var.trace_add("write", lambda *_a, c=command: c())

    def _update_slider_label(self, value: str, label: ttk.Label) -> None:
        label.config(text=f"{int(float(value))}%")

    def _build_icons(self) -> None:
        color = self._theme("fg")
        self.icons: dict[str, ImageTk.PhotoImage] = {}
        for name in [
            "new", "open", "save", "pdf", "undo", "redo", "color", "fullscreen",
            "theme", "zoom_in", "zoom_out", "fit", "clear", "pen", "highlighter",
            "eraser", "hand", "line", "arrow", "rect", "oval", "polygon", "ruler",
            "protractor", "compass", "measure", "text", "record", "stop", "ai",
            "dna", "lens", "rc", "wire3d", "periodic", "wave", "vector", "molecule",
            "atom", "pulley", "incline", "axes", "image", "select", "pdfin",
        ]:
            self.icons[name] = _make_icon(name, size=22, color=color)
        self.icons["record"] = _make_icon("record", size=22, color="#e53935")
        self.icons["stop"] = _make_icon("stop", size=22, color="#e53935")

    def _apply_theme(self) -> None:
        self._build_icons()
        bg = self._theme("ui_bg")
        fg = self._theme("ui_fg")
        select = self._theme("select")
        accent = self._theme("accent")
        button = self._theme("button")
        button_active = self._theme("button_active")

        self.style.configure(".", background=bg, foreground=fg, fieldbackground=button)
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("TButton", background=button, foreground=fg, bordercolor=bg)
        self.style.map("TButton", background=[("active", button_active), ("pressed", select)])
        self.style.configure("TRadiobutton", background=bg, foreground=fg)
        self.style.configure("TCheckbutton", background=bg, foreground=fg)
        self.style.configure("TScale", background=bg, troughcolor=button)
        self.style.configure("TSpinbox", fieldbackground=button, foreground=fg)
        self.style.configure("TCombobox", fieldbackground=button, foreground=fg)
        self.style.map("TCombobox", fieldbackground=[("readonly", button)])
        self.style.configure("TEntry", fieldbackground=button, foreground=fg)
        self.style.configure("TLabelframe", background=bg, foreground=fg)
        self.style.configure("TLabelframe.Label", background=bg, foreground=fg)

        if hasattr(self, "canvas"):
            self.canvas.config(bg=self._hex(self._theme("bg")))
        if hasattr(self, "_left_canvas"):
            self._left_canvas.config(bg=self._theme("ui_bg"))

        if hasattr(self, "color_preview"):
            self.color_preview.config(bg=self.fg_color, highlightbackground=self._theme("grid"))
        if hasattr(self, "fill_preview"):
            self.fill_preview.config(highlightbackground=self._theme("grid"))

        self._apply_tool_button_theme()

    def _apply_tool_button_theme(self) -> None:
        if hasattr(self, "tool_buttons"):
            theme = THEMES[self.theme]
            bg = theme["button"]
            fg = theme["fg"]
            select = theme["select"]
            active = theme["button_active"]
            for tool, rb in self.tool_buttons.items():
                img = self.icons.get(tool)
                rb.config(
                    image=img, selectimage=img,
                    bg=bg, fg=fg, selectcolor=select,
                    activebackground=active, activeforeground=fg,
                )
        for btn, name in self.top_button_icons.items():
            try:
                btn.config(image=self.icons.get(name))
            except tk.TclError:
                pass
        for btn, name in getattr(self, "science_button_icons", {}).items():
            try:
                btn.config(image=self.icons.get(name))
            except tk.TclError:
                pass

    def _theme(self, key: str):
        return THEMES[self.theme][key]

    def _hex(self, rgb: tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % rgb

    # ------------------------------------------------------------------ Events
    def _bind_events(self) -> None:
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-2>", self._pan_press)
        self.canvas.bind("<B2-Motion>", self._pan_drag)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<Configure>", self._on_configure)
        self.tool_var.trace_add("write", self._on_tool_change)

        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-o>", lambda e: self.open_project())
        self.root.bind("<Control-e>", lambda e: self.export_image())
        self.root.bind("<Control-n>", lambda e: self.new_board())
        self.root.bind("<Control-equal>", lambda e: self.zoom_in())
        self.root.bind("<Control-minus>", lambda e: self.zoom_out())
        self.root.bind("<Control-0>", lambda e: self.zoom_fit())
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Delete>", lambda e: self.delete_selected())
        self.root.bind("<Escape>", lambda e: self.deselect())
        self.root.bind("<<PlotGraph>>", lambda e: self.plot_function())

    def _on_tool_change(self, *_args: object) -> None:
        tool = self.current_tool
        if tool == "hand":
            self.canvas.config(cursor="fleur")
        elif tool == "select":
            self.canvas.config(cursor="arrow")
        else:
            self.canvas.config(cursor="crosshair")

    def _on_configure(self, event: tk.Event | None = None) -> None:
        new_w = max(1, self.canvas.winfo_width())
        new_h = max(1, self.canvas.winfo_height())
        if self.viewport_w == new_w and self.viewport_h == new_h:
            return
        old_cx = self.pan_x + (self.viewport_w / 2.0) / self.zoom
        old_cy = self.pan_y + (self.viewport_h / 2.0) / self.zoom
        self.viewport_w, self.viewport_h = new_w, new_h
        if not hasattr(self, "_view_initialized"):
            self._center_view()
            self._view_initialized = True
        else:
            self.pan_x = old_cx - (self.viewport_w / 2.0) / self.zoom
            self.pan_y = old_cy - (self.viewport_h / 2.0) / self.zoom
        self.request_render()

    def _center_view(self) -> None:
        self.pan_x = -(self.viewport_w / 2.0) / self.zoom
        self.pan_y = -(self.viewport_h / 2.0) / self.zoom

    # ------------------------------------------------------------------ Coordinate helpers
    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (self.pan_x + sx / self.zoom, self.pan_y + sy / self.zoom)

    def _world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return ((wx - self.pan_x) * self.zoom, (wy - self.pan_y) * self.zoom)

    def _coords(self, event: tk.Event) -> tuple[float, float]:
        return float(event.x), float(event.y)

    def _world_coords(self, event: tk.Event) -> tuple[float, float]:
        return self._screen_to_world(float(event.x), float(event.y))

    def _snap(self, wx: float, wy: float) -> tuple[float, float]:
        if not self.snap_var.get():
            return wx, wy
        g = self.grid_size
        return round(wx / g) * g, round(wy / g) * g

    def _constrain(self, sx: float, sy: float, wx: float, wy: float, tool: str) -> tuple[float, float]:
        dx, dy = wx - sx, wy - sy
        if tool in ("line", "arrow", "measure", "ruler", "protractor", "compass"):
            r = math.hypot(dx, dy)
            if r < 1e-6:
                return wx, wy
            angle = math.atan2(dy, dx)
            snap = round(angle / (math.pi / 4)) * (math.pi / 4)
            return sx + r * math.cos(snap), sy + r * math.sin(snap)
        if tool in ("rect", "oval"):
            side = max(abs(dx), abs(dy))
            if side == 0:
                return wx, wy
            return sx + math.copysign(side, dx), sy + math.copysign(side, dy)
        return wx, wy

    def _screen_brush(self) -> float:
        return max(1.0, self.brush_size * (0.5 + 0.5 * self.pressure_var.get() / 100.0))

    # ------------------------------------------------------------------ UI actions
    def _on_size_change(self, value: str) -> None:
        self.brush_size = max(1, int(float(value)))
        self.size_label.config(text=str(self.brush_size))

    def _on_pressure_change(self) -> None:
        pass

    def _on_flow_change(self) -> None:
        pass

    def _on_sensitivity_change(self) -> None:
        pass

    def toggle_theme(self) -> None:
        self.theme = "dark" if self.theme == "light" else "light"
        self._apply_theme()
        self.render()

    @property
    def current_tool(self) -> str:
        return self.tool_var.get()

    def _current_page(self) -> dict:
        return self.pages[self.current_page_idx]

    def _append_object(self, obj: dict) -> None:
        """Central creation point: tag new objects with the active layer."""
        obj.setdefault("layer", min(self.current_layer, max(0, len(self.layers) - 1)))
        self.objects.append(obj)

    # ------------------------------------------------------------------ Layers
    def _layer_visible(self, obj: dict) -> bool:
        idx = obj.get("layer", 0)
        return 0 <= idx < len(self.layers) and self.layers[idx]["visible"]

    def add_layer(self) -> None:
        self.layers.append({"name": f"Layer {len(self.layers) + 1}", "visible": True})
        self.current_layer = len(self.layers) - 1
        self._rebuild_layer_ui()

    def delete_layer(self) -> None:
        if len(self.layers) <= 1:
            messagebox.showwarning("Layers", "You must keep at least one layer.")
            return
        idx = self.current_layer
        if not messagebox.askyesno(
            "Delete Layer", f"Delete '{self.layers[idx]['name']}' and all of its objects?"
        ):
            return
        self._snapshot()
        self.objects = [o for o in self.objects if o.get("layer", 0) != idx]
        for o in self.objects:
            lay = o.get("layer", 0)
            if lay > idx:
                o["layer"] = lay - 1
        del self.layers[idx]
        self.current_layer = min(idx, len(self.layers) - 1)
        self._selected_idx = None
        self._rebuild_layer_ui()
        self.render()

    def _on_active_layer_change(self, _event: tk.Event | None = None) -> None:
        self.current_layer = max(0, self.layer_combo.current())

    def _toggle_layer_visible(self, idx: int) -> None:
        if 0 <= idx < len(self.layers):
            self.layers[idx]["visible"] = bool(self._layer_vars[idx].get())
            self.render()

    def _rebuild_layer_ui(self) -> None:
        if not hasattr(self, "layer_vis_frame"):
            return
        for widget in self.layer_vis_frame.winfo_children():
            widget.destroy()
        names = [l["name"] for l in self.layers]
        self.layer_combo["values"] = names
        self.layer_combo.current(min(self.current_layer, len(names) - 1))
        self._layer_vars = []
        for i, lyr in enumerate(self.layers):
            var = tk.BooleanVar(value=lyr["visible"])
            self._layer_vars.append(var)
            tk.Checkbutton(
                self.layer_vis_frame,
                text=lyr["name"],
                variable=var,
                command=lambda i=i: self._toggle_layer_visible(i),
            ).pack(anchor=tk.W)

    def _set_active_layer(self, idx: int) -> None:
        if 0 <= idx < len(self.layers):
            self.current_layer = idx
            if hasattr(self, "layer_combo"):
                self.layer_combo.current(idx)

    def _set_color(self, color: str) -> None:
        self.fg_color = color
        self.color_preview.config(bg=color)
        self._add_recent_color(color)

    def _add_recent_color(self, color: str) -> None:
        if color in self.recent_colors:
            self.recent_colors.remove(color)
        self.recent_colors.insert(0, color)
        self.recent_colors = self.recent_colors[:8]
        self._build_recent_palette()

    def _build_recent_palette(self) -> None:
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        for color in self.recent_colors:
            btn = tk.Button(
                self.recent_frame, bg=color, width=2, height=1, relief=tk.RIDGE, bd=2,
                command=lambda c=color: self._set_color(c)
            )
            btn.pack(side=tk.LEFT, padx=1)

    @property
    def _effective_fill(self) -> str | None:
        return self.fill_color if self.fill_var.get() else None

    def _toggle_fill(self) -> None:
        if self.fill_var.get() and not self.fill_color:
            self.fill_color = self.fg_color
            self.fill_preview.config(bg=self.fill_color)

    def pick_fill_color(self) -> None:
        color = colorchooser.askcolor(color=self.fill_color or self.fg_color, title="Choose fill color")[1]
        if color:
            self.fill_color = color
            self.fill_preview.config(bg=color)
            self.fill_var.set(True)

    def pick_color(self) -> None:
        color = colorchooser.askcolor(color=self.fg_color, title="Choose color")[1]
        if color:
            self._set_color(color)

    # ------------------------------------------------------------------ Rendering
    def request_render(self) -> None:
        """Coalesce bursty render requests into one redraw per event-loop cycle."""
        if self._render_pending:
            return
        self._render_pending = True
        self.root.after_idle(self._do_pending_render)

    def _do_pending_render(self) -> None:
        self._render_pending = False
        self.render()

    def render(self) -> None:
        w, h = self.viewport_w, self.viewport_h
        bg = self._theme("bg") + (255,)
        viewport = Image.new("RGBA", (w, h), bg)
        draw = ImageDraw.Draw(viewport)
        self._render_background(viewport, draw, w, h)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for obj in self.objects:
            if not self._layer_visible(obj):
                continue
            self._render_object(od, obj)

        viewport = Image.alpha_composite(viewport, overlay)
        self.photo = ImageTk.PhotoImage(viewport)
        self.canvas.itemconfig(self.canvas_image, image=self.photo)
        self._update_selection_ui()
        zoom_text = f"{int(self.zoom * 100)}%"
        self.zoom_label.config(text=zoom_text)
        if hasattr(self, "status_zoom"):
            self.status_zoom.config(text=zoom_text)
        if self.recording:
            self._queue_record_frame()

    def _render_background(self, img: Image.Image, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        bg = self._theme("bg")
        grid_color = self._theme("grid")
        axis_color = self._theme("axis")

        if self.bg_kind == "image" and self.bg_image is not None:
            img = self.bg_image
            sx1 = int(self.pan_x)
            sy1 = int(self.pan_y)
            sx2 = int(math.ceil(self.pan_x + w / self.zoom))
            sy2 = int(math.ceil(self.pan_y + h / self.zoom))
            sx1 = max(0, min(sx1, img.width))
            sy1 = max(0, min(sy1, img.height))
            sx2 = max(0, min(sx2, img.width))
            sy2 = max(0, min(sy2, img.height))
            if sx2 > sx1 and sy2 > sy1:
                crop = img.crop((sx1, sy1, sx2, sy2))
                nw = max(1, int((sx2 - sx1) * self.zoom))
                nh = max(1, int((sy2 - sy1) * self.zoom))
                resized = crop.resize((nw, nh), Image.LANCZOS)
                dx = int((sx1 - self.pan_x) * self.zoom)
                dy = int((sy1 - self.pan_y) * self.zoom)
                img.paste(resized, (dx, dy))
            return

        if self.bg_kind == "dark":
            draw.rectangle([0, 0, w, h], fill=bg)
            grid_color = "#546e7a"
            axis_color = "#78909c"
        else:
            draw.rectangle([0, 0, w, h], fill=bg)

        left, top = self._screen_to_world(0, 0)
        right, bottom = self._screen_to_world(w, h)

        if self.bg_kind in ("plain", "dark"):
            return

        g = self.grid_size
        # Adaptive density: keep grid cells at a visible screen size when zoomed out
        while g * self.zoom < 8:
            g *= 2

        if self.bg_kind in ("grid", "dots"):
            x = math.floor(left / g) * g
            while x <= right:
                sx, _ = self._world_to_screen(x, 0)
                if self.bg_kind == "grid":
                    draw.line([(int(sx), 0), (int(sx), h)], fill=grid_color, width=1)
                else:
                    y = math.floor(top / g) * g
                    while y <= bottom:
                        sx2, sy2 = self._world_to_screen(x, y)
                        draw.ellipse([int(sx2) - 1, int(sy2) - 1, int(sx2) + 1, int(sy2) + 1], fill=grid_color)
                        y += g
                x += g

            if self.bg_kind == "grid":
                y = math.floor(top / g) * g
                while y <= bottom:
                    _, sy = self._world_to_screen(0, y)
                    draw.line([(0, int(sy)), (w, int(sy))], fill=grid_color, width=1)
                    y += g

            if abs(left) <= right - left or abs(right) <= right - left:
                _, cx = self._world_to_screen(0, 0)
                draw.line([(int(cx), 0), (int(cx), h)], fill=axis_color, width=2)
            if abs(top) <= bottom - top or abs(bottom) <= bottom - top:
                cy, _ = self._world_to_screen(0, 0)
                draw.line([(0, int(cy)), (w, int(cy))], fill=axis_color, width=2)

        elif self.bg_kind == "lined":
            y = math.floor(top / g) * g
            while y <= bottom:
                _, sy = self._world_to_screen(0, y)
                draw.line([(0, int(sy)), (w, int(sy))], fill=grid_color, width=1)
                y += g

        elif self.bg_kind == "iso":
            m = math.sqrt(3)
            step = g
            # Horizontal
            y = math.floor(top / step) * step
            while y <= bottom:
                _, sy = self._world_to_screen(0, y)
                draw.line([(0, int(sy)), (w, int(sy))], fill=grid_color, width=1)
                y += step
            # Positive slope
            x0 = math.floor((left - (bottom - top) / m) / step) * step
            while x0 <= right + (bottom - top) / m:
                y_at_left = m * (left - x0)
                y_at_right = m * (right - x0)
                sy1, _ = self._world_to_screen(0, y_at_left + top)
                sy2, _ = self._world_to_screen(0, y_at_right + top)
                if max(y_at_left, y_at_right) >= top and min(y_at_left, y_at_right) <= bottom:
                    draw.line([(0, int(sy1)), (w, int(sy2))], fill=grid_color, width=1)
                x0 += step
            # Negative slope
            x0 = math.floor((left - (bottom - top) / m) / step) * step
            while x0 <= right + (bottom - top) / m:
                y_at_left = -m * (left - x0)
                y_at_right = -m * (right - x0)
                sy1, _ = self._world_to_screen(0, y_at_left + top)
                sy2, _ = self._world_to_screen(0, y_at_right + top)
                if max(y_at_left, y_at_right) >= top and min(y_at_left, y_at_right) <= bottom:
                    draw.line([(0, int(sy1)), (w, int(sy2))], fill=grid_color, width=1)
                x0 += step

    def _render_object(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        kind = obj.get("type")
        w, h = self.viewport_w, self.viewport_h
        bbox = self._obj_bbox(obj)
        if bbox:
            bx1, by1, bx2, by2 = bbox
            sr = (self._world_to_screen(bx2, by2)[0] < 0 or self._world_to_screen(bx1, by1)[0] > w or
                  self._world_to_screen(bx2, by2)[1] < 0 or self._world_to_screen(bx1, by1)[1] > h)
            if sr:
                return

        if kind == "pen":
            pts = obj["points"]
            if len(pts) < 2:
                return
            widths = obj.get("widths")
            color = hex_to_rgba(obj["color"], obj.get("alpha", 255))
            screen_pts = [self._world_to_screen(*p) for p in pts]
            if not widths or max(widths) - min(widths) < 1e-6:
                w_world = widths[0] if widths else obj["width"]
                width = max(1, int(w_world * self.zoom))
                draw.line(screen_pts, fill=color, width=width, joint="curve")
                r = width / 2.0
                for p in (screen_pts[0], screen_pts[-1]):
                    draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)
                return
            for i in range(len(pts) - 1):
                ww = widths[i] * self.zoom
                width = max(1, int(ww))
                draw.line([screen_pts[i], screen_pts[i + 1]], fill=color, width=width, joint="curve")
                p1 = screen_pts[i]
                draw.ellipse([p1[0] - width / 2, p1[1] - width / 2, p1[0] + width / 2, p1[1] + width / 2], fill=color)
            last = screen_pts[-1]
            width = max(1, int(widths[-1] * self.zoom))
            draw.ellipse([last[0] - width / 2, last[1] - width / 2, last[0] + width / 2, last[1] + width / 2], fill=color)

        elif kind == "highlighter":
            pts = obj["points"]
            if len(pts) < 2:
                return
            color = hex_to_rgba(obj["color"], obj.get("alpha", 100))
            screen_pts = [self._world_to_screen(*p) for p in pts]
            width = max(1, int(obj["width"] * self.zoom))
            draw.line(screen_pts, fill=color, width=width, joint="curve")

        elif kind == "line":
            p1 = self._world_to_screen(*obj["p1"])
            p2 = self._world_to_screen(*obj["p2"])
            width = max(1, int(obj["width"] * self.zoom))
            draw.line([p1, p2], fill=obj["color"], width=width)

        elif kind == "arrow":
            p1 = self._world_to_screen(*obj["p1"])
            p2 = self._world_to_screen(*obj["p2"])
            width = max(1, int(obj["width"] * self.zoom))
            draw.line([p1, p2], fill=obj["color"], width=width)
            head = [self._world_to_screen(*pt) for pt in obj["head"]]
            if head:
                draw.polygon(head, fill=obj["color"], outline=obj["color"])

        elif kind == "rect":
            x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
            p1 = self._world_to_screen(x1, y1)
            p2 = self._world_to_screen(x2, y2)
            width = max(1, int(obj["width"] * self.zoom))
            coords = [p1[0], p1[1], p2[0], p2[1]]
            fill = self._parse_fill(obj.get("fill"))
            draw.rectangle(coords, fill=fill, outline=obj["color"], width=width)

        elif kind == "oval":
            p1 = self._world_to_screen(obj["x1"], obj["y1"])
            p2 = self._world_to_screen(obj["x2"], obj["y2"])
            width = max(1, int(obj["width"] * self.zoom))
            fill = self._parse_fill(obj.get("fill"))
            draw.ellipse([p1[0], p1[1], p2[0], p2[1]], fill=fill, outline=obj["color"], width=width)

        elif kind == "polygon":
            pts = [self._world_to_screen(*p) for p in obj["points"]]
            width = max(1, int(obj["width"] * self.zoom))
            fill = self._parse_fill(obj.get("fill"))
            if fill:
                draw.polygon(pts, fill=fill, outline=obj["color"])
            else:
                draw.line(pts + [pts[0]], fill=obj["color"], width=width, joint="curve")

        elif kind == "text":
            pos = self._world_to_screen(*obj["pos"])
            size = max(1, int(obj["size"] * self.zoom))
            font = self._load_font(obj.get("font_path", FONT_CANDIDATES[0]), size)
            self._draw_multiline_text(draw, pos, obj["text"], font, obj["color"], anchor="lt")

        elif kind == "measure":
            p1 = self._world_to_screen(*obj["p1"])
            p2 = self._world_to_screen(*obj["p2"])
            width = max(1, int(obj["width"] * self.zoom))
            self._draw_dashed_line(draw, p1, p2, obj["color"], width)
            text = obj["label"]
            size = max(8, int(14 * self.zoom))
            font = self._get_font(size)
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 12 * self.zoom)
            self._draw_multiline_text(draw, mid, text, font, obj["color"], anchor="mm")

        elif kind == "ruler":
            p1 = self._world_to_screen(*obj["p1"])
            p2 = self._world_to_screen(*obj["p2"])
            width = max(1, int(obj["width"] * self.zoom))
            draw.line([p1, p2], fill=obj["color"], width=width)
            ux, uy = self._unit(p1, p2)
            if ux is not None:
                px, py = -uy, ux
                tick = self.grid_size
                wx1, wy1 = obj["p1"]
                wx2, wy2 = obj["p2"]
                r_world = math.hypot(wx2 - wx1, wy2 - wy1)
                step_world = max(tick, 1)
                for dist in self._frange(0, r_world, step_world):
                    cx = wx1 + dist * ux
                    cy = wy1 + dist * uy
                    csc = self._world_to_screen(cx, cy)
                    major = (int(round(dist / step_world)) % 5 == 0)
                    length = 8 / self.zoom if major else 4 / self.zoom
                    s1 = self._world_to_screen(cx + px * length, cy + py * length)
                    s2 = self._world_to_screen(cx - px * length, cy - py * length)
                    draw.line([s1, s2], fill=obj["color"], width=max(1, int(width / 2)))
            text = obj["label"]
            size = max(8, int(14 * self.zoom))
            font = self._get_font(size)
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 12 * self.zoom)
            draw.text(mid, text, fill=obj["color"], font=font, anchor="mm")

        elif kind == "protractor":
            cx, cy = obj["center"]
            r = obj["radius"]
            angle = obj["angle"]
            sc = self._world_to_screen(cx, cy)
            sr = int(r * self.zoom)
            if sr < 2:
                return
            color = obj["color"]
            width = max(1, int(obj["width"] * self.zoom))
            pts = []
            for a in range(0, int(angle) + 1, 2):
                rad = math.radians(a)
                pts.append((sc[0] + sr * math.cos(rad), sc[1] - sr * math.sin(rad)))
            draw.line(pts, fill=color, width=width)
            for a in range(0, int(angle) + 1, 10):
                rad = math.radians(a)
                x1 = sc[0] + (sr - 5) * math.cos(rad)
                y1 = sc[1] - (sr - 5) * math.sin(rad)
                x2 = sc[0] + sr * math.cos(rad)
                y2 = sc[1] - sr * math.sin(rad)
                draw.line([(x1, y1), (x2, y2)], fill=color, width=max(1, width // 2))
            draw.line([sc, (sc[0] + sr, sc[1])], fill=color, width=width)
            p2 = self._world_to_screen(*obj["p2"])
            draw.line([sc, p2], fill=color, width=width)
            mid = (sc[0] + sr * 0.6 * math.cos(math.radians(angle / 2)),
                   sc[1] - sr * 0.6 * math.sin(math.radians(angle / 2)))
            size = max(8, int(14 * self.zoom))
            font = self._get_font(size)
            draw.text(mid, f"{angle:.1f}°", fill=color, font=font, anchor="mm")

        elif kind == "compass":
            cx, cy = obj["center"]
            r = obj["radius"]
            sc = self._world_to_screen(cx, cy)
            sr = int(r * self.zoom)
            color = obj["color"]
            width = max(1, int(obj["width"] * self.zoom))
            if sr >= 2:
                draw.ellipse([sc[0] - sr, sc[1] - sr, sc[0] + sr, sc[1] + sr], outline=color, width=width)
            p2 = self._world_to_screen(*obj["p2"])
            draw.line([sc, p2], fill=color, width=width)
            cr = max(3 / self.zoom, obj["width"])
            s1 = self._world_to_screen(cx - cr, cy)
            s2 = self._world_to_screen(cx + cr, cy)
            s3 = self._world_to_screen(cx, cy - cr)
            s4 = self._world_to_screen(cx, cy + cr)
            draw.line([s1, s2], fill=color, width=max(1, width // 2))
            draw.line([s3, s4], fill=color, width=max(1, width // 2))
            mid = ((sc[0] + p2[0]) / 2, (sc[1] + p2[1]) / 2 - 12 * self.zoom)
            size = max(8, int(14 * self.zoom))
            font = self._get_font(size)
            draw.text(mid, f"r={r:.1f}", fill=color, font=font, anchor="mm")

        elif kind == "function":
            self._render_function(draw, obj)

        elif kind == "projectile":
            self._render_projectile(draw, obj)

        elif kind == "dna":
            self._render_dna(draw, obj)

        elif kind == "lens":
            self._render_lens(draw, obj)

        elif kind == "rc":
            self._render_rc_circuit(draw, obj)

        elif kind == "wire3d":
            self._render_wire3d(draw, obj)

        elif kind == "wave":
            self._render_wave(draw, obj)

        elif kind == "vector":
            self._render_vector(draw, obj)

        elif kind == "molecule":
            self._render_molecule(draw, obj)

        elif kind == "atom":
            self._render_atom(draw, obj)

        elif kind == "pulley":
            self._render_pulley(draw, obj)

        elif kind == "incline":
            self._render_incline(draw, obj)

        elif kind == "axes":
            self._render_axes(draw, obj)

    def _parse_fill(self, fill: str | None) -> tuple[int, int, int, int] | None:
        if not fill:
            return None
        return hex_to_rgba(fill, 255)

    def _draw_dashed_line(self, draw: ImageDraw.ImageDraw, p1: tuple[float, float], p2: tuple[float, float], color: str, width: int) -> None:
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        dist = math.hypot(dx, dy)
        if dist < 1:
            return
        ux, uy = dx / dist, dy / dist
        on = 6 * self.zoom
        off = 4 * self.zoom
        pos = 0.0
        drawing = True
        while pos < dist:
            seg = on if drawing else off
            end = min(pos + seg, dist)
            a = (p1[0] + ux * pos, p1[1] + uy * pos)
            b = (p1[0] + ux * end, p1[1] + uy * end)
            if drawing:
                draw.line([a, b], fill=color, width=width)
            pos = end
            drawing = not drawing

    def _unit(self, p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float | None, float | None]:
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        r = math.hypot(dx, dy)
        if r < 1:
            return None, None
        return dx / r, dy / r

    def _frange(self, start: float, stop: float, step: float):
        d = start
        while d <= stop:
            yield d
            d += step

    def _obj_bbox(self, obj: dict) -> tuple[float, float, float, float] | None:
        kind = obj.get("type")
        if kind in ("pen", "highlighter"):
            pts = obj["points"]
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (min(xs), min(ys), max(xs), max(ys))
        if kind in ("line", "arrow", "measure", "ruler"):
            return (min(obj["p1"][0], obj["p2"][0]), min(obj["p1"][1], obj["p2"][1]),
                    max(obj["p1"][0], obj["p2"][0]), max(obj["p1"][1], obj["p2"][1]))
        if kind in ("rect", "oval"):
            return (min(obj["x1"], obj["x2"]), min(obj["y1"], obj["y2"]),
                    max(obj["x1"], obj["x2"]), max(obj["y1"], obj["y2"]))
        if kind == "polygon":
            pts = obj["points"]
            if not pts:
                return None
            return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        if kind == "text":
            size = obj["size"]
            lines = obj["text"].split("\n")
            w = max(len(line) for line in lines) * size * 0.6 if lines else size
            h = len(lines) * size * 1.3
            return (obj["pos"][0], obj["pos"][1], obj["pos"][0] + w, obj["pos"][1] + h)
        if kind in ("protractor", "compass"):
            cx, cy = obj["center"]
            r = obj["radius"]
            return (cx - r, cy - r, cx + r, cy + r)
        if kind == "function":
            return (obj["origin"][0] - 1000 * obj["scale"], obj["origin"][1] - 1000 * obj["scale"],
                    obj["origin"][0] + 1000 * obj["scale"], obj["origin"][1] + 1000 * obj["scale"])
        if kind == "projectile":
            origin = obj["origin"]
            r = obj["range"] * obj["scale"]
            h = obj["max_height"] * obj["scale"]
            return (origin[0], origin[1] - h, origin[0] + r, origin[1])
        if kind == "vector":
            tx, ty = obj["tail"]
            hx, hy = obj["head"]
            return (min(tx, hx), min(ty, hy), max(tx, hx), max(ty, hy))
        if kind in ("dna", "lens", "rc", "wave", "incline", "axes"):
            return (min(obj["x1"], obj["x2"]), min(obj["y1"], obj["y2"]),
                    max(obj["x1"], obj["x2"]), max(obj["y1"], obj["y2"]))
        if kind == "wire3d":
            cx, cy = obj["center"]
            s = obj["size"]
            return (cx - s, cy - s, cx + s, cy + s)
        if kind == "molecule":
            cx, cy = obj["center"]
            s = obj["size"]
            return (cx - s, cy - s, cx + s, cy + s)
        if kind == "atom":
            cx, cy = obj["center"]
            s = obj["size"]
            return (cx - s, cy - s, cx + s, cy + s)
        if kind == "pulley":
            x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        return None

    # ------------------------------------------------------------------ Fonts
    def _get_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for name in FONT_CANDIDATES:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _load_font(self, name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            return self._get_font(size)

    def _text_bbox(self, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str, anchor: str = "lt") -> tuple[int, int, int, int]:
        try:
            return draw.textbbox((0, 0), text, font=font, anchor=anchor)
        except TypeError:
            return draw.textbbox((0, 0), text, font=font)

    def _draw_multiline_text(self, draw: ImageDraw.ImageDraw, pos: tuple[float, float], text: str, font: ImageFont.ImageFont, color: str, anchor: str = "lt") -> None:
        text = _shape_bidi_text(text)
        lines = text.split("\n")
        if anchor == "mm":
            heights: list[float] = []
            for line in lines:
                bbox = self._text_bbox(draw, font, line, "mm")
                heights.append(bbox[3] - bbox[1])
            total = sum(heights)
            y = pos[1] - total / 2
            for line, h in zip(lines, heights):
                draw.text((pos[0], y + h / 2), line, fill=color, font=font, anchor="mm")
                y += h
        else:
            y = pos[1]
            for line in lines:
                bbox = self._text_bbox(draw, font, line, anchor)
                h = bbox[3] - bbox[1]
                draw.text((pos[0], y), line, fill=color, font=font, anchor=anchor)
                y += h

    # ------------------------------------------------------------------ Zoom / pan
    def zoom_in(self, factor: float = 1.2, at: tuple[float, float] | None = None) -> None:
        self._zoom_by(factor, at)

    def zoom_out(self, factor: float = 0.833, at: tuple[float, float] | None = None) -> None:
        self._zoom_by(factor, at)

    def _zoom_by(self, factor: float, at: tuple[float, float] | None = None) -> None:
        old = self.zoom
        new = max(MIN_ZOOM, min(MAX_ZOOM, old * factor))
        if new == old:
            return
        sx = at[0] if at else self.viewport_w / 2.0
        sy = at[1] if at else self.viewport_h / 2.0
        wx = self.pan_x + sx / old
        wy = self.pan_y + sy / old
        self.zoom = new
        self.pan_x = wx - sx / new
        self.pan_y = wy - sy / new
        self.request_render()

    def zoom_fit(self) -> None:
        bbox = self._content_bbox()
        if bbox:
            bx1, by1, bx2, by2 = bbox
            margin = 40 / self.zoom
            bw, bh = bx2 - bx1 + 2 * margin, by2 - by1 + 2 * margin
            self.zoom = min(self.viewport_w / bw, self.viewport_h / bh, MAX_ZOOM)
            self.zoom = max(MIN_ZOOM, self.zoom)
            self.pan_x = bx1 - margin
            self.pan_y = by1 - margin
        else:
            self.zoom = 1.0
            self._center_view()
        self.render()

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.zoom_in(at=(event.x, event.y))
        elif event.num == 5 or getattr(event, "delta", 0) < 0:
            self.zoom_out(at=(event.x, event.y))

    def _pan_press(self, event: tk.Event) -> None:
        self._pan_start = (event.x, event.y)
        self._pan_start_view = (self.pan_x, self.pan_y)

    def _pan_drag(self, event: tk.Event) -> None:
        if not hasattr(self, "_pan_start"):
            return
        dx = event.x - self._pan_start[0]
        dy = event.y - self._pan_start[1]
        self.pan_x = self._pan_start_view[0] - dx / self.zoom
        self.pan_y = self._pan_start_view[1] - dy / self.zoom
        self.request_render()

    def _content_bbox(self) -> tuple[float, float, float, float] | None:
        boxes = []
        for obj in self.objects:
            b = self._obj_bbox(obj)
            if b:
                boxes.append(b)
        if self.bg_kind == "image" and self.bg_image is not None:
            boxes.append((0, 0, self.bg_image.width, self.bg_image.height))
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    # ------------------------------------------------------------------ Snapshot / undo
    def _snapshot(self) -> None:
        page = self._current_page()
        if len(page["undo_stack"]) >= UNDO_LIMIT:
            page["undo_stack"].pop(0)
        page["undo_stack"].append(_copy_objects(self.objects))
        page["redo_stack"].clear()

    def undo(self, _event: tk.Event | None = None) -> None:
        page = self._current_page()
        if not page["undo_stack"]:
            return
        page["redo_stack"].append(_copy_objects(self.objects))
        self.objects = page["undo_stack"].pop()
        self._selected_idx = None
        self.render()

    def redo(self, _event: tk.Event | None = None) -> None:
        page = self._current_page()
        if not page["redo_stack"]:
            return
        page["undo_stack"].append(_copy_objects(self.objects))
        self.objects = page["redo_stack"].pop()
        self._selected_idx = None
        self.render()

    # ------------------------------------------------------------------ Pages
    def _new_page_dict(self, kind: str) -> None:
        self.pages.append({
            "objects": [],
            "bg_kind": kind,
            "bg_image": None,
            "undo_stack": [],
            "redo_stack": [],
        })

    def _store_page(self) -> None:
        page = self._current_page()
        page["objects"] = _copy_objects(self.objects)
        page["bg_kind"] = self.bg_kind
        page["bg_image"] = self.bg_image.copy() if self.bg_image else None

    def _set_page(self, idx: int, store: bool = True) -> None:
        if store:
            self._store_page()
        self.current_page_idx = idx
        page = self.pages[idx]
        self.objects = _copy_objects(page["objects"])
        self.bg_kind = page["bg_kind"]
        self.bg_image = page["bg_image"].copy() if page["bg_image"] else None
        self._selected_idx = None
        self.bg_combo.set(BG_LABELS[self.bg_kind])
        self._update_page_label()
        self.render()

    def _update_page_label(self) -> None:
        text = f"Page {self.current_page_idx + 1} / {len(self.pages)}"
        self.page_label.config(text=text)
        if hasattr(self, "status_page"):
            self.status_page.config(text=text)

    def add_page(self) -> None:
        self._store_page()
        self._new_page_dict("plain")
        self._set_page(len(self.pages) - 1, store=False)

    def prev_page(self) -> None:
        if self.current_page_idx > 0:
            self._set_page(self.current_page_idx - 1)

    def next_page(self) -> None:
        if self.current_page_idx < len(self.pages) - 1:
            self._set_page(self.current_page_idx + 1)

    def delete_page(self) -> None:
        if len(self.pages) <= 1:
            messagebox.showwarning("Cannot delete", "You must keep at least one page.")
            return
        del self.pages[self.current_page_idx]
        if self.current_page_idx >= len(self.pages):
            self.current_page_idx = len(self.pages) - 1
        self._set_page(self.current_page_idx, store=False)

    # ------------------------------------------------------------------ Stroke smoothing
    def _smooth_stroke(self, points: list[tuple[float, float]], widths: list[float], iterations: int = 2) -> tuple[list[tuple[float, float]], list[float]]:
        """Laplacian-like smoothing that preserves end points."""
        if len(points) < 3:
            return points[:], widths[:]
        # Each point has an associated half-width from the two neighbouring segments
        assoc = [widths[0]] + [(widths[i - 1] + widths[i]) / 2.0 for i in range(1, len(widths))] + [widths[-1]]
        for _ in range(iterations):
            new_pts: list[tuple[float, float]] = [points[0]]
            new_assoc: list[float] = [assoc[0]]
            for i in range(1, len(points) - 1):
                x = 0.25 * points[i - 1][0] + 0.5 * points[i][0] + 0.25 * points[i + 1][0]
                y = 0.25 * points[i - 1][1] + 0.5 * points[i][1] + 0.25 * points[i + 1][1]
                new_pts.append((x, y))
                new_assoc.append(0.25 * assoc[i - 1] + 0.5 * assoc[i] + 0.25 * assoc[i + 1])
            new_pts.append(points[-1])
            new_assoc.append(assoc[-1])
            points = new_pts
            assoc = new_assoc
        new_widths = [(assoc[i] + assoc[i + 1]) / 2.0 for i in range(len(assoc) - 1)]
        return points, new_widths

    # ------------------------------------------------------------------ Drawing event handlers
    def on_press(self, event: tk.Event) -> None:
        sx, sy = self._coords(event)
        if self.current_tool == "hand":
            self._pan_press(event)
            return
        wx, wy = self._screen_to_world(sx, sy)
        if self.current_tool == "select":
            self._select_press(wx, wy)
            return
        if self.current_tool in ("line", "arrow", "rect", "oval", "polygon", "measure", "ruler", "protractor", "compass"):
            wx, wy = self._snap(wx, wy)
        self._start_world = (wx, wy)
        self._last_world = (wx, wy)
        self._last_time = time.perf_counter()
        self._stroke_points: list[tuple[float, float]] = [(wx, wy)]
        self._stroke_widths: list[float] = []
        self._stroke_times: list[float] = [self._last_time]
        self.temp_shape = None
        self.temp_text = None

        if self.current_tool == "text":
            self._place_text(wx, wy)

    def on_drag(self, event: tk.Event) -> None:
        sx, sy = self._coords(event)
        if self.current_tool == "hand":
            self._pan_drag(event)
            return
        wx, wy = self._screen_to_world(sx, sy)
        if self.current_tool == "select":
            self._select_drag(wx, wy)
            return
        if self.current_tool in ("line", "arrow", "rect", "oval", "polygon", "measure", "ruler", "protractor", "compass"):
            wx, wy = self._snap(wx, wy)
        if event.state & 0x1:
            wx, wy = self._constrain(self._start_world[0], self._start_world[1], wx, wy, self.current_tool)

        tool = self.current_tool
        p1 = self._world_to_screen(*self._start_world)
        p2 = self._world_to_screen(wx, wy)

        if tool in ("pen", "highlighter"):
            now = time.perf_counter()
            dt = now - self._last_time
            dist = math.hypot(wx - self._last_world[0], wy - self._last_world[1])
            if dist < 0.5 / self.zoom:
                return
            v = dist / max(dt, 0.001)
            v_norm = min(v / 1000.0, 1.0)
            base_w = self._screen_brush() / self.zoom
            sens = self.sensitivity_var.get() / 100.0
            pressure_factor = 0.5 + 0.5 * self.pressure_var.get() / 100.0
            width_world = base_w * pressure_factor * (1.0 + sens * (1.0 - v_norm))
            width_world = max(0.5 / self.zoom, width_world)
            self._stroke_points.append((wx, wy))
            self._stroke_widths.append(width_world)
            self._stroke_times.append(now)
            self._last_world = (wx, wy)
            self._last_time = now

            screen_pts = [self._world_to_screen(*p) for p in self._stroke_points[-2:]]
            w_screen = max(1, int(width_world * self.zoom))
            if tool == "highlighter":
                w_screen = max(1, int(w_screen * 2))
                alpha = int(255 * self.flow_var.get() / 100.0 * 0.65)
                self.canvas.create_line(
                    *screen_pts[0], *screen_pts[1], fill=self.fg_color,
                    width=w_screen, capstyle=tk.ROUND, joinstyle=tk.ROUND,
                    stipple="gray50", tags="stroke_preview"
                )
            else:
                alpha = int(255 * self.flow_var.get() / 100.0)
                color = self._hex(hex_to_rgba(self.fg_color, alpha)[:3])
                self.canvas.create_line(
                    *screen_pts[0], *screen_pts[1], fill=color,
                    width=w_screen, capstyle=tk.ROUND, joinstyle=tk.ROUND,
                    tags="stroke_preview"
                )

        elif tool == "eraser":
            self._stroke_points.append((wx, wy))
            self.canvas.delete("stroke_preview")
            r = max(self.brush_size * 2, 4) / self.zoom
            for i, p in enumerate(self._stroke_points):
                if i == 0:
                    continue
                sc = self._world_to_screen(p[0], p[1])
                scp = self._world_to_screen(self._stroke_points[i - 1][0], self._stroke_points[i - 1][1])
                self.canvas.create_line(scp[0], scp[1], sc[0], sc[1], fill=self._hex(self._theme("select")), width=2, tags="stroke_preview")
                self.canvas.create_oval(sc[0] - r * self.zoom, sc[1] - r * self.zoom, sc[0] + r * self.zoom, sc[1] + r * self.zoom, outline="#ff5722", tags="stroke_preview")

        elif tool in ("line", "rect", "oval", "arrow"):
            self._clear_preview()
            fill = self._effective_fill
            if tool == "line":
                self.temp_shape = self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=self.fg_color, width=self.brush_size, capstyle=tk.ROUND, tags="shape_preview")
            elif tool == "arrow":
                head, _sides, start, tip = self._arrow_points_world(self._start_world, (wx, wy))
                shead = [self._world_to_screen(*pt) for pt in head]
                sstart = self._world_to_screen(*start)
                stip = self._world_to_screen(*tip)
                self.canvas.create_line(sstart[0], sstart[1], stip[0], stip[1], fill=self.fg_color, width=self.brush_size, capstyle=tk.ROUND, tags="shape_preview")
                if shead:
                    self.temp_shape = self.canvas.create_polygon(*[c for pt in shead for c in pt], fill=self.fg_color, outline=self.fg_color, tags="shape_preview")
            elif tool == "rect":
                f = self._hex(self._parse_fill(fill)[:3]) if fill else ""
                self.temp_shape = self.canvas.create_rectangle(p1[0], p1[1], p2[0], p2[1], outline=self.fg_color, fill=f, width=self.brush_size, tags="shape_preview")
            elif tool == "oval":
                f = self._hex(self._parse_fill(fill)[:3]) if fill else ""
                self.temp_shape = self.canvas.create_oval(p1[0], p1[1], p2[0], p2[1], outline=self.fg_color, fill=f, width=self.brush_size, tags="shape_preview")

        elif tool == "polygon":
            self._preview_polygon(wx, wy)
        elif tool == "measure":
            self._preview_measure(wx, wy)
        elif tool == "ruler":
            self._preview_ruler(wx, wy)
        elif tool == "protractor":
            self._preview_protractor(wx, wy)
        elif tool == "compass":
            self._preview_compass(wx, wy)

    def on_release(self, event: tk.Event) -> None:
        if self.current_tool == "hand":
            return
        sx, sy = self._coords(event)
        wx, wy = self._screen_to_world(sx, sy)
        if self.current_tool == "select":
            self._select_release()
            return
        if self.current_tool in ("line", "arrow", "rect", "oval", "polygon", "measure", "ruler", "protractor", "compass"):
            wx, wy = self._snap(wx, wy)
        if event.state & 0x1:
            wx, wy = self._constrain(self._start_world[0], self._start_world[1], wx, wy, self.current_tool)

        tool = self.current_tool

        if tool in ("pen", "highlighter"):
            self.canvas.delete("stroke_preview")
            if len(self._stroke_points) > 1:
                self._snapshot()
                alpha = int(255 * self.flow_var.get() / 100.0)
                if tool == "highlighter":
                    alpha = int(255 * self.flow_var.get() / 100.0 * 0.65)
                pts, wds = self._smooth_stroke(self._stroke_points, self._stroke_widths)
                self._append_object({
                    "type": tool,
                    "points": pts,
                    "widths": wds,
                    "width": wds[0] if wds else self._screen_brush() / self.zoom,
                    "color": self.fg_color,
                    "alpha": alpha,
                })
                self.render()

        elif tool == "eraser":
            self.canvas.delete("stroke_preview")
            if len(self._stroke_points) > 1:
                self._snapshot()
                self._erase(self._stroke_points)
                self.render()

        elif tool in ("line", "rect", "oval", "arrow"):
            self._clear_preview()
            self._snapshot()
            if tool == "line":
                self._append_object({"type": "line", "p1": self._start_world, "p2": (wx, wy), "color": self.fg_color, "width": self.brush_size / self.zoom})
            elif tool == "arrow":
                head, _, _s, _t = self._arrow_points_world(self._start_world, (wx, wy))
                self._append_object({"type": "arrow", "p1": self._start_world, "p2": (wx, wy), "head": head, "color": self.fg_color, "width": self.brush_size / self.zoom})
            elif tool == "rect":
                self._append_object({"type": "rect", "x1": self._start_world[0], "y1": self._start_world[1], "x2": wx, "y2": wy, "color": self.fg_color, "width": self.brush_size / self.zoom, "fill": self._effective_fill})
            elif tool == "oval":
                self._append_object({"type": "oval", "x1": self._start_world[0], "y1": self._start_world[1], "x2": wx, "y2": wy, "color": self.fg_color, "width": self.brush_size / self.zoom, "fill": self._effective_fill})
            self.render()

        elif tool == "polygon":
            self._draw_polygon(wx, wy)
        elif tool == "measure":
            self._draw_measure(wx, wy)
        elif tool == "ruler":
            self._draw_ruler(wx, wy)
        elif tool == "protractor":
            self._draw_protractor(wx, wy)
        elif tool == "compass":
            self._draw_compass(wx, wy)

    def _clear_preview(self) -> None:
        self.canvas.delete("shape_preview")
        if self.temp_shape is not None:
            self.canvas.delete(self.temp_shape)
            self.temp_shape = None
        if self.temp_text is not None:
            self.canvas.delete(self.temp_text)
            self.temp_text = None

    # ------------------------------------------------------------------ Selection tool
    HIT_TOL_PX = 8.0

    def _hit_tolerance(self) -> float:
        return self.HIT_TOL_PX / self.zoom

    def _obj_hit(self, obj: dict, wx: float, wy: float, tol: float) -> bool:
        kind = obj.get("type")
        if kind in ("pen", "highlighter"):
            pts = obj["points"]
            if len(pts) == 1:
                return math.hypot(wx - pts[0][0], wy - pts[0][1]) <= tol
            for i in range(len(pts) - 1):
                if self._point_to_segment((wx, wy), pts[i], pts[i + 1]) <= tol:
                    return True
            return False
        if kind in ("line", "arrow", "measure", "ruler"):
            return self._point_to_segment((wx, wy), obj["p1"], obj["p2"]) <= tol
        if kind == "vector":
            return self._point_to_segment((wx, wy), obj["tail"], obj["head"]) <= max(tol, 6 / self.zoom)
        if kind == "polygon":
            pts = obj["points"]
            n = len(pts)
            for i in range(n):
                if self._point_to_segment((wx, wy), pts[i], pts[(i + 1) % n]) <= tol:
                    return True
            return False
        b = self._obj_bbox(obj)
        if not b:
            return False
        return b[0] - tol <= wx <= b[2] + tol and b[1] - tol <= wy <= b[3] + tol

    def _hit_test(self, wx: float, wy: float) -> int | None:
        tol = self._hit_tolerance()
        for idx in range(len(self.objects) - 1, -1, -1):
            obj = self.objects[idx]
            if not self._layer_visible(obj):
                continue
            if self._obj_hit(obj, wx, wy, tol):
                return idx
        return None

    def _translate_object(self, obj: dict, dx: float, dy: float) -> None:
        """Translate every world coordinate of an object by (dx, dy)."""
        def tp(p: tuple[float, float]) -> tuple[float, float]:
            return (p[0] + dx, p[1] + dy)

        kind = obj.get("type")
        if kind in ("pen", "highlighter", "polygon"):
            obj["points"] = [tp(p) for p in obj["points"]]
        elif kind == "text":
            obj["pos"] = tp(obj["pos"])
        elif kind in ("line", "measure", "ruler"):
            obj["p1"] = tp(obj["p1"])
            obj["p2"] = tp(obj["p2"])
        elif kind == "arrow":
            obj["p1"] = tp(obj["p1"])
            obj["p2"] = tp(obj["p2"])
            obj["head"] = [tp(p) for p in obj.get("head", [])]
        elif kind in ("rect", "oval", "dna", "lens", "rc", "wave", "incline", "axes", "pulley"):
            obj["x1"] += dx
            obj["y1"] += dy
            obj["x2"] += dx
            obj["y2"] += dy
        elif kind in ("protractor", "compass"):
            obj["center"] = tp(obj["center"])
            obj["p2"] = tp(obj["p2"])
        elif kind in ("function", "projectile"):
            obj["origin"] = tp(obj["origin"])
        elif kind == "vector":
            obj["tail"] = tp(obj["tail"])
            obj["head"] = tp(obj["head"])
        elif kind in ("wire3d", "molecule", "atom"):
            obj["center"] = tp(obj["center"])

    def _select_press(self, wx: float, wy: float) -> None:
        idx = self._hit_test(wx, wy)
        self._selected_idx = idx
        self._move_start = (wx, wy) if idx is not None else None
        self._move_orig = _copy_value(self.objects[idx]) if idx is not None else None
        self._move_snapshot_done = False
        if idx is not None:
            self._set_active_layer(self.objects[idx].get("layer", 0))
        self.render()

    def _select_drag(self, wx: float, wy: float) -> None:
        if self._selected_idx is None or self._move_orig is None or self._move_start is None:
            return
        dx = wx - self._move_start[0]
        dy = wy - self._move_start[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return
        if not self._move_snapshot_done:
            self._snapshot()
            self._move_snapshot_done = True
        obj = _copy_value(self._move_orig)
        self._translate_object(obj, dx, dy)
        self.objects[self._selected_idx] = obj
        self.request_render()

    def _select_release(self) -> None:
        self._move_orig = None
        self._move_start = None

    def delete_selected(self) -> None:
        if self._selected_idx is None:
            return
        if not (0 <= self._selected_idx < len(self.objects)):
            self._selected_idx = None
            return
        self._snapshot()
        del self.objects[self._selected_idx]
        self._selected_idx = None
        self.render()

    def deselect(self, _event: tk.Event | None = None) -> None:
        if self._selected_idx is not None:
            self._selected_idx = None
            self.render()

    def _update_selection_ui(self) -> None:
        self.canvas.delete("selection_ui")
        idx = self._selected_idx
        if idx is None:
            return
        if not (0 <= idx < len(self.objects)):
            self._selected_idx = None
            return
        b = self._obj_bbox(self.objects[idx])
        if not b:
            return
        sx1, sy1 = self._world_to_screen(b[0], b[1])
        sx2, sy2 = self._world_to_screen(b[2], b[3])
        pad = 5
        self.canvas.create_rectangle(
            sx1 - pad, sy1 - pad, sx2 + pad, sy2 + pad,
            outline=self._theme("accent"), dash=(5, 3), width=1, tags="selection_ui",
        )

    def _arrow_points_world(self, p1: tuple[float, float], p2: tuple[float, float]) -> tuple[list[tuple[float, float]], list[tuple[tuple[float, float], tuple[float, float]]], tuple[float, float], tuple[float, float]]:
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        r = math.hypot(dx, dy)
        if r < 1e-6:
            return [p1], [], p1, p2
        ux, uy = dx / r, dy / r
        px, py = -uy, ux
        head_len = max(self.brush_size * 3 / self.zoom, 12 / self.zoom)
        head_width = head_len * 0.6
        tip = p2
        back = (p2[0] - ux * head_len, p2[1] - uy * head_len)
        left = (back[0] + px * head_width, back[1] + py * head_width)
        right = (back[0] - px * head_width, back[1] - py * head_width)
        return [back, left, tip, right], [(tip, left), (tip, right)], p1, tip

    def _preview_polygon(self, wx: float, wy: float) -> None:
        self._clear_preview()
        cx, cy = self._start_world
        radius = math.hypot(wx - cx, wy - cy)
        if radius < 2 / self.zoom:
            return
        n = max(3, int(self.sides_var.get()))
        angle = math.atan2(wy - cy, wx - cx)
        pts = []
        for i in range(n):
            a = angle + 2 * math.pi * i / n
            px = cx + radius * math.cos(a)
            py = cy + radius * math.sin(a)
            pts.extend(self._world_to_screen(px, py))
        fill = self._effective_fill
        f = self._hex(self._parse_fill(fill)[:3]) if fill else ""
        self.temp_shape = self.canvas.create_polygon(*pts, outline=self.fg_color, fill=f, width=self.brush_size, tags="shape_preview")

    def _draw_polygon(self, wx: float, wy: float) -> None:
        self._clear_preview()
        cx, cy = self._start_world
        radius = math.hypot(wx - cx, wy - cy)
        if radius < 2 / self.zoom:
            return
        self._snapshot()
        n = max(3, int(self.sides_var.get()))
        angle = math.atan2(wy - cy, wx - cx)
        pts = []
        for i in range(n):
            a = angle + 2 * math.pi * i / n
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        self._append_object({"type": "polygon", "points": pts, "color": self.fg_color, "width": self.brush_size / self.zoom, "fill": self._effective_fill})
        self.render()

    def _preview_measure(self, wx: float, wy: float) -> None:
        self._clear_preview()
        p1 = self._world_to_screen(*self._start_world)
        p2 = self._world_to_screen(wx, wy)
        self.temp_shape = self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=self.fg_color, width=self.brush_size, dash=(4, 4), tags="shape_preview")
        dx, dy = wx - self._start_world[0], wy - self._start_world[1]
        length = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx))
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 12 * self.zoom)
        self.temp_text = self.canvas.create_text(mid[0], mid[1], text=f"L={length:.1f}\nθ={angle:.1f}°", fill=self.fg_color, anchor=tk.CENTER, tags="shape_preview")

    def _draw_measure(self, wx: float, wy: float) -> None:
        self._clear_preview()
        self._snapshot()
        dx, dy = wx - self._start_world[0], wy - self._start_world[1]
        length = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx))
        self._append_object({
            "type": "measure",
            "p1": self._start_world,
            "p2": (wx, wy),
            "color": self.fg_color,
            "width": self.brush_size / self.zoom,
            "label": f"L={length:.1f}\nθ={angle:.1f}°",
        })
        self.render()

    def _preview_ruler(self, wx: float, wy: float) -> None:
        self._clear_preview()
        p1 = self._world_to_screen(*self._start_world)
        p2 = self._world_to_screen(wx, wy)
        self.temp_shape = self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=self.fg_color, width=self.brush_size, tags="shape_preview")
        dx, dy = wx - self._start_world[0], wy - self._start_world[1]
        r = math.hypot(dx, dy)
        if r > 1 / self.zoom:
            ux, uy = dx / r, dy / r
            px, py = -uy, ux
            tick = self.grid_size
            for dist in self._frange(0, r, tick):
                major = (int(round(dist / tick)) % 5 == 0)
                length = 8 / self.zoom if major else 4 / self.zoom
                cx = self._start_world[0] + dist * ux
                cy = self._start_world[1] + dist * uy
                csc = self._world_to_screen(cx, cy)
                s1 = self._world_to_screen(cx + px * length, cy + py * length)
                s2 = self._world_to_screen(cx - px * length, cy - py * length)
                self.canvas.create_line(s1[0], s1[1], s2[0], s2[1], fill=self.fg_color, width=max(1, self.brush_size // 2), tags="shape_preview")
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 12 * self.zoom)
        self.temp_text = self.canvas.create_text(mid[0], mid[1], text=f"{r:.1f}", fill=self.fg_color, anchor=tk.CENTER, tags="shape_preview")

    def _draw_ruler(self, wx: float, wy: float) -> None:
        self._clear_preview()
        self._snapshot()
        dx, dy = wx - self._start_world[0], wy - self._start_world[1]
        r = math.hypot(dx, dy)
        if r < 1 / self.zoom:
            return
        self._append_object({
            "type": "ruler",
            "p1": self._start_world,
            "p2": (wx, wy),
            "color": self.fg_color,
            "width": self.brush_size / self.zoom,
            "label": f"{r:.1f}",
        })
        self.render()

    def _preview_protractor(self, wx: float, wy: float) -> None:
        self._clear_preview()
        cx, cy = self._start_world
        sc = self._world_to_screen(cx, cy)
        r = math.hypot(wx - cx, wy - cy)
        sr = int(r * self.zoom)
        if sr < 2:
            return
        self.temp_shape = self.canvas.create_arc(sc[0] - sr, sc[1] - sr, sc[0] + sr, sc[1] + sr, start=0, extent=-180, style="arc", outline=self.fg_color, width=self.brush_size, tags="shape_preview")
        for a in range(0, 181, 10):
            rad = math.radians(a)
            x1 = sc[0] + (sr - 5) * math.cos(rad)
            y1 = sc[1] - (sr - 5) * math.sin(rad)
            x2 = sc[0] + sr * math.cos(rad)
            y2 = sc[1] - sr * math.sin(rad)
            self.canvas.create_line(x1, y1, x2, y2, fill=self.fg_color, width=max(1, self.brush_size // 2), tags="shape_preview")
        self.canvas.create_line(sc[0], sc[1], sc[0] + sr, sc[1], fill=self.fg_color, width=self.brush_size, tags="shape_preview")
        p2 = self._world_to_screen(wx, wy)
        self.canvas.create_line(sc[0], sc[1], p2[0], p2[1], fill=self.fg_color, width=self.brush_size, tags="shape_preview")
        angle = math.degrees(math.atan2(abs(cy - wy), wx - cx))
        mid = (sc[0] + sr * 0.6 * math.cos(math.radians(angle / 2)), sc[1] - sr * 0.6 * math.sin(math.radians(angle / 2)))
        self.temp_text = self.canvas.create_text(mid[0], mid[1], text=f"{angle:.1f}°", fill=self.fg_color, anchor=tk.CENTER, tags="shape_preview")

    def _draw_protractor(self, wx: float, wy: float) -> None:
        self._clear_preview()
        self._snapshot()
        cx, cy = self._start_world
        r = math.hypot(wx - cx, wy - cy)
        if r < 1 / self.zoom:
            return
        angle = math.degrees(math.atan2(abs(cy - wy), wx - cx))
        self._append_object({
            "type": "protractor",
            "center": self._start_world,
            "p2": (wx, wy),
            "radius": r,
            "angle": angle,
            "color": self.fg_color,
            "width": self.brush_size / self.zoom,
        })
        self.render()

    def _preview_compass(self, wx: float, wy: float) -> None:
        self._clear_preview()
        cx, cy = self._start_world
        sc = self._world_to_screen(cx, cy)
        r = math.hypot(wx - cx, wy - cy)
        sr = int(r * self.zoom)
        if sr < 2:
            return
        self.temp_shape = self.canvas.create_oval(sc[0] - sr, sc[1] - sr, sc[0] + sr, sc[1] + sr, outline=self.fg_color, width=self.brush_size, tags="shape_preview")
        p2 = self._world_to_screen(wx, wy)
        self.canvas.create_line(sc[0], sc[1], p2[0], p2[1], fill=self.fg_color, width=self.brush_size, tags="shape_preview")
        mid = ((sc[0] + p2[0]) / 2, (sc[1] + p2[1]) / 2 - 12 * self.zoom)
        self.temp_text = self.canvas.create_text(mid[0], mid[1], text=f"r={r:.1f}", fill=self.fg_color, anchor=tk.CENTER, tags="shape_preview")

    def _draw_compass(self, wx: float, wy: float) -> None:
        self._clear_preview()
        self._snapshot()
        cx, cy = self._start_world
        r = math.hypot(wx - cx, wy - cy)
        if r < 1 / self.zoom:
            return
        self._append_object({
            "type": "compass",
            "center": self._start_world,
            "p2": (wx, wy),
            "radius": r,
            "color": self.fg_color,
            "width": self.brush_size / self.zoom,
        })
        self.render()

    def _place_text(self, wx: float, wy: float) -> None:
        dlg = TextDialog(self.root)
        if not dlg.text:
            return
        self._snapshot()
        self._append_object({
            "type": "text",
            "pos": (wx, wy),
            "text": dlg.text,
            "size": dlg.size / self.zoom,
            "color": self.fg_color,
            "font_path": dlg.font_path,
        })
        self.render()

    def _erase(self, path: list[tuple[float, float]]) -> None:
        radius = max(self.brush_size * 2, 4) / self.zoom
        keep = []
        for obj in self.objects:
            if not self._layer_visible(obj) or not self._obj_intersects_path(obj, path, radius):
                keep.append(obj)
        self.objects = keep
        self._selected_idx = None

    def _obj_intersects_path(self, obj: dict, path: list[tuple[float, float]], radius: float) -> bool:
        kind = obj.get("type")
        if kind in ("pen", "highlighter"):
            pts = obj["points"]
            for i in range(len(pts) - 1):
                for p in path:
                    if self._point_to_segment(p, pts[i], pts[i + 1]) <= radius:
                        return True
            return False
        if kind in ("line", "arrow", "measure", "ruler"):
            for p in path:
                if self._point_to_segment(p, obj["p1"], obj["p2"]) <= radius:
                    return True
            return False
        if kind == "rect":
            x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
            for p in path:
                if x1 - radius <= p[0] <= x2 + radius and y1 - radius <= p[1] <= y2 + radius:
                    return True
            return False
        if kind == "oval":
            cx = (obj["x1"] + obj["x2"]) / 2
            cy = (obj["y1"] + obj["y2"]) / 2
            rx = abs(obj["x2"] - obj["x1"]) / 2 + radius
            ry = abs(obj["y2"] - obj["y1"]) / 2 + radius
            for p in path:
                if ((p[0] - cx) / rx) ** 2 + ((p[1] - cy) / ry) ** 2 <= 1:
                    return True
            return False
        if kind == "polygon":
            pts = obj["points"]
            for i in range(len(pts)):
                a = pts[i]
                b = pts[(i + 1) % len(pts)]
                for p in path:
                    if self._point_to_segment(p, a, b) <= radius:
                        return True
            return False
        if kind in ("protractor", "compass"):
            cx, cy = obj["center"]
            r = obj["radius"] + radius
            for p in path:
                if math.hypot(p[0] - cx, p[1] - cy) <= r:
                    return True
            return False
        if kind == "text":
            size = obj["size"]
            lines = obj["text"].split("\n")
            w = max(len(line) for line in lines) * size * 0.6 if lines else size
            h = len(lines) * size * 1.3
            x, y = obj["pos"]
            for p in path:
                if x - radius <= p[0] <= x + w + radius and y - radius <= p[1] <= y + h + radius:
                    return True
            return False
        if kind in ("function", "projectile"):
            # Simplified: erase entire if any path point near origin
            origin = obj.get("origin")
            if origin:
                for p in path:
                    if math.hypot(p[0] - origin[0], p[1] - origin[1]) <= radius * 3:
                        return True
            return False
        return False

    def _point_to_segment(self, p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        if l2 == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
        proj = (a[0] + t * dx, a[1] + t * dy)
        return math.hypot(p[0] - proj[0], p[1] - proj[1])

    # ------------------------------------------------------------------ Background
    def _on_grid_size_change(self) -> None:
        try:
            self.grid_size = int(self.grid_size_var.get())
        except ValueError:
            self.grid_size = GRID_SIZE
        self.request_render()

    def set_background(self, kind: str) -> None:
        if kind == self.bg_kind:
            return
        self._snapshot()
        self.bg_kind = kind
        self.render()

    def _on_bg_change(self, _event: tk.Event | None = None) -> None:
        label = self.bg_combo.get()
        kind = {v: k for k, v in BG_LABELS.items()}[label]
        self.set_background(kind)

    # ------------------------------------------------------------------ UI actions
    def new_board(self, _event: tk.Event | None = None) -> None:
        self._snapshot()
        self.objects.clear()
        self._selected_idx = None
        self.bg_kind = "plain"
        self.bg_combo.set(BG_LABELS["plain"])
        self.bg_image = None
        self._center_view()
        self.render()

    def clear(self) -> None:
        self._snapshot()
        self.objects.clear()
        self._selected_idx = None
        self.render()

    def toggle_fullscreen(self, _event: tk.Event | None = None) -> None:
        current = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current)

    def toggle_recording(self) -> None:
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if not HAS_IMAGEIO:
            messagebox.showwarning("Recorder", "imageio is not installed. Recording unavailable.")
            return
        dlg = RecordingDialog(self.root)
        if not dlg.ok:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("Image sequence folder", "")],
        )
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path = path + ".mp4"
        self._rec_w, self._rec_h = dlg.resolution
        self._rec_fps = max(10, min(120, dlg.fps))
        self._rec_quality = max(1, min(10, dlg.quality))
        try:
            self._rec_writer = imageio.get_writer(path, fps=self._rec_fps, codec="libx264", quality=self._rec_quality)
        except Exception as exc:
            messagebox.showerror("Recorder", f"Could not start recording:\n{exc}")
            return
        self._rec_path = path
        self._rec_frame_count = 0
        self._rec_start_time = time.perf_counter()
        self.recording = True
        self.rec_btn.config(image=self.icons.get("stop"), text="STOP")
        self.status_rec.config(text="REC")
        self.status_msg.config(text=f"Recording {self._rec_w}x{self._rec_h}@{self._rec_fps}fps to {path}")

    def _stop_recording(self) -> None:
        self.recording = False
        if self._rec_after_id:
            try:
                self.root.after_cancel(self._rec_after_id)
            except Exception:
                pass
            self._rec_after_id = None
        if self._rec_writer:
            try:
                self._rec_writer.close()
            except Exception:
                pass
            self._rec_writer = None
        duration = time.perf_counter() - (self._rec_start_time or time.perf_counter())
        self.rec_btn.config(image=self.icons.get("record"), text="REC")
        self.status_rec.config(text="")
        self.status_msg.config(text=f"Saved {self._rec_frame_count} frames ({duration:.1f}s)")
        self._rec_path = None

    def _queue_record_frame(self) -> None:
        if not self.recording or not self._rec_writer:
            return
        if self._rec_after_id:
            return
        try:
            img = self._render_current_image_rec().convert("RGB")
            frame = np.array(img) if np is not None else img
            self._rec_writer.append_data(frame)
            self._rec_frame_count += 1
            elapsed = time.perf_counter() - self._rec_start_time
            self.status_msg.config(text=f"REC {self._rec_w}x{self._rec_h} {self._rec_frame_count} frames  {elapsed:.1f}s")
        except Exception as exc:
            self.status_msg.config(text=f"REC error: {exc}")
            self._stop_recording()
            return
        self._rec_after_id = self.root.after(int(1000 / self._rec_fps), self._clear_rec_after)

    def _clear_rec_after(self) -> None:
        self._rec_after_id = None

    # ------------------------------------------------------------------ Math tools
    def plot_function(self) -> None:
        expr = simpledialog.askstring("Graph Function", "Enter y = f(x), e.g. sin(x), x**2 - 5:")
        if not expr:
            return
        try:
            scale = float(simpledialog.askstring("Scale", "Pixels per unit:", initialvalue="30"))
        except (TypeError, ValueError):
            scale = 30.0
        self._snapshot()
        self._add_function(expr, self.fg_color, scale)

    def _add_function(self, expr_str: str, color: str, scale: float) -> None:
        if not HAS_SYMPY:
            messagebox.showwarning("Math", "SymPy is required for plotting.")
            return
        try:
            sp.sympify(expr_str)
        except Exception as exc:
            messagebox.showerror("Plot Error", f"Could not parse expression:\n{exc}")
            return
        origin = (self.pan_x + (self.viewport_w / 2.0) / self.zoom,
                  self.pan_y + (self.viewport_h / 2.0) / self.zoom)
        self._append_object({
            "type": "function",
            "expr": expr_str.replace("^", "**"),
            "origin": origin,
            "scale": scale / self.zoom,
            "color": color,
            "width": self.brush_size / self.zoom,
        })
        self.render()

    def _render_function(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        if not HAS_SYMPY:
            return
        try:
            x = sp.Symbol("x")
            expr = sp.sympify(obj["expr"])
            f = sp.lambdify(x, expr, modules="math")
        except Exception:
            return
        ox, oy = obj["origin"]
        scale = obj["scale"]
        left, top = self._screen_to_world(0, 0)
        right, bottom = self._screen_to_world(self.viewport_w, self.viewport_h)
        x_min = (left - ox) / scale
        x_max = (right - ox) / scale
        step = max(0.01, 1.0 / (scale * self.zoom))
        points = []
        prev = None
        x_val = x_min
        while x_val <= x_max:
            try:
                y_val = float(f(x_val))
                if math.isfinite(y_val):
                    wx = ox + x_val * scale
                    wy = oy - y_val * scale
                    p = self._world_to_screen(wx, wy)
                    if 0 <= p[0] < self.viewport_w and 0 <= p[1] < self.viewport_h:
                        if prev is not None and abs(p[1] - prev[1]) > self.viewport_h / 2:
                            if len(points) > 1:
                                draw.line(points, fill=obj["color"], width=max(1, int(obj["width"] * self.zoom)))
                            points = []
                        else:
                            points.append(p)
                        prev = p
                    else:
                        if len(points) > 1:
                            draw.line(points, fill=obj["color"], width=max(1, int(obj["width"] * self.zoom)))
                        points = []
                        prev = None
                else:
                    if len(points) > 1:
                        draw.line(points, fill=obj["color"], width=max(1, int(obj["width"] * self.zoom)))
                    points = []
                    prev = None
            except Exception:
                if len(points) > 1:
                    draw.line(points, fill=obj["color"], width=max(1, int(obj["width"] * self.zoom)))
                points = []
                prev = None
            x_val += step
        if len(points) > 1:
            draw.line(points, fill=obj["color"], width=max(1, int(obj["width"] * self.zoom)))

    def math_assistant(self) -> None:
        if not HAS_SYMPY:
            messagebox.showwarning("Math Assistant", "SymPy is not installed.")
            return
        dlg = MathDialog(self.root)
        if not dlg.ok:
            return
        expr_input = dlg.expr.strip().replace("^", "**")
        if not expr_input:
            return
        x = sp.Symbol("x")
        try:
            if dlg.operation == "Solve":
                if "=" in expr_input:
                    lhs, rhs = expr_input.split("=", 1)
                    eq = sp.Eq(sp.sympify(lhs), sp.sympify(rhs))
                    result = sp.solve(eq, x)
                else:
                    result = sp.solve(sp.sympify(expr_input), x)
                result_text = f"Solutions for {dlg.expr}:\n{result}"
            else:
                expr = sp.sympify(expr_input)
                if dlg.operation == "Derivative":
                    res = sp.diff(expr, x)
                    result_text = f"f(x) = {sp.pretty(expr)}\n\nf'(x) = {sp.pretty(res)}"
                    if dlg.plot:
                        self._snapshot()
                        self._add_function(expr_input, "#9e9e9e", dlg.scale)
                        self._add_function(str(res), self.fg_color, dlg.scale)
                elif dlg.operation == "Integral":
                    res = sp.integrate(expr, x)
                    result_text = f"f(x) = {sp.pretty(expr)}\n\n∫ f(x) dx = {sp.pretty(res)} + C"
                    if dlg.plot:
                        self._snapshot()
                        self._add_function(expr_input, "#9e9e9e", dlg.scale)
                        self._add_function(str(res), self.fg_color, dlg.scale)
                elif dlg.operation == "Simplify":
                    res = sp.simplify(expr)
                    result_text = f"Simplified:\n{sp.pretty(res)}"
                elif dlg.operation == "Table of variations":
                    res = self._variation_table(expr, x)
                    result_text = f"Function: {sp.pretty(expr)}\n\n{res}"
                else:  # Plot
                    result_text = f"f(x) = {sp.pretty(expr)}"
                    if dlg.plot:
                        self._snapshot()
                        self._add_function(expr_input, self.fg_color, dlg.scale)
        except Exception as exc:
            messagebox.showerror("Math Error", f"Could not process expression:\n{exc}")
            return
        messagebox.showinfo("Math Assistant", result_text)

    def _variation_table(self, expr, x) -> str:
        d = sp.diff(expr, x)
        crit = sp.solve(d, x)
        real_crit = []
        for c in crit:
            try:
                if c.is_real:
                    real_crit.append(c)
            except Exception:
                pass
        real_crit = sorted(set(real_crit))
        bounds = []
        if not real_crit:
            bounds.append((-sp.oo, sp.oo))
        else:
            bounds.append((-sp.oo, real_crit[0]))
            for i in range(len(real_crit) - 1):
                bounds.append((real_crit[i], real_crit[i + 1]))
            bounds.append((real_crit[-1], sp.oo))
        lines = []
        for a, b in bounds:
            if a == -sp.oo and b == sp.oo:
                test = 0
            elif a == -sp.oo:
                test = float(b) - 1
            elif b == sp.oo:
                test = float(a) + 1
            else:
                test = (float(a) + float(b)) / 2
            sign_val = d.subs(x, test)
            try:
                sign = float(sp.sign(sign_val))
            except Exception:
                sign = 0.0
            if sign > 0:
                lines.append(f"  ({sp.pretty(a)}, {sp.pretty(b)}): f'(x) > 0  → increasing")
            elif sign < 0:
                lines.append(f"  ({sp.pretty(a)}, {sp.pretty(b)}): f'(x) < 0  → decreasing")
            else:
                lines.append(f"  ({sp.pretty(a)}, {sp.pretty(b)}): f'(x) = 0  → stationary")
        if real_crit:
            lines.append("Critical points:")
            for c in real_crit:
                val = expr.subs(x, c)
                lines.append(f"  x = {sp.pretty(c)}, f(x) = {sp.pretty(val)}")
        return "\n".join(lines)

    def projectile_sim(self) -> None:
        dlg = PhysicsDialog(self.root)
        if not dlg.ok:
            return
        v0 = max(0.0, dlg.v0)
        angle = max(0.0, min(90.0, dlg.angle))
        h0 = dlg.h0
        g = max(0.1, dlg.g)
        if angle <= 0 or angle >= 90:
            messagebox.showwarning("Projectile", "Launch angle must be between 0° and 90°.")
            return
        theta = math.radians(angle)
        vx = v0 * math.cos(theta)
        vy = v0 * math.sin(theta)
        t_peak = vy / g
        h_max = h0 + vy * t_peak - 0.5 * g * t_peak * t_peak
        t_flight = (vy + math.sqrt(vy * vy + 2 * g * max(0, h0))) / g
        r = vx * t_flight

        scale = dlg.scale / self.zoom
        origin = (self.pan_x + 80 / self.zoom, self.pan_y + (self.viewport_h - 80) / self.zoom)

        self._snapshot()
        self._append_object({
            "type": "projectile",
            "v0": v0,
            "angle": angle,
            "h0": h0,
            "g": g,
            "origin": origin,
            "scale": scale,
            "range": r,
            "max_height": h_max,
            "flight_time": t_flight,
            "color": self.fg_color,
            "width": self.brush_size / self.zoom,
        })
        result = (
            f"Projectile Motion\n"
            f"v0 = {v0} m/s, angle = {angle}°, g = {g} m/s²\n"
            f"Range = {r:.2f} m,  Max height = {h_max:.2f} m,  Flight time = {t_flight:.2f} s"
        )
        self._append_object({
            "type": "text",
            "pos": (origin[0] + 10 / self.zoom, origin[1] - h_max * scale - 80 / self.zoom),
            "text": result,
            "size": 16 / self.zoom,
            "color": self.fg_color,
            "font_path": FONT_CANDIDATES[0],
        })
        self.render()

    def _render_projectile(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        v0 = obj["v0"]
        angle = math.radians(obj["angle"])
        h0 = obj["h0"]
        g = obj["g"]
        scale = obj["scale"]
        ox, oy = obj["origin"]
        vx = v0 * math.cos(angle)
        vy = v0 * math.sin(angle)
        t_flight = obj["flight_time"]
        steps = 200
        pts = []
        for i in range(steps + 1):
            t = t_flight * i / steps
            x = vx * t
            y = h0 + vy * t - 0.5 * g * t * t
            pts.append(self._world_to_screen(ox + x * scale, oy - y * scale))
        width = max(1, int(obj["width"] * self.zoom))
        draw.line(pts, fill=obj["color"], width=width)
        # axes
        r = obj["range"] * scale
        h = obj["max_height"] * scale
        so = self._world_to_screen(ox, oy)
        draw.line([so, self._world_to_screen(ox + r + 20 / self.zoom, oy)], fill="#888888", width=max(1, width // 2))
        draw.line([so, self._world_to_screen(ox, oy - h - 20 / self.zoom)], fill="#888888", width=max(1, width // 2))
        # markers
        sr = max(1, int(3 * self.zoom))
        draw.ellipse([so[0] - sr, so[1] - sr, so[0] + sr, so[1] + sr], fill=obj["color"])
        peak_t = vy / g
        peak_x = ox + vx * peak_t * scale
        peak_y = oy - obj["max_height"] * scale
        sp = self._world_to_screen(peak_x, peak_y)
        draw.ellipse([sp[0] - sr, sp[1] - sr, sp[0] + sr, sp[1] + sr], fill=obj["color"])
        land = self._world_to_screen(ox + r, oy)
        draw.ellipse([land[0] - sr, land[1] - sr, land[0] + sr, land[1] + sr], fill=obj["color"])

    def _render_dna(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        p1 = self._world_to_screen(obj["x1"], obj["y1"])
        p2 = self._world_to_screen(obj["x2"], obj["y2"])
        width = max(1, int(obj["width"] * self.zoom))
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dist = math.hypot(dx, dy)
        if dist < 1:
            return
        ux, uy = dx / dist, dy / dist
        turns = obj.get("turns", 4)
        amp = max(3, int(obj.get("amp", 16) * self.zoom))
        n = min(int(dist), 400)
        pts1, pts2 = [], []
        for i in range(n + 1):
            t = i / dist if dist else 0
            cx = p1[0] + t * dx
            cy = p1[1] + t * dy
            ang = 2 * math.pi * turns * t
            offset = amp * math.sin(ang)
            pts1.append((cx - uy * offset, cy + ux * offset))
            pts2.append((cx + uy * offset, cy - ux * offset))
            if i % 12 == 0 and i > 0 and i < n:
                draw.line([pts1[-1], pts2[-1]], fill="#888888", width=max(1, width // 2))
        color = obj["color"]
        draw.line(pts1, fill=color, width=width)
        draw.line(pts2, fill=color, width=width)

    def _render_lens(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
        p1 = self._world_to_screen(x1, y1)
        p2 = self._world_to_screen(x2, y2)
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        h = (p2[1] - p1[1]) / 2
        # principal axis
        draw.line([(p1[0], mid_y), (p2[0], mid_y)], fill="#888888", width=max(1, width // 2))
        # lens symbol (double-headed vertical arrow)
        draw.line([(mid_x, p1[1]), (mid_x, p2[1])], fill=color, width=width)
        draw.polygon([(mid_x - 5, p1[1] + 8), (mid_x, p1[1]), (mid_x + 5, p1[1] + 8)], fill=color)
        draw.polygon([(mid_x - 5, p2[1] - 8), (mid_x, p2[1]), (mid_x + 5, p2[1] - 8)], fill=color)
        # focal points
        f = obj.get("f", (x2 - x1) / 6)
        f_px = f * self.zoom
        if abs(f_px) > 2:
            for sign in (-1, 1):
                fx = mid_x + sign * f_px
                draw.ellipse([fx - 3, mid_y - 3, fx + 3, mid_y + 3], outline=color, width=width)
            font = self._get_font(max(8, int(12 * self.zoom)))
            draw.text((mid_x - f_px - 6, mid_y - 16), "F", fill=color, font=font)
            draw.text((mid_x + f_px - 8, mid_y - 16), "F'", fill=color, font=font)

    def _render_rc_circuit(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
        left = self._world_to_screen(x1, (y1 + y2) / 2)
        right = self._world_to_screen(x2, (y1 + y2) / 2)
        top = self._world_to_screen((x1 + x2) / 2, y1)
        bottom = self._world_to_screen((x1 + x2) / 2, y2)
        cy = (left[1] + right[1]) / 2
        total_w = right[0] - left[0]
        seg = total_w / 4
        # top wire
        draw.line([(left[0], top[1]), (right[0], top[1])], fill=color, width=width)
        # bottom wire
        draw.line([(left[0], bottom[1]), (right[0], bottom[1])], fill=color, width=width)
        # battery
        bx = left[0] + seg
        draw.line([(bx, top[1]), (bx, top[1] + (bottom[1] - top[1]) * 0.25)], fill=color, width=width)
        draw.line([(bx, top[1] + (bottom[1] - top[1]) * 0.75), (bx, bottom[1])], fill=color, width=width)
        draw.line([(bx - 6, top[1] + (bottom[1] - top[1]) * 0.25), (bx + 6, top[1] + (bottom[1] - top[1]) * 0.25)], fill=color, width=width)
        draw.line([(bx - 10, top[1] + (bottom[1] - top[1]) * 0.75), (bx + 10, top[1] + (bottom[1] - top[1]) * 0.75)], fill=color, width=width)
        # resistor zigzag
        rx = left[0] + 2 * seg
        zig = []
        mid_y = (top[1] + bottom[1]) / 2
        for i in range(8):
            zy = top[1] + (bottom[1] - top[1]) * (0.15 + 0.7 * ((i % 2) / 7))
            zig.append((rx - seg * 0.35 + i * (seg * 0.7 / 7), zy))
        for i in range(len(zig) - 1):
            draw.line([zig[i], zig[i + 1]], fill=color, width=width)
        # capacitor
        cx = left[0] + 3 * seg
        draw.line([(cx - 1, top[1] + (bottom[1] - top[1]) * 0.25), (cx - 1, top[1] + (bottom[1] - top[1]) * 0.75)], fill=color, width=max(2, width))
        draw.line([(cx + 1, top[1] + (bottom[1] - top[1]) * 0.25), (cx + 1, top[1] + (bottom[1] - top[1]) * 0.75)], fill=color, width=max(2, width))
        # closing wires
        draw.line([(bx, top[1]), (rx, top[1])], fill=color, width=width)
        draw.line([(rx, top[1]), (cx, top[1])], fill=color, width=width)
        draw.line([(cx, top[1]), (right[0], top[1])], fill=color, width=width)
        draw.line([(bx, bottom[1]), (right[0], bottom[1])], fill=color, width=width)
        font = self._get_font(max(8, int(12 * self.zoom)))
        draw.text((rx - 8, bottom[1] - 14), "R", fill=color, font=font)
        draw.text((cx + 4, bottom[1] - 14), "C", fill=color, font=font)
        draw.text((bx - 16, top[1] - 16), "V", fill=color, font=font)

    def _render_wire3d(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        cx, cy = self._world_to_screen(*obj["center"])
        s = obj["size"] * self.zoom

        def project(x, y, z):
            return cx - x * 0.7 + y * 0.7, cy - x * 0.35 - y * 0.35 + z

        shape = obj.get("shape", "cube")
        if shape == "cube":
            v = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                 (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
            edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                     (0, 4), (1, 5), (2, 6), (3, 7)]
        elif shape == "pyramid":
            v = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (0, 0, 1)]
            edges = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)]
        elif shape == "sphere":
            # wireframe sphere (latitude/longitude)
            pts = []
            for lat in range(-90, 91, 30):
                ring = []
                for lon in range(0, 361, 20):
                    r = math.cos(math.radians(lat))
                    x = r * math.cos(math.radians(lon))
                    z = math.sin(math.radians(lat))
                    y = r * math.sin(math.radians(lon))
                    ring.append(project(x * s, y * s, z * s))
                for i in range(len(ring) - 1):
                    draw.line([ring[i], ring[i + 1]], fill=color, width=width)
            for lon in range(0, 180, 30):
                ring = []
                for lat in range(-90, 91, 10):
                    r = math.cos(math.radians(lat))
                    x = r * math.cos(math.radians(lon))
                    z = math.sin(math.radians(lat))
                    y = r * math.sin(math.radians(lon))
                    ring.append(project(x * s, y * s, z * s))
                for i in range(len(ring) - 1):
                    draw.line([ring[i], ring[i + 1]], fill=color, width=width)
            return
        else:
            v, edges = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        pts = [(project(x * s, y * s, z * s)) for (x, y, z) in v]
        for a, b in edges:
            draw.line([pts[a], pts[b]], fill=color, width=width)

    def _render_wave(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        p1 = self._world_to_screen(obj["x1"], obj["y1"])
        p2 = self._world_to_screen(obj["x2"], obj["y2"])
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dist = math.hypot(dx, dy)
        if dist < 2:
            return
        ux, uy = dx / dist, dy / dist
        px, py = -uy, ux
        amp = max(2, int(obj.get("amplitude", 20) * self.zoom))
        freq = obj.get("frequency", 3.0)
        pts = []
        n = min(int(dist), 400)
        for i in range(n + 1):
            t = i / n
            base = (p1[0] + t * dx, p1[1] + t * dy)
            wave = amp * math.sin(2 * math.pi * freq * t)
            pts.append((base[0] + px * wave, base[1] + py * wave))
        draw.line(pts, fill=color, width=width)
        # axis
        draw.line([p1, p2], fill="#888888", width=max(1, width // 2))

    def _render_vector(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        tail = self._world_to_screen(*obj["tail"])
        head = self._world_to_screen(*obj["head"])
        draw.line([tail, head], fill=color, width=width)
        dx = head[0] - tail[0]
        dy = head[1] - tail[1]
        dist = math.hypot(dx, dy)
        if dist > 6:
            ux, uy = dx / dist, dy / dist
            px, py = -uy, ux
            hl = min(18, dist * 0.35)
            hw = hl * 0.5
            p_back = (head[0] - ux * hl, head[1] - uy * hl)
            p_left = (p_back[0] + px * hw, p_back[1] + py * hw)
            p_right = (p_back[0] - px * hw, p_back[1] - py * hw)
            draw.polygon([head, p_left, p_right], fill=color, outline=color)
        font = self._get_font(max(8, int(12 * self.zoom)))
        label = obj.get("label", "")
        if label:
            mid = ((tail[0] + head[0]) / 2, (tail[1] + head[1]) / 2 - 14)
            draw.text(mid, label, fill=color, font=font, anchor="mm")

    def _render_molecule(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        cx, cy = self._world_to_screen(*obj["center"])
        s = obj["size"] * self.zoom
        name = obj.get("name", "water")
        font = self._get_font(max(8, int(12 * self.zoom)))

        if name == "water":
            atoms = [(0, -0.8, "O", "#e53935"), (-0.9, 0.6, "H", "#1e88e5"), (0.9, 0.6, "H", "#1e88e5")]
            bonds = [(0, 1), (0, 2)]
        elif name == "methane":
            atoms = [(0, 0, "C", "#333333"), (-0.9, -0.6, "H", "#1e88e5"), (0.9, -0.6, "H", "#1e88e5"), (0, 1.0, "H", "#1e88e5"), (0, -1.0, "H", "#1e88e5")]
            bonds = [(0, 1), (0, 2), (0, 3), (0, 4)]
        elif name == "co2":
            atoms = [(-1.0, 0, "O", "#e53935"), (0, 0, "C", "#333333"), (1.0, 0, "O", "#e53935")]
            bonds = [(0, 1), (1, 2)]
        else:  # benzene ring
            n = 6
            atoms = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), "C", "#333333") for i in range(n)]
            bonds = [(i, (i + 1) % n) for i in range(n)] + [(0, 3), (1, 4), (2, 5)]

        for a, b in bonds:
            x1 = cx + atoms[a][0] * s
            y1 = cy + atoms[a][1] * s
            x2 = cx + atoms[b][0] * s
            y2 = cy + atoms[b][1] * s
            draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

        for x, y, symbol, ac in atoms:
            ax = cx + x * s
            ay = cy + y * s
            r = max(4, int(s * 0.18))
            draw.ellipse([ax - r, ay - r, ax + r, ay + r], fill=ac, outline=color, width=width)
            draw.text((ax, ay), symbol, fill="white" if ac != "#ffffff" else color, font=font, anchor="mm")

    def _render_atom(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        cx, cy = self._world_to_screen(*obj["center"])
        s = obj["size"] * self.zoom
        z = obj.get("protons", 1)
        n_orbits = min(max(1, z // 2 + 1), 5)
        font = self._get_font(max(8, int(12 * self.zoom)))
        # nucleus
        nr = max(6, int(s * 0.12))
        draw.ellipse([cx - nr, cy - nr, cx + nr, cy + nr], fill="#e53935", outline=color, width=width)
        draw.text((cx, cy), f"Z={z}", fill="white", font=font, anchor="mm")
        # orbits
        for i in range(1, n_orbits + 1):
            r = (s * i) / (n_orbits + 1)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(1, width // 2))
            # electron
            ang = 2 * math.pi * i / n_orbits
            ex = cx + r * math.cos(ang)
            ey = cy + r * math.sin(ang)
            er = max(2, int(s * 0.04))
            draw.ellipse([ex - er, ey - er, ex + er, ey + er], fill="#1e88e5", outline=color, width=width)

    def _render_pulley(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
        left = self._world_to_screen(x1, (y1 + y2) / 2)
        right = self._world_to_screen(x2, (y1 + y2) / 2)
        top = self._world_to_screen((x1 + x2) / 2, y1)
        bottom = self._world_to_screen((x1 + x2) / 2, y2)
        cx = (left[0] + right[0]) / 2
        cy = top[1] + (bottom[1] - top[1]) * 0.25
        pr = (bottom[1] - top[1]) * 0.15
        # wheel
        draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], outline=color, width=width)
        draw.ellipse([cx - pr * 0.15, cy - pr * 0.15, cx + pr * 0.15, cy + pr * 0.15], fill=color)
        # ropes
        draw.line([(cx - pr, cy), (left[0], bottom[1])], fill=color, width=width)
        draw.line([(cx + pr, cy), (right[0], bottom[1])], fill=color, width=width)
        # masses
        mw = (right[0] - left[0]) * 0.12
        for bx, label, m in [(left[0], "m1", obj.get("m1", 2)), (right[0], "m2", obj.get("m2", 3))]:
            draw.rectangle([bx - mw / 2, bottom[1] - mw, bx + mw / 2, bottom[1]], outline=color, fill="#1e88e5", width=width)
            font = self._get_font(max(8, int(12 * self.zoom)))
            draw.text((bx, bottom[1] - mw / 2), f"{label}={m}kg", fill=color, font=font, anchor="mm")

    def _render_incline(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
        p1 = self._world_to_screen(x1, y2)
        p2 = self._world_to_screen(x2, y2)
        p3 = self._world_to_screen(x2, y1)
        # slope triangle
        draw.polygon([p1, p2, p3], outline=color, fill=self._hex(self._parse_fill("#eeeeee")[:3]) if self.theme == "light" else self._hex(self._parse_fill("#333333")[:3]), width=width)
        # block
        ang = math.radians(obj.get("angle", 30))
        side = (p3[0] - p2[0]) * 0.15
        bx = (p2[0] + p3[0]) / 2
        by = (p2[1] + p3[1]) / 2 - side / 2
        # simple square rotated
        bpts = []
        for a in [0, math.pi / 2, math.pi, 3 * math.pi / 2]:
            bpts.append((bx + side * math.cos(a + ang), by + side * math.sin(a + ang)))
        draw.polygon(bpts, outline=color, fill="#1e88e5", width=width)
        # angle arc
        arc_r = (p2[0] - p1[0]) * 0.12
        draw.arc([p2[0] - arc_r, p2[1] - arc_r, p2[0] + arc_r, p2[1] + arc_r], start=0, end=int(math.degrees(ang)), fill=color, width=width)
        # label
        font = self._get_font(max(8, int(12 * self.zoom)))
        draw.text((p2[0] + arc_r * 0.6, p2[1] - arc_r * 0.6), f"θ={int(math.degrees(ang))}°", fill=color, font=font)

    def _render_axes(self, draw: ImageDraw.ImageDraw, obj: dict) -> None:
        color = obj["color"]
        width = max(1, int(obj["width"] * self.zoom))
        x1, y1, x2, y2 = obj["x1"], obj["y1"], obj["x2"], obj["y2"]
        p1 = self._world_to_screen(x1, y1)
        p2 = self._world_to_screen(x2, y2)
        mid_y = (p1[1] + p2[1]) / 2
        mid_x = (p1[0] + p2[0]) / 2
        # x-axis
        draw.line([(p1[0], mid_y), (p2[0] - 8, mid_y)], fill=color, width=width)
        draw.polygon([(p2[0], mid_y), (p2[0] - 8, mid_y - 4), (p2[0] - 8, mid_y + 4)], fill=color)
        # y-axis
        draw.line([(mid_x, p2[1]), (mid_x, p1[1] + 8)], fill=color, width=width)
        draw.polygon([(mid_x, p1[1]), (mid_x - 4, p1[1] + 8), (mid_x + 4, p1[1] + 8)], fill=color)
        font = self._get_font(max(8, int(12 * self.zoom)))
        draw.text((p2[0] - 10, mid_y - 16), "x", fill=color, font=font)
        draw.text((mid_x - 16, p1[1] + 2), "y", fill=color, font=font)
        # ticks
        tick = (x2 - x1) / 10
        for i in range(-5, 6):
            if i == 0:
                continue
            tx = mid_x + i * tick * self.zoom
            draw.line([(tx, mid_y - 3), (tx, mid_y + 3)], fill=color, width=max(1, width // 2))
            ty = mid_y + i * tick * self.zoom
            draw.line([(mid_x - 3, ty), (mid_x + 3, ty)], fill=color, width=max(1, width // 2))

    def _get_viewport_center_world(self) -> tuple[float, float]:
        return (self.pan_x + self.viewport_w / (2 * self.zoom), self.pan_y + self.viewport_h / (2 * self.zoom))

    def insert_dna(self) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        size = 200 / self.zoom
        self._append_object({
            "type": "dna",
            "x1": cx - size / 2,
            "y1": cy - size / 6,
            "x2": cx + size / 2,
            "y2": cy + size / 6,
            "turns": 4,
            "amp": 18 / self.zoom,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_lens(self) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        w = 260 / self.zoom
        h = 120 / self.zoom
        f = simpledialog.askfloat("Thin Lens", "Enter focal length (positive for converging, negative for diverging):", initialvalue=60.0)
        if f is None:
            return
        self._append_object({
            "type": "lens",
            "x1": cx - w / 2,
            "y1": cy - h / 2,
            "x2": cx + w / 2,
            "y2": cy + h / 2,
            "f": f / self.zoom,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_rc_circuit(self) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        w = 280 / self.zoom
        h = 120 / self.zoom
        self._append_object({
            "type": "rc",
            "x1": cx - w / 2,
            "y1": cy - h / 2,
            "x2": cx + w / 2,
            "y2": cy + h / 2,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_3d_shape(self) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        shape = simpledialog.askstring("3D Wireframe", "Choose shape: cube, pyramid, sphere", initialvalue="cube")
        if shape is None:
            return
        shape = shape.strip().lower()
        if shape not in ("cube", "pyramid", "sphere"):
            shape = "cube"
        self._append_object({
            "type": "wire3d",
            "center": (cx, cy),
            "size": 90 / self.zoom,
            "shape": shape,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_wave(self) -> None:
        self._snapshot()
        freq = simpledialog.askfloat("Wave", "Frequency (cycles per wave length):", initialvalue=3.0)
        if freq is None:
            return
        amp = simpledialog.askfloat("Wave", "Amplitude (pixels):", initialvalue=20.0)
        if amp is None:
            return
        cx, cy = self._get_viewport_center_world()
        w = 240 / self.zoom
        self._append_object({
            "type": "wave",
            "x1": cx - w / 2,
            "y1": cy,
            "x2": cx + w / 2,
            "y2": cy,
            "amplitude": amp / self.zoom,
            "frequency": freq,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_vector(self) -> None:
        self._snapshot()
        mag = simpledialog.askfloat("Vector", "Magnitude:", initialvalue=120.0)
        if mag is None:
            return
        angle = simpledialog.askfloat("Vector", "Angle (degrees, 0 = right, 90 = up):", initialvalue=45.0)
        if angle is None:
            return
        label = simpledialog.askstring("Vector", "Label (e.g. F, v, a):", initialvalue="F")
        cx, cy = self._get_viewport_center_world()
        rad = math.radians(-angle)
        head = (cx + (mag / self.zoom) * math.cos(rad), cy + (mag / self.zoom) * math.sin(rad))
        self._append_object({
            "type": "vector",
            "tail": (cx, cy),
            "head": head,
            "label": label or "",
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_molecule(self) -> None:
        self._snapshot()
        options = ["water (H₂O)", "methane (CH₄)", "co2 (CO₂)", "benzene (C₆H₆)"]
        name = simpledialog.askstring("Molecule", f"Choose one of {', '.join(options)}:", initialvalue="water")
        if name is None:
            return
        name = name.split()[0].lower()
        if name not in ("water", "methane", "co2", "benzene"):
            name = "water"
        cx, cy = self._get_viewport_center_world()
        self._append_object({
            "type": "molecule",
            "center": (cx, cy),
            "size": 90 / self.zoom,
            "name": name,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_atom(self) -> None:
        self._snapshot()
        z = simpledialog.askinteger("Atom", "Number of protons (Z):", initialvalue=8)
        if z is None:
            return
        cx, cy = self._get_viewport_center_world()
        self._append_object({
            "type": "atom",
            "center": (cx, cy),
            "size": 110 / self.zoom,
            "protons": max(1, z),
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_pulley(self) -> None:
        self._snapshot()
        m1 = simpledialog.askfloat("Atwood Machine", "Mass m1 (kg):", initialvalue=2.0)
        if m1 is None:
            return
        m2 = simpledialog.askfloat("Atwood Machine", "Mass m2 (kg):", initialvalue=3.0)
        if m2 is None:
            return
        cx, cy = self._get_viewport_center_world()
        w = 220 / self.zoom
        h = 160 / self.zoom
        self._append_object({
            "type": "pulley",
            "x1": cx - w / 2,
            "y1": cy - h / 2,
            "x2": cx + w / 2,
            "y2": cy + h / 2,
            "m1": m1,
            "m2": m2,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_incline(self) -> None:
        self._snapshot()
        angle = simpledialog.askfloat("Inclined Plane", "Angle (degrees):", initialvalue=30.0)
        if angle is None:
            return
        cx, cy = self._get_viewport_center_world()
        w = 240 / self.zoom
        h = 140 / self.zoom
        self._append_object({
            "type": "incline",
            "x1": cx - w / 2,
            "y1": cy - h / 2,
            "x2": cx + w / 2,
            "y2": cy + h / 2,
            "angle": max(5, min(80, angle)),
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def insert_axes(self) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        w = 260 / self.zoom
        h = 180 / self.zoom
        self._append_object({
            "type": "axes",
            "x1": cx - w / 2,
            "y1": cy - h / 2,
            "x2": cx + w / 2,
            "y2": cy + h / 2,
            "color": self.fg_color,
            "width": self.brush_size,
        })
        self.render()

    def ai_copilot(self) -> None:
        AICopilotDialog(self.root, self)

    def open_periodic_table(self) -> None:
        PeriodicTableDialog(self.root, self)

    def insert_element_info(self, symbol: str, name: str, number: int) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        self._append_object({
            "type": "text",
            "pos": (cx, cy),
            "text": f"{symbol}\n{name}\nZ = {number}",
            "size": 20 / self.zoom,
            "color": self.fg_color,
            "font_path": FONT_CANDIDATES[0],
        })
        self.render()

    def open_chemistry_library(self) -> None:
        ChemistryLibraryDialog(self.root, self)

    def insert_chem_equation(self, text: str) -> None:
        self._snapshot()
        cx, cy = self._get_viewport_center_world()
        self._append_object({
            "type": "text",
            "pos": (cx - 120 / self.zoom, cy),
            "text": text,
            "size": 18 / self.zoom,
            "color": self.fg_color,
            "font_path": FONT_CANDIDATES[0],
        })
        self.status_msg.config(text="Chemical equation inserted")
        self.render()

    def generate_exercise(self) -> None:
        if not HAS_SYMPY:
            messagebox.showwarning("Exercise Generator", "SymPy is required.")
            return
        dlg = ExerciseDialog(self.root)
        if not dlg.ok:
            return
        if not dlg.generated:
            return
        self._snapshot()
        self._append_object({
            "type": "text",
            "pos": (self.pan_x + 30 / self.zoom, self.pan_y + 30 / self.zoom),
            "text": dlg.generated,
            "size": 16 / self.zoom,
            "color": self.fg_color,
            "font_path": FONT_CANDIDATES[0],
        })
        self.render()

    # ------------------------------------------------------------------ Worksheet maker
    def open_worksheet_generator(self) -> None:
        dlg = WorksheetDialog(self.root)
        if not dlg.ok:
            return
        if dlg.action == "insert":
            self._insert_worksheet(dlg.meta, dlg.questions)
        elif dlg.action == "pdf":
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                title="Export Worksheet PDF",
            )
            if not path:
                return
            try:
                self._write_worksheet_pdf(path, dlg.meta, dlg.questions)
            except Exception as exc:
                messagebox.showerror("Worksheet Maker", f"Could not export PDF:\n{exc}")
                return
            messagebox.showinfo("Worksheet Maker", f"Worksheet exported to:\n{path}")

    def _insert_worksheet(self, meta: dict, questions: list[tuple[str, str, str]]) -> None:
        self._snapshot()
        L = WORKSHEET_LANGS[meta["lang"]]
        x = self.pan_x + 40 / self.zoom
        y = self.pan_y + 30 / self.zoom

        def add_text(text: str, size: float) -> None:
            nonlocal y
            self._append_object({
                "type": "text", "pos": (x, y), "text": text,
                "size": size / self.zoom, "color": self.fg_color,
                "font_path": FONT_CANDIDATES[0],
            })
            y += (text.count("\n") + 2.4) * size / self.zoom

        header_bits = [meta["title"].upper()]
        for key in ("school", "teacher"):
            if meta.get(key):
                header_bits.append(f"{L[key]} {meta[key]}")
        bits = [f"{L['class']}: {meta['klass']}"] if meta.get("klass") else []
        if meta.get("date"):
            bits.append(f"{L['date']} {meta['date']}")
        add_text("\n".join(header_bits), 20)
        if bits:
            add_text("   |   ".join(bits), 13)
        step = max(1, round(len(questions) / 3))
        for i, (_topic, q, _a) in enumerate(questions, 1):
            add_text(f"{i}. {q}\n{'.' * 46}", 15)
        key_lines = [f"{i}. {a.replace(chr(10), ' | ')}" for i, (_t, _q, a) in enumerate(questions, 1)]
        add_text(f"—— {L['answer_key']} ——\n" + "\n".join(key_lines), 12)
        self.status_msg.config(text=f"Worksheet inserted ({len(questions)} questions)")
        self.render()

    def _worksheet_pdf_fonts(self) -> tuple[str, str]:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        for reg_name, bold_name in [("segoeui.ttf", "segoeuib.ttf"), ("arial.ttf", "arialbd.ttf")]:
            regular = os.path.join(windir, "Fonts", reg_name)
            bold = os.path.join(windir, "Fonts", bold_name)
            if os.path.exists(regular):
                try:
                    _rl_metrics.registerFont(_RLTTFont("WSBody", regular))
                    if os.path.exists(bold):
                        _rl_metrics.registerFont(_RLTTFont("WSBold", bold))
                        return "WSBody", "WSBold"
                    return "WSBody", "WSBody"
                except Exception:
                    continue
        return "Helvetica", "Helvetica-Bold"

    def _write_worksheet_pdf(self, path: str, meta: dict, questions: list[tuple[str, str, str]]) -> None:
        if not HAS_REPORTLAB:
            raise RuntimeError("reportlab is required (pip install reportlab).")
        c = _rl_canvas.Canvas(path, pagesize=A4)
        W, H = A4
        m = 54
        body_f, bold_f = self._worksheet_pdf_fonts()
        L = WORKSHEET_LANGS[meta["lang"]]

        def put(y: float, text: str, size: float = 11, font: str | None = None,
                align: str = "auto", color=None) -> float:
            font = font or body_f
            for seg in text.split("\n"):
                arabic = _has_arabic(seg)
                if arabic:
                    seg = _shape_bidi_text(seg)
                c.setFont(font, size)
                if color:
                    c.setFillColorRGB(*color)
                if align == "center":
                    c.drawCentredString(W / 2, y, seg)
                elif align == "right" or (align == "auto" and arabic):
                    c.drawRightString(W - m, y, seg)
                else:
                    c.drawString(m, y, seg)
                c.setFillColorRGB(0, 0, 0)
                y -= size * 1.5
            return y

        def footer() -> None:
            c.setFont(body_f, 9)
            c.drawCentredString(W / 2, m * 0.5, f"{L['page']} {c.getPageNumber()}")
            if meta.get("seed"):
                c.setFont(body_f, 7)
                c.drawString(m, m * 0.5, f"ws#{meta['seed']}")

        def new_page() -> float:
            footer()
            c.showPage()
            return H - m

        y = H - m
        y = put(y, meta["title"], 18, bold_f, "center")
        bits = [b for b in (
            f"{L['school']} {meta.get('school','')}".strip() if meta.get("school") else "",
            f"{L['teacher']} {meta.get('teacher','')}".strip() if meta.get("teacher") else "",
            f"{L['class']} {meta.get('klass','')}".strip() if meta.get("klass") else "",
            f"{L['date']} {meta.get('date','')}".strip() if meta.get("date") else "",
        ) if b]
        if bits:
            y = put(y, "   |   ".join(bits), 10, align="center")
        y = put(y, f"{L['name_field']} {'.' * 60}   {L['class']} {'.' * 18}", 11)
        y -= 6
        c.setLineWidth(1.2)
        c.line(m, y, W - m, y)
        y -= 26

        for i, (_topic, q, _a) in enumerate(questions, 1):
            n_lines = q.count("\n") + 1
            needed = n_lines * 17 + 64
            if y - needed < m + 34:
                y = new_page()
            y = put(y, f"{i}.", 12, bold_f) if False else y
            c.setFont(bold_f, 12)
            first_line, rest = (q.split("\n", 1) + [""])[:2]
            arabic = _has_arabic(first_line)
            if arabic:
                first_line_shaped = _shape_bidi_text(first_line)
                c.setFont(bold_f, 11.5)
                c.drawRightString(W - m, y, f"{first_line_shaped}  .{i}")
                y -= 17
            else:
                c.drawString(m, y, f"{i}. {first_line}")
                y -= 17
            if rest:
                y = put(y, rest, 10.5)
            c.setStrokeColorRGB(0.72, 0.72, 0.78)
            c.setLineWidth(0.7)
            for k in range(2):
                yy = y - 14 - k * 24
                c.line(m, yy, W - m, yy)
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(1)
            y -= 66

        y = new_page()
        y = put(y, f"—— {L['answer_key']} ——", 14, bold_f, "center")
        y -= 8
        for i, (_t, _q, a) in enumerate(questions, 1):
            if y < m + 30:
                y = new_page()
            y = put(y, f"{i}. {a}", 10.5)
        footer()
        c.save()

    # ------------------------------------------------------------------ Project documents
    DOCUMENT_APP_ID = "InteractiveWhiteboard"
    DOCUMENT_VERSION = 1

    def _serialize_document(self) -> dict:
        self._store_page()
        pages = []
        for page in self.pages:
            pages.append({
                "bg_kind": page["bg_kind"],
                "bg_image": (
                    base64.b64encode(_image_to_bytes(page["bg_image"])).decode("ascii")
                    if page["bg_image"] else None
                ),
                "objects": _to_jsonable(page["objects"]),
            })
        return {
            "app": self.DOCUMENT_APP_ID,
            "version": self.DOCUMENT_VERSION,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "theme": self.theme,
            "fg_color": self.fg_color,
            "current_page": self.current_page_idx,
            "layers": _to_jsonable(self.layers),
            "current_layer": self.current_layer,
            "pages": pages,
        }

    def _load_document(self, data: dict) -> None:
        if data.get("app") != self.DOCUMENT_APP_ID:
            raise ValueError("Not an InteractiveWhiteboard document.")
        version = int(data.get("version", 0))
        if version > self.DOCUMENT_VERSION:
            raise ValueError(
                f"Document version {version} is newer than supported ({self.DOCUMENT_VERSION})."
            )
        new_pages = []
        for p in data.get("pages", []):
            bg_image = None
            if p.get("bg_image"):
                bg_image = Image.open(io.BytesIO(base64.b64decode(p["bg_image"]))).convert("RGB")
            new_pages.append({
                "objects": _copy_objects(p.get("objects", [])),
                "bg_kind": p.get("bg_kind", "plain"),
                "bg_image": bg_image,
                "undo_stack": [],
                "redo_stack": [],
            })
        if not new_pages:
            raise ValueError("Document contains no pages.")
        raw_layers = data.get("layers")
        if isinstance(raw_layers, list) and raw_layers:
            self.layers = [
                {"name": str(l.get("name", f"Layer {i + 1}")), "visible": bool(l.get("visible", True))}
                for i, l in enumerate(raw_layers)
                if isinstance(l, dict)
            ]
        if not self.layers:
            self.layers = [{"name": "Layer 1", "visible": True}]
        self.current_layer = max(0, min(int(data.get("current_layer", 0)), len(self.layers) - 1))
        self.pages = new_pages
        self.theme = data.get("theme", self.theme)
        self.fg_color = data.get("fg_color", self.fg_color)
        idx = max(0, min(int(data.get("current_page", 0)), len(self.pages) - 1))
        self._apply_theme()
        self._set_page(idx, store=False)
        self._rebuild_layer_ui()

    def save_project(self, _event: tk.Event | None = None) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".wbd",
            filetypes=[("Whiteboard document", "*.wbd"), ("All files", "*.*")],
            title="Save Whiteboard Document",
        )
        if not path:
            return
        if not path.lower().endswith(".wbd"):
            path += ".wbd"
        try:
            data = self._serialize_document()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self.status_msg.config(text=f"Saved document: {path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not save document:\n{exc}")
            return
        messagebox.showinfo("Saved", f"Whiteboard document saved to:\n{path}")

    def open_project(self, _event: tk.Event | None = None) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Whiteboard document", "*.wbd"), ("All files", "*.*")],
            title="Open Whiteboard Document",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_document(data)
            self.status_msg.config(text=f"Opened document: {path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open document:\n{exc}")

    # ------------------------------------------------------------------ Image / PDF export
    def export_image(self, _event: tk.Event | None = None) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg;*.jpeg"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._render_current_image().save(path)
            messagebox.showinfo("Saved", f"Whiteboard exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not export image:\n{exc}")

    def export_pdf(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._render_current_image().save(path, "PDF", resolution=100.0)
            messagebox.showinfo("Saved", f"PDF saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not export PDF:\n{exc}")

    def export_all_pdf(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._store_page()
            frames = []
            for page in self.pages:
                frames.append(self._render_page_image(page))
            if frames:
                frames[0].save(
                    path,
                    "PDF",
                    resolution=100.0,
                    save_all=True,
                    append_images=frames[1:],
                )
            messagebox.showinfo("Saved", f"PDF exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not export PDF:\n{exc}")

    def _render_current_image(self) -> Image.Image:
        return self._render_image(self.objects, self.bg_kind, self.bg_image, self.viewport_w, self.viewport_h, self.pan_x, self.pan_y, self.zoom)

    def _render_current_image_rec(self) -> Image.Image:
        """Render the current view at the recording resolution while keeping the same world region centered."""
        w, h = self._rec_w, self._rec_h
        if w <= 0 or h <= 0 or (w == self.viewport_w and h == self.viewport_h):
            return self._render_current_image()
        scale = min(w / max(1, self.viewport_w), h / max(1, self.viewport_h))
        zoom = self.zoom * scale
        cx = self.pan_x + self.viewport_w / (2.0 * self.zoom)
        cy = self.pan_y + self.viewport_h / (2.0 * self.zoom)
        pan_x = cx - w / (2.0 * zoom)
        pan_y = cy - h / (2.0 * zoom)
        return self._render_image(self.objects, self.bg_kind, self.bg_image, w, h, pan_x, pan_y, zoom)

    def _render_page_image(self, page: dict) -> Image.Image:
        bbox = self._bbox_for_objects(page["objects"], page)
        if bbox:
            bx1, by1, bx2, by2 = bbox
            margin = 40
            w = max(int(bx2 - bx1 + 2 * margin), 200)
            h = max(int(by2 - by1 + 2 * margin), 200)
            pan_x = bx1 - margin
            pan_y = by1 - margin
            zoom = 1.0
        else:
            w, h, pan_x, pan_y, zoom = self.viewport_w, self.viewport_h, self.pan_x, self.pan_y, self.zoom
        return self._render_image(page["objects"], page["bg_kind"], page.get("bg_image"), w, h, pan_x, pan_y, zoom)

    def _bbox_for_objects(self, objects: list[dict], page: dict | None = None) -> tuple[float, float, float, float] | None:
        boxes = []
        for obj in objects:
            b = self._obj_bbox(obj)
            if b:
                boxes.append(b)
        if page and page.get("bg_image") is not None:
            boxes.append((0, 0, page["bg_image"].width, page["bg_image"].height))
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def _render_image(self, objects: list[dict], bg_kind: str, bg_image: Image.Image | None, w: int, h: int, pan_x: float, pan_y: float, zoom: float) -> Image.Image:
        bg = self._theme("bg") + (255,)
        img = Image.new("RGBA", (w, h), bg)
        draw = ImageDraw.Draw(img)
        # background
        if bg_kind == "image" and bg_image is not None:
            sx1 = int(pan_x)
            sy1 = int(pan_y)
            sx2 = int(math.ceil(pan_x + w / zoom))
            sy2 = int(math.ceil(pan_y + h / zoom))
            sx1 = max(0, min(sx1, bg_image.width))
            sy1 = max(0, min(sy1, bg_image.height))
            sx2 = max(0, min(sx2, bg_image.width))
            sy2 = max(0, min(sy2, bg_image.height))
            if sx2 > sx1 and sy2 > sy1:
                crop = bg_image.crop((sx1, sy1, sx2, sy2))
                nw = max(1, int((sx2 - sx1) * zoom))
                nh = max(1, int((sy2 - sy1) * zoom))
                resized = crop.resize((nw, nh), Image.LANCZOS)
                dx = int((sx1 - pan_x) * zoom)
                dy = int((sy1 - pan_y) * zoom)
                img.paste(resized, (dx, dy))
        else:
            if bg_kind == "dark":
                draw.rectangle([0, 0, w, h], fill=bg)
            else:
                draw.rectangle([0, 0, w, h], fill=bg)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        old_zoom, old_pan = self.zoom, (self.pan_x, self.pan_y)
        self.zoom = zoom
        self.pan_x, self.pan_y = pan_x, pan_y
        for obj in objects:
            self._render_object(od, obj)
        self.zoom, self.pan_x, self.pan_y = old_zoom, old_pan[0], old_pan[1]
        img = Image.alpha_composite(img, overlay)
        return img.convert("RGB")

    # ------------------------------------------------------------------ Open / background
    def open_image(self, _event: tk.Event | None = None) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
            self._snapshot()
            self.bg_image = img
            self.bg_kind = "image"
            self.bg_combo.set(BG_LABELS["image"])
            self.render()
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open image:\n{exc}")

    # ------------------------------------------------------------------ PDF import
    PDF_IMPORT_DPI_ZOOM = 2.0  # ~144 dpi render scale
    PDF_IMPORT_PAGE_CAP = 60

    def _render_pdf_pages(self, path: str, max_pages: int) -> list[Image.Image]:
        """Render the first pages of a PDF to RGB images (no UI)."""
        if not HAS_PYMUPDF:
            raise RuntimeError("PyMuPDF is not installed.")
        doc = _pymupdf.open(path)
        try:
            count = min(doc.page_count, max_pages)
            matrix = _pymupdf.Matrix(self.PDF_IMPORT_DPI_ZOOM, self.PDF_IMPORT_DPI_ZOOM)
            images = []
            for i in range(count):
                pix = doc[i].get_pixmap(matrix=matrix, alpha=False)
                images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            return images
        finally:
            doc.close()

    def import_pdf(self, _event: tk.Event | None = None) -> None:
        if not HAS_PYMUPDF:
            messagebox.showwarning(
                "Import PDF",
                "PyMuPDF is required for PDF import.\nInstall it with: pip install PyMuPDF",
            )
            return
        path = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            title="Import PDF as Pages",
        )
        if not path:
            return
        try:
            doc_count = _pymupdf.open(path).page_count
        except Exception as exc:
            messagebox.showerror("Import PDF", f"Could not open PDF:\n{exc}")
            return
        if doc_count == 0:
            messagebox.showwarning("Import PDF", "This PDF has no pages.")
            return
        cap = self.PDF_IMPORT_PAGE_CAP
        if doc_count > cap and not messagebox.askyesno(
            "Import PDF", f"The PDF has {doc_count} pages. Import only the first {cap}?"
        ):
            return
        count = min(doc_count, cap)
        replace = messagebox.askyesno(
            "Import PDF",
            f"Import {count} page(s)?\n\nYES = replace current board\nNO = append after current page",
        )
        try:
            images = self._render_pdf_pages(path, count)
        except Exception as exc:
            messagebox.showerror("Import PDF", f"Could not render PDF:\n{exc}")
            return
        new_pages = [
            {"objects": [], "bg_kind": "image", "bg_image": img, "undo_stack": [], "redo_stack": []}
            for img in images
        ]
        self._selected_idx = None
        if replace:
            self.pages.clear()
            self.objects.clear()
            self.pages.extend(new_pages)
            self._set_page(0, store=False)
        else:
            self._store_page()
            at = self.current_page_idx + 1
            self.pages[at:at] = new_pages
            self._set_page(at, store=False)
        self.status_msg.config(text=f"Imported {len(images)} PDF page(s) from {Path(path).name}")

    # ------------------------------------------------------------------ Autosave
    def _autosave_path(self) -> Path:
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA", Path.home())))
        else:
            base = Path.home() / ".local" / "share"
        d = base / "InteractiveWhiteboard"
        d.mkdir(parents=True, exist_ok=True)
        return d / "autosave.pkl"

    def _autosave(self) -> None:
        try:
            self._store_page()
            pages = []
            for page in self.pages:
                pages.append({
                    "objects": _copy_objects(page["objects"]),
                    "bg_kind": page["bg_kind"],
                    "bg_image": _image_to_bytes(page["bg_image"]) if page["bg_image"] else None,
                })
            with open(self._autosave_path(), "wb") as f:
                pickle.dump({"version": 2, "pages": pages, "theme": self.theme, "fg_color": self.fg_color}, f, pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass
        self.root.after(60000, self._autosave)

    def _check_autosave(self) -> None:
        path = self._autosave_path()
        if path.exists():
            if messagebox.askyesno("Restore session", "An autosaved session was found. Restore it?"):
                self._load_autosave(path)
            else:
                try:
                    path.unlink()
                except Exception:
                    pass

    def _load_autosave(self, path: Path) -> None:
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            new_pages = []
            for p in data.get("pages", []):
                bg_image = Image.open(io.BytesIO(p["bg_image"])).convert("RGB") if p.get("bg_image") else None
                new_pages.append({
                    "objects": _copy_objects(p.get("objects", [])),
                    "bg_kind": p.get("bg_kind", "plain"),
                    "bg_image": bg_image,
                    "undo_stack": [],
                    "redo_stack": [],
                })
            if new_pages:
                self.pages = new_pages
                self.theme = data.get("theme", self.theme)
                self.fg_color = data.get("fg_color", self.fg_color)
                self._apply_theme()
                self._set_page(0, store=False)
        except Exception as exc:
            messagebox.showerror("Restore failed", f"Could not restore session:\n{exc}")

    def _on_close(self) -> None:
        self._autosave()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    WhiteboardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
