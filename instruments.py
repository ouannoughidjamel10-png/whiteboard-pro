"""Realistic draggable drawing instruments (ruler / protractor / compass).

Mixin for WhiteboardApp. Instruments live above the board in screen-space
(constant size), anchored at world coordinates so they pan/zoom naturally.
"""
from __future__ import annotations

import math


class InstrumentsMixin:
    RULER_LEN = 430.0
    RULER_H = 42.0
    PROT_R = 150.0

    # ------------------------------------------------------------------ state helpers
    def _instr_init_state(self) -> None:
        self.instruments = {
            "ruler":      {"visible": False, "center": (0.0, 0.0), "angle": 0.0},
            "protractor": {"visible": False, "center": (0.0, 0.0), "angle": 0.0},
            "compass":    {"visible": False, "pivot": (0.0, 0.0),
                           "angle_deg": -30.0, "len_px": 150.0,
                           "sweep": (None, None)},
        }
        self._instr_drag = None

    def toggle_instrument(self, kind: str) -> None:
        inst = self.instruments[kind]
        inst["visible"] = bool(self.instr_vars[kind].get())
        if inst["visible"]:
            cx, cy = self._get_viewport_center_world()
            if kind == "compass":
                if inst["pivot"] == (0.0, 0.0):
                    inst["pivot"] = (cx - 120 / self.zoom, cy + 40 / self.zoom)
            elif inst["center"] == (0.0, 0.0):
                inst["center"] = (cx, cy)
        self.render()

    def _instr_anchor(self, kind: str):
        if kind == "compass":
            return (self._world_to_screen(*self.instruments[kind]["pivot"]),
                    math.radians(self.instruments[kind]["angle_deg"]))
        return (self._world_to_screen(*self.instruments[kind]["center"]),
                math.radians(self.instruments[kind]["angle"]))

    @staticmethod
    def _rot_pt(px: float, py: float, ax: float, ay: float, ang: float):
        ca, sa = math.cos(ang), math.sin(ang)
        dx, dy = px - ax, py - ay
        return ax + dx * ca - dy * sa, ay + dx * sa + dy * ca

    def _compass_len(self) -> float:
        return float(self.instruments["compass"].get("len_px", 150.0))

    # ------------------------------------------------------------------ drawing
    def render_instruments_layer(self, d) -> None:
        self._draw_ruler_instr(d)
        self._draw_protractor_instr(d)
        self._draw_compass_instr(d)

    def _draw_ruler_instr(self, d) -> None:
        inst = self.instruments["ruler"]
        if not inst.get("visible"):
            return
        (cx, cy), ang = self._instr_anchor("ruler")
        L, H = self.RULER_LEN, self.RULER_H
        corners = [self._rot_pt(cx + dx, cy + dy, cx, cy, ang)
                   for dx, dy in [(-L / 2, -H / 2), (L / 2, -H / 2),
                                  (L / 2, H / 2), (-L / 2, H / 2)]]
        d.polygon(corners, fill=(205, 228, 245, 110), outline=(20, 80, 160, 255))
        ux, uy = math.cos(ang), math.sin(ang)
        sx, sy = self._rot_pt(cx - L / 2, cy + H / 2, cx, cy, ang)
        i = 0
        while i * 9 <= L:
            ln = 11 if i % 9 == 0 else (6 if i % 3 == 0 else 3)
            d.line([(sx, sy), (sx + uy * ln, sy - ux * ln)], fill=(25, 90, 170, 230))
            if i % 9 == 0:
                d.text((sx + uy * 14 + 1, sy - ux * 14 - 6), str(i // 9),
                       fill=(15, 60, 130, 255))
            sx += ux * 9
            sy += uy * 9
            i += 1
        kx, ky = self._rot_pt(cx + L / 2 + 16, cy, cx, cy, ang)
        d.ellipse([kx - 11, ky - 11, kx + 11, ky + 11],
                  fill=(33, 150, 243, 210), outline=(255, 255, 255, 255))

    def _draw_protractor_instr(self, d) -> None:
        inst = self.instruments["protractor"]
        if not inst.get("visible"):
            return
        (cx, cy), ang = self._instr_anchor("protractor")
        R = self.PROT_R
        deg_off = math.degrees(ang) + 180.0
        d.pieslice([cx - R, cy - R, cx + R, cy + R], start=deg_off, end=deg_off + 180,
                   fill=(180, 214, 240, 100), outline=(20, 80, 160, 255))
        d.arc([cx - R, cy - R, cx + R, cy + R], start=deg_off, end=deg_off + 180,
              fill=(20, 80, 160, 255), width=3)

        def local(t_deg: float):
            rad = ang + math.pi + math.radians(t_deg)
            return math.cos(rad), math.sin(rad)

        p_l = (cx + R * local(0)[0], cy + R * local(0)[1])
        p_r = (cx + R * local(180)[0], cy + R * local(180)[1])
        d.line([p_l, p_r], fill=(20, 80, 160, 255), width=2)
        for t in range(0, 181, 5):
            ux_, uy_ = local(t)
            ln = 13 if t % 10 == 0 else 6
            d.line([(cx + R * ux_, cy + R * uy_),
                    (cx + (R - ln) * ux_, cy + (R - ln) * uy_)],
                   fill=(20, 80, 160, 220))
            if t % 30 == 0:
                d.text((cx + (R - 28) * ux_ - 6, cy + (R - 28) * uy_ - 7), str(t),
                       fill=(15, 60, 130, 255))
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(220, 40, 40, 255))
        kx, ky = p_r
        d.ellipse([kx - 10, ky - 10, kx + 10, ky + 10],
                  fill=(33, 150, 243, 210), outline=(255, 255, 255, 255))

    def _draw_compass_instr(self, d) -> None:
        inst = self.instruments["compass"]
        if not inst.get("visible"):
            return
        (px, py), ang = self._instr_anchor("compass")
        leg = self._compass_len()
        tip = (px + leg * math.cos(ang), py + leg * math.sin(ang))
        d.line([(px, py), tip], fill=(70, 70, 78, 235), width=5)
        d.line([(px, py), (px - 26, py - 46)], fill=(70, 70, 78, 235), width=4)
        d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=(205, 205, 212, 255),
                  outline=(50, 50, 58, 255), width=3)
        d.ellipse([tip[0] - 8, tip[1] - 8, tip[0] + 8, tip[1] + 8],
                  fill=(33, 150, 243, 225), outline=(255, 255, 255, 255))
        a0, a1 = inst.get("sweep", (None, None))
        if a0 is not None and a1 is not None and abs(a1 - a0) > 0.5:
            s, e = sorted((a0, a1))
            lw = max(2, int(self.brush_size * max(1.0, self.zoom)))
            col = tuple(int(c * 255) for c in (0, 0, 0)) if False else (226, 60, 60, 255)
            try:
                rr, gg, bb, _aa = __import__("whiteboard").hex_to_rgba(self.fg_color, 255)
                col = (rr, gg, bb, 255)
            except Exception:
                pass
            d.arc([px - leg, py - leg, px + leg, py + leg], start=s, end=e,
                  fill=col, width=lw)
            mid = math.radians((s + e) / 2)
            lx, ly = px + (leg + 20) * math.cos(mid), py + (leg + 20) * math.sin(mid)
            d.text((lx, ly), f"R={leg / max(self.zoom, 1e-6):.1f}",
                   fill=(200, 30, 30, 255))

    # ------------------------------------------------------------------ interaction
    def _instrument_press(self, sx: float, sy: float) -> bool:
        def near(px, py, qx, qy, r):
            return (px - qx) ** 2 + (py - qy) ** 2 <= r * r

        ruler = self.instruments["ruler"]
        if ruler.get("visible"):
            (cx, cy), ang = self._instr_anchor("ruler")
            kx, ky = self._rot_pt(cx + self.RULER_LEN / 2 + 16, cy, cx, cy, ang)
            if near(sx, sy, kx, ky, 17):
                self._instr_drag = ("rot", "ruler", 0.0, 0.0)
                return True
            lx, ly = self._rot_pt(sx, sy, cx, cy, ang)
            lx, ly = lx - cx, ly - cy
            if abs(ly) <= self.RULER_H / 2 + 8 and abs(lx) <= self.RULER_LEN / 2 + 8:
                wx, wy = self._screen_to_world(sx, sy)
                wc = ruler["center"]
                self._instr_drag = ("move", "ruler", wc[0] - wx, wc[1] - wy)
                return True
        prot = self.instruments["protractor"]
        if prot.get("visible"):
            (cx, cy), ang = self._instr_anchor("protractor")
            ur = ang + math.pi
            kx, ky = cx + self.PROT_R * math.cos(ur), cy + self.PROT_R * math.sin(ur)
            if near(sx, sy, kx, ky, 16):
                self._instr_drag = ("rot", "protractor", 0.0, 0.0)
                return True
            dist = math.hypot(sx - cx, sy - cy)
            loc_a = (math.atan2(sy - cy, sx - cx) - ang - math.pi + math.pi) % (2 * math.pi)
            if dist <= self.PROT_R + 8 and loc_a <= math.pi + 0.12:
                wx, wy = self._screen_to_world(sx, sy)
                wc = prot["center"]
                self._instr_drag = ("move", "protractor", wc[0] - wx, wc[1] - wy)
                return True
        comp = self.instruments["compass"]
        if comp.get("visible"):
            (px, py), _ = self._instr_anchor("compass")
            rad = math.radians(comp["angle_deg"])
            tip = (px + self._compass_len() * math.cos(rad),
                   py + self._compass_len() * math.sin(rad))
            if near(sx, sy, tip[0], tip[1], 18):
                cur = math.degrees(math.atan2(sy - py, sx - px))
                comp["sweep"] = (cur, cur)
                self._instr_drag = ("compass", 0.0, 0.0)
                return True
            if near(sx, sy, px, py, 16):
                wx, wy = self._screen_to_world(sx, sy)
                pv = comp["pivot"]
                self._instr_drag = ("move", "compass", pv[0] - wx, pv[1] - wy)
                return True
        return False

    def _instrument_drag(self, sx: float, sy: float) -> bool:
        if not self._instr_drag:
            return False
        mode, kind = self._instr_drag[0], self._instr_drag[1]
        if mode == "move":
            inst = self.instruments[kind]
            key = "pivot" if kind == "compass" else "center"
            wx, wy = self._screen_to_world(sx, sy)
            inst[key] = (wx + self._instr_drag[2], wy + self._instr_drag[3])
            self.request_render()
            return True
        if mode == "rot":
            inst = self.instruments[kind]
            (ax, ay), _cur = self._instr_anchor(kind)
            new_ang = math.degrees(math.atan2(sy - ay, sx - ax))
            if kind == "protractor":
                inst["angle"] = new_ang - 180.0
            else:
                inst["angle"] = new_ang
            self.request_render()
            return True
        if kind == "compass" and mode != "compass":
            pass
        if self._instr_drag[0] == "compass":
            comp = self.instruments["compass"]
            (px, py), _ = self._instr_anchor("compass")
            cur = math.degrees(math.atan2(sy - py, sx - px))
            dist = math.hypot(sx - px, sy - py)
            a0, _a1 = comp.get("sweep", (None, None))
            comp["sweep"] = (comp["sweep"][0], cur)
            comp["angle_deg"] = cur
            if 30 <= dist <= 340 and a0 is not None:
                comp["len_px"] = float(dist)
            self.request_render()
            return True
        return False

    def _instrument_release(self) -> bool:
        if not self._instr_drag:
            return False
        was_compass = self._instr_drag[0] == "compass"
        self._instr_drag = None
        if was_compass:
            comp = self.instruments["compass"]
            a0, a1 = comp.get("sweep", (None, None))
            comp["sweep"] = (None, None)
            delta = abs(((a1 - a0) + 180.0) % 360.0 - 180.0) if a0 is not None and a1 is not None else 0
            if delta > 2:
                r_world = self._compass_len() / max(self.zoom, 1e-6)
                rad = math.radians(comp["angle_deg"])
                pv = comp["pivot"]
                end = (pv[0] + r_world * math.cos(rad), pv[1] + r_world * math.sin(rad))
                self._snapshot()
                self._append_object({
                    "type": "compass", "center": pv, "p2": end, "radius": r_world,
                    "color": self.fg_color, "width": self.brush_size / self.zoom,
                })
                self.render()
                return True
        self.render()
        return True

    # ------------------------------------------------------------------ pen snapping
    def _snap_point_to_instrument(self, wx: float, wy: float):
        sx, sy = self._world_to_screen(wx, wy)
        ruler = self.instruments["ruler"]
        if ruler.get("visible"):
            (cx, cy), ang = self._instr_anchor("ruler")
            ex1, ey1 = self._rot_pt(cx - self.RULER_LEN / 2, cy + self.RULER_H / 2,
                                    cx, cy, ang)
            ex2, ey2 = self._rot_pt(cx + self.RULER_LEN / 2, cy + self.RULER_H / 2,
                                    cx, cy, ang)
            vx, vy = ex2 - ex1, ey2 - ey1
            seg2 = vx * vx + vy * vy
            t = ((sx - ex1) * vx + (sy - ey1) * vy) / seg2
            qx, qy = ex1 + t * vx, ey1 + t * vy
            if math.hypot(sx - qx, sy - qy) < 16 and -0.02 <= t <= 1.02:
                return self._screen_to_world(qx, qy)
        prot = self.instruments["protractor"]
        if prot.get("visible"):
            (cx, cy), ang = self._instr_anchor("protractor")
            dist = math.hypot(sx - cx, sy - cy)
            if abs(dist - self.PROT_R) < 20:
                loc = (math.atan2(sy - cy, sx - cx) - ang - math.pi) % (2 * math.pi)
                if loc <= math.pi:
                    rad = ang + math.pi + loc
                    qx, qy = cx + self.PROT_R * math.cos(rad), cy + self.PROT_R * math.sin(rad)
                    return self._screen_to_world(qx, qy)
        return None
