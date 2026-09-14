# PROJECT BRIEF — Interactive Whiteboard Pro (AI Handoff Document)
> انسخ هذا الملف كاملاً لأي نموذج LLM ليصبح قادراً على مواصلة تطوير المشروع فوراً.

## 1) الهوية والهدف
تطبيق سبورة تفاعلية سطح مكتب لـ Windows موجّه للمدرّس العربي (رياضيات/فيزياء/كيمياء).
- **النسخة الحالية النشطة**: `whiteboard_qt.py` (PySide6/Qt6) — اسم المنتج WhiteboardPro.
- **نسخة تراثية**: `whiteboard.py` (Tkinter، ~4300 سطر) — ما زالت تعمل وتحتوي ميزة تسجيل الشاشة REC، وتُستخدم **كمكتبة منطق مشتركة** (استيراد كسول).
- لغة المستخدم: العربية. تعليقات الكود بالإنجليزية.

## 2) خريطة الملفات
| الملف | الدور |
|---|---|
| `whiteboard_qt.py` (~2600 سطر) | التطبيق الحالي كاملاً: MainWindow + BoardView(QGraphicsView) + عناصر المشهد + كل الميزات |
| `whiteboard.py` (Tkinter) | منطق مشترك يُستورد كسولياً: `WORKSHEET_TOPICS`, `generate_problem_raw(topic,level,lang)`, `generate_verified_questions(topics,per_topic,level,lang)`, `CHEMISTRY_EQUATIONS`, `PHYSICS_EQUATIONS`, `WORKSHEET_LANGS`, `_shape_bidi_text`, `molar_mass`, و`WhiteboardApp._write_worksheet_pdf` (method) |
| `instruments.py` | أدوات هندسية لنسخة Tkinter فقط (Qt لديه نسخه الخاصة داخل whiteboard_qt) |
| `nav_tools.py` | **طبقة التنقّل الاحترافية** (نظير أدوات Adobe): `NavViewport` (نموذج التحويل) · `NavigationController` (معالجة الأحداث) · `NavigatorPanel` (لوحة المعاينة). **مستوردة في `whiteboard_qt.py:50`** — لا تحذفها من git وإلا فشل الاستيراد |
| `run_whiteboard.py` | مشغّل تطويري: `python run_whiteboard.py` (مسار نسبي، لا مسار مطلق) |
| `tests/` | **الاختبارات الدائمة** (انظر `tests/README.md`): `test_pen_tool.py` (21 فحصاً لأداة القلم) · `wb_penmath_test.py` · `wb_penfix_test.py` |
| `icon.ico`, `Whiteboard.spec`, `WhiteboardPro.spec` | بناء |
| `README.md` | وصف تسويقي/مستخدم |
| `test_nav_tools.py`, `_smoke_nav_integration.py` | اختبارا التنقّل (في جذر المشروع) |

## 3) البنية المعمارية (Qt)
- `MainWindow(QMainWindow)`: يملك `QGraphicsScene(-100k..200k)` و `BoardView`. الشريط الجانبي **مُلفّ في `QScrollArea`** (`sidebarScroll`) لأن محتواه أطول من معظم الشاشات — انظر فخّ 24.
- `BoardView(QGraphicsView)`: كل منطق الضغط/السحب/الإفلات حسب `win.tool`.
- **التنقّل ليس مملوكاً لـBoardView بل لـ`nav_tools`**: `view.nav` = `NavigationController`. أشرطة التمرير **مخفية دائماً** (`ScrollBarAlwaysOff`) = لوحة لا نهائية.
- ترتيب معالجة mousePressEvent: **`nav.press(e)` أولاً** (أوسط/Space/Hand/Zoom/Rotate) → text → latex → laser → vpen → nodeedit → instrument_press → snap_pen → select(سوبر) → زر أيسر → eraser → pen/highlighter → shapes.
- العناصر = عناصر Qt حقيقية (QGraphicsPathItem/Line/Rect/Ellipse/TextItem/PixmapItem) — **لا إعادة رسم كاملة**؛ GPU يكفي حتى آلاف الكائنات.

### طبقة التنقّل (`nav_tools.py`) — أُضيفت بعد P6
`view.nav` هو **المالك الوحيد** للزوم/التمرير/الدوران:
- **Hand**: سحب ١:١ بلا فقدان بكسل · **Zoom**: نقرة = درجة في السلّم، Alt+نقرة = درجة للخلف، سحب = مستطيل تكبير يبقى متمركزاً · **Rotate Canvas**: سحب = زاوية السحب، نقر مزدوج = تصفير.
- **Space** = Hand مؤقّت أثناء أي أداة رسم (ويُستهلك فلا يرسم) · **الزر الأوسط** = تمرير · **Shift+عجلة** = تمرير أفقي.
- **عجلة الفأرة** تُبقي النقطة تحت المؤشر ثابتة (`zoom_at`) — مقيس: انحراف ‎5.7e-14‎.
- **لوحة Navigator** في الشريط الجانبي + `fit_content()` + `actual_size()` (100% بالضبط).
- **قاعدتان صارمتان**: التنقّل **لا يُنشئ أي مدخل Undo**، و**لا يلمس عناصر المشهد** إطلاقاً.
- **سبب إعادة الكتابة**: النسخة القديمة كانت `scrollBar.setValue(v.value() - int(delta))` — (١) `int()` يُسقط حتى ١ بكسل لكل حدث فيتخلّف المحتوى عن المؤشر («مطاطي»)، (٢) تتوقف كلياً عندما يكون المحتوى أصغر من العرض.

## 4) نظام الحمولات Payloads (الأهم — احفظه حرفياً)
كل كائن يحمل قاموس حمولة في **خاصية بايثون** `it._payload` (وليس setData!). الوصول دائماً عبر:
```python
def pl_of(it): return getattr(it, "_payload", None)
```
`it.setData(0, True)` مجرد علامة truthy. الفلترة: `pl.get("_instr")` = True يعني أداة هندسية (تُستثنى من الحفظ/الطبقات).

### المخططات (Schemas) — الإحداثيات بمقياس المشهد، y لأسفل:
```
pen:        {type, points:[[x,y]..], width, widths?:[..], variable?:True,
             color, alpha:0-255, layer}
highlighter: مثل pen + alpha≈90
line:       {type, p1:[x,y], p2:[x,y], color, width, layer}
arrow:      line + head:[[x,y]×3] (back-left, tip, back-right)
rect/oval:  {type, x1,y1,x2,y2, color, width, fill:None|"#hex", layer}
polygon:    {type, points:[[x,y]..], color, width, fill?, layer}
text:       {type, pos:[x,y], text, size(pt), color, layer}
latex:      {type, tex, size, base(=الحجم الأصلي), pos, color, scale, layer}
image:      {type, png:base64, pos, scale, layer,
             src_pdf?:path, src_page?:int, page_pt?:[w_pt,h_pt]}   ← لصفحات PDF المستوردة
compass:    {type, center:[x,y], p2:[x,y], radius, color, width, layer}
group:      {type, items:[payloads الأبناء], layer}
vpath:      {type:"vpath", closed:bool, nodes:[node..], fill:None|"#hex",
             stroke:{color,width,alpha}, rot, layer}      ← مسار القلم/Bezier
node:       {p:[x,y], out:[dx,dy]|None, in:[dx,dy]|None,
             t:"corner"|"smooth"|"asym"}
```
- `translate_payload(pl,dx,dy)` يترجم كل الأنواع (تستخدمها المجموعات).
- `payload_to_item(pl)` يبني العنصر ويضبط `_payload=deepcopy(pl)` + flags(Selectable|Movable).
- `_payloads()` يجمّع من المشهد (مع تفكيك المجموعات إلى {type:group,items} وتخطي الأبناء).

### ⚠ اصطلاح مقابض `vpath` — احفظه حرفياً (خطأ إشارة كلّف ساعات)
```
out = control_point - anchor        }  كلاهما إزاحة من العقدة، بنفس الإشارة
in  = control_point - anchor        }
⇒ العقدة الناعمة تخزّن  in == -out  (انعكاس)
⇒ نقطة التحكّم الواصلة إلى عقدة = anchor + in
```
كانت دوالّ الرسم الثلاث تحسب `anchor - in` بينما كل المسارات التفاعلية
(انعكاس السحب، التقسيم، الحذف، ink→vpath، اختبار إصابة المقبض) تفترض
`control - anchor` ⇒ **كل عقدة «ناعمة» كانت كسراً بـ180° يلتفّ على نفسه**.
الملفات المتأثرة عند الإصلاح: `_vpath_to_qpath` · `_vp_seg_bezier` ·
`_vpen_rubber` · `_vp_split_segment` · `_qpath_to_vpath_nodes`.
**إن رأيت `anchor - in` مرة أخرى، فهو الخطأ نفسه.**

## 5) الأدوات الهندسية (Qt)
`InstrumentItem(QGraphicsItem)` أساس + `RulerItem/ProtractorItem/CompassItem`.
- `_payload={"_instr":True}`، zValue=500، ظل QGraphicsDropShadowEffect.
- الضغط: **أولوية المقابض (hit_role<16px) ثم body contains()** — لأن boundingRect أوسع من الشكل.
- الفرجار: `arc_a0` يُلتقط **لحظة الضغط** على الرِجل (ليس أول حركة)، `commit()` يرجع compass payload عند span>2°.
- القلم يلتقط: `snap_pen(sp)` يمر على الأدوات ويعيد إسقاطاً على حافة المسطرة/قوس المنقلة (تسامح 15-17px).
- **ممنوع** `scene.items(QPointF)` — غير موثوق؛ iterate الكل + فلترة.

## 6) الميزات → نقاط الكود
| الميزة | الدوال/الأصناف |
|---|---|
| LaTeX فيكتور | `latex_to_qpath` (matplotlib TextPath→QPainterPath، y مقلوبة)، حوار `open_equation_dialog` بمعاينة حية، `_restyle` يتعامل scale=width/base، SVG عبر `qpath_to_svg_d` |
| PDF استيراد | `_render_pdf_images(path,dpi)` → [(QImage,w_pt,h_pt)]، `import_pdf` (حوار dpi + نمطا إدراج) |
| Unlock | `unlock_to_vector`: pymupdf get_text("dict") spans→text payloads + get_drawings (l/c/re، c يُسطَّر 8 قطع) → pen/polygon(fill) |
| PDF Overlay export | `_export_overlay_pdf(path,dpi)`: show_pdf_page للأصل + overlay PNG شفاف للشرح |
| PDF vector export | `_export_pdf(path,rect,dpi,vector_text)`: QPdfWriter؛ عند vector_text يُخفى النصوص ثم تُرسم drawText (نص حقيقي قابل للتحديد — مُثبت بـPyMuPDF) |
| Flatten dialog | `export_flatten` (Ctrl+E): preset/slider توازن/dpi/alpha/selection-only/preview/Copy-for-Word |
| حافظة Word | `copy_selection` → `_put_word_clipboard(payloads,img_alpha,rect)`: يضع CLIP_MIME + image/png(شفاف) + image/svg+xml (`_selection_svg`) + DIB أبيض |
| Group/Ungroup | `BoardGroup` (ItemSendsGeometryChanges **ضروري**) itemChange يترجم حمولات الأبناء؛ `group_selection/ungroup_selection`؛ الحفظ يفكّها إلى {type:group,items} |
| Properties | `update_props_panel` (selectionChanged) + `_restyle(it,color,width)`: للنص size، للمتغير widths×ratio (**التقط old_width قبل التحديث**)، للـlatex scale |
| Layers | `self.layers[{name,visible}]`, `current_layer`; `_apply_layer_visibility`; الحمولات تحمل layer int |
| Pages | `self.pages[list[payloads]]`, `_load_page/_sync_page_store` |
| Worksheet | `open_worksheet_maker`: QDialog → legacy.generate_verified_questions → إدراج نصوص أو `_write_worksheet_pdf` عبر حيلة `_PDFHost` (لأنها method) |
| مكتبات المعادلات | `_open_equation_library(title,cats)` عاملة للفئتين |
| Laser | `laser_press/move/fade` (QTimer 70ms، عمر 1.5ث) |
| REC (تسجيل MP4) | `toggle_recording/_start_recording/_stop_recording/_rec_capture_frame/_rec_grab_frame` + حوار `_rec_settings_dialog` (720p..4K، fps 10-120، جودة 1-10)؛ زر `rec_btn` (F9)؛ `viewport().grab()` → RGB888 → numpy → `imageio.get_writer(libx264, macro_block_size=1)`؛ `macro_block_size=1` **ضروري** وإلا يُمدّ 1080→1088 |
| SnapEngine (P1) | `SnapEngine.snap(sp,origin,shift,alt,grid)` → نقطة+نوع؛ نقاط الكائنات (نهايات/منتصف/مركز/محاور بيضاوي) > زوايا 15° (Shift) > ortho ضمني > grid24؛ tol=12px/zoom؛ مؤشرات `BoardView._show_snap` (مربع/مثلث/دائرة/معين)؛ زر Snap (Ctrl+Shift+S) = `snap_on` |
| مثبّت الحبر (P1) | `_rdp_simplify/_rdp_keep_indices` (eps≈1-1.4) + `_catmull_bezier_path` + `_smooth_stroke_path`؛ عند الإفلات: pen عادي → ناعم، brush → RDP على نقاط+أزمنة معاً (widths متزامنة) |
| TransformBox (P1) | `_update_tbox` (تحديد واحد + أداة select، لا مجموعات)؛ 8 مقابض + rot فوق المنتصف؛ زوايا=uniform (Shift=حر)، حواف=محور واحد؛ rot يُطبّق عبر `rotate_payload`+حقل `rot` (payload_to_item يعيّن setRotation)؛ `scale_payload/rotate_payload` + `_rebuild_item_geometry` يعيد البناء من الحمولة الحية؛ يتبع الحركة الأصلية عند الإفلات |
| Shiboken refs (CRITICAL) | **أي عنصر يُضاف بلا مرجع Python يفقد `_payload` عند أول GC!** الحل: `MainWindow._add_item(it)` يضيف للمشهد + `self._item_refs` — **كل** addItem في التطبيق يجب عبرها |
| V-Pen + NodeEdit (P2) | schema v2: `{type:"vpath",closed,nodes:[{p,in,out,t:corner\|smooth\|asym}],stroke{color,width,alpha},fill,rot,layer}` — دوال نقية `_vp_node/_vpath_to_qpath/_vp_seg_bezier/_vp_point_on_seg/_vp_split_segment(de Casteljau shape-preserving)/_vp_delete_node/_ink_to_vpath/_vp_path_bbox`؛ أداة `vpen` (نقرة=corner، سحب=smooth متناظر، Alt=asym، إغلاق بالنقر على الأولى ≤12px/zoom، Enter=commit مفتوح، Esc=إلغاء، push_undo عند أول عقدة)؛ أداة `nodeedit` (سحب عقدة/مقبض، Alt=فك تناظر، Alt+نقر مقطع=قسمة de Casteljau عند t الأقرب، Del=حذف+تنعيم الجارين، S/C=تحويل نوع، مستطيل تحديد مطاطي، overlay `_ne_overlay` z=9500)؛ `ink_to_path` (Ctrl+Shift+K): RDP(1.4)+Catmull→nodes (in/out=±1/6 الجوار)؛ TransformBox/SnapEngine/SVG(`_vpath_svg_d` → M+C+Z)/_restyle/_rebuild تعالج vpath؛ round-trip بايت-مطابق |
| التلوين (P3) | fill schema موسع: `None \| "#hex" \| {kind:linear(angle)\|radial(center,radius), stops:[[t,"#hex",α]...]}` — `_norm_fill/_fill_qbrush/apply_fill_to_item` (إحداثيات نسبية تُرسم على boundingRect وتُعاد عند التحجيم في `_rebuild_item_geometry`)؛ `GradientDialog` (نوع+زاوية+stops قابلة للإضافة/الحذف/التلوين+α+معاينة حية+Apply) زر Fill في الخصائص؛ SVG: `_svg_gradient_def/_svg_fill_attr` → `<defs><linearGradient/radialGradient gradientUnits="userSpaceOnUse">` + `fill="url(#gN)"`؛ أنماط خط: `dash [8,6]/[2,4]` + `join round/miter/bevel` + `alpha` (vpath تحت stroke، البقية أعلى الحمولة) عبر `apply_prop_dash/join/alpha + _refresh_item_pen`؛ قطّارة (زر Pick، Ctrl+Shift+I) + Swatches (10 افتراضية + محفوظة بـ`~/.whiteboard_swatches.json`، `_remember_swatch` LRU 10) |
| Chalkboard | `toggle_theme` → `win.dark` يغير drawBackground |
| Boolean (P4) | `payload_to_qpath/_qpath_to_vpath_nodes/boolean_payloads(unite/subtract/intersect)` — Qt قد يفلّت المنحنيات → إذا >60 عقدة: RDP تقريب؛ أزرار ∪−∩ (تحديد 2، الترتيب بzValue، الناتج vpath يرث fill/stroke) |
| لصق Office (P4) | `text/html` جداول → `_html_rows` (regex) → `_table_payloads` (خطوط شبكة+نصوص خلايا)؛ text/plain→نص؛ CLIP_MIME داخلي؛ PNG/صور |
| تحرير النص (P4) | dblclick بأداة select (بحث عبر `_item_refs` لأن wrappers قد تفقد `_payload`) → `edit_text_item` (TextEditorInteraction+watch) → `_commit_text_edits` (hook في mousePressEvent) |
| Align/Distribute (P4) | `align_selection(left/right/hcenter/top/bottom/vcenter + hdist/vdist)` عبر moveBy + `sync_item_payload_pos` فوراً |
| Flip / Reflect (2026-09-14) | `flip_selection("h"\|"v")` — انعكاس حول مركز bounding box للتحديد، عبر `scale_payload(±1)` ثم `_rebuild_item_geometry`. **يستدعي `sync_item_payload_pos` أولاً** (وإلا يقفز العنصر المسحوب أصلياً). المجموعات تُعكس ابناً ابناً (حمولة الابن هي المصدر). `text/latex/image` تُعكس **صناديقها** لا نقطة أصلها فقط. أزرار ⇋ ⇵ في لوحة COMBINE/ALIGN + Ctrl+Shift+H/J |
| Precision HUD (2026-09-14) | `BoardView.hud_text/_hud_show/_hud_clear` — `QGraphicsTextItem` بـ`setScale(1/zoom)` وإزاحة `15/zoom` ⇒ **حجم ثابت على الشاشة عند أي زوم**. يظهر لأداتَي `vpen`/`nodeedit` فقط ويُمسح في `set_tool`. يُضاف عبر `_item_refs` (فخّ 14) وبلا `_payload` فلا يُحفظ |
| Numeric node entry (2026-09-14) | `MainWindow._sync_node_pos_fields` / `apply_node_pos` + `node_x`/`node_y` (QDoubleSpinBox) في الشريط الجانبي. **نقطة الاختناق**: `_ne_redraw_handles_only` تنادي `_sync_node_pos_fields` فيتحدّث الصندوقان مع كل تغيير تحديد وكل سحب. حارس `_node_field_loading` يمنع الرجع (echo) |
| Curve / Convert anchor (2026-09-14) | أداة `curve` (نظير Anchor Point Tool): `_curve_press/_curve_move/_curve_release/_curve_apply` + `_curve_hit` (عقدة تتقدّم على ضلع). **تُعيد الحساب من `_cv_snapshot`** (deepcopy عند الضغط) فلا يتراكم الخطأ. سحب **عقدة** ⇒ `out=drag` و`in=-out` و`t="smooth"` (فينحني الضلعان المتصلان). سحب **ضلع** ⇒ `c1+=4d/3` و`c2+=4d/3` حيث `d = المؤشر - منتصف الضلع لحظة الضغط`؛ لأن `B(0.5)=(P0+3c1+3c2+P3)/8` فالمنتصف يهبط **تحت المؤشر بالضبط** (مقيس: خطأ 0.00e+00). الطرفان لا يتحركان، و`t` يصير `asym` على الطرفين المعدَّلين |
| Break handle (2026-09-14) | في `_vpen_press`: **Alt+ضغط على العقدة الأخيرة** أثناء جلسة القلم ⇒ `nd["out"]=None` و`t="asym"` (يبقى `in`) ⇒ **الضلع التالي مستقيم**. ومع السحب يسحب مقبض خروج جديداً مستقلاً. `_vp_break_drag` يُثبّت الكسر **طوال السحب** حتى لو أُطلق Alt في منتصفه (وإلا أُعيد التناظر بصمت). اختبارات 20 و21 |
| طبقات حقيقية (P5) | لوحة `layer_list` (QListWidget) في الشريط الجانبي: **قفل** (`locked` — `_apply_layer_lock` يمنع التحديد)، **تسمية** (rename_layer)، **حذف** (delete_layer — الكائنات تنتقل للطبقة السابقة + إعادة ترقيم)، **سحب لإعادة الترتيب** (`_on_layers_reordered` — remap فهارس الحمولات)، **نقل كائنات للطبقة** (`move_selection_to_layer`)، **عداد كائنات** لكل طبقة في العنوان، Checkbox=إظهار؛ `_layers_updating` يمنع الحلقات؛ المخطط `{name,visible,locked?}` متوافق خلفياً |
| مكتبة أشكال (P5) | `SHAPE_LIBRARY` 12 شكلاً: مثلث قائم/متساوي، نجمة 5/6، قوس 90°، قطاع، **محاور+شبكة** (أسهم+خطوط 20px)، دائرة وحدة، متجه، أسطوانة/مخروط/صندوق 3D تخطيطية — `shape_payloads(kind,origin,size)` يبني payloads نقية؛ `open_shape_library` (زر 📐) حوار قائمة+حجم، إدراج بمركز العرض على الطبقة النشطة، الأسهم تُبنى رؤوسها بعد الإدراج |
| V-Pen Pro (P6) | **Rubber-Band حي**: `_vpen_rubber` (hover + أثناء سحب المقبض) — مقطع متقطع أخضر من آخر عقدة (بمقبض out الحي) إلى المؤشر (z=9200) + **دائرة دليل ⅓** (قاعدة الثلث) عند ثلث p0→المؤشر أثناء سحب المقبض؛ **Shift=45°** (وضع العقدة عبر `_vpen_place_point` **وقفل المقبض** داخل `_vpen_drag`)؛ **Backspace/Del** حذف آخر عقدة؛ **نقر مزدوج** إنهاء مفتوح؛ **Space أثناء السحب** = تحريك الارتكاز نفسه قبل تثبيته (`_vpen_space_hold` — phase "anchor" ثم عودة لـ "out" عند الإفلات، keyPressEvent/Release)؛ **Space بدون سحب** تبديل corner↔smooth؛ **Ctrl لحظيّاً** = Direct Selection أثناء الجلسة (`_vpen_quick_node` — سحب عقدة سابقة مباشرة)؛ **استكمال مسارات قائمة**: `_vpen_find_open_end` (نقر ≤10px/zoom على نهاية مسار مفتوح → يكمله؛ النقر على البداية يعكس المسار)؛ العقدة الجديدة ترث in=نصف out السابق (سلسلة ناعمة تلقائية)؛ **الدقة الرياضية**: B(t) Bernstein تكعيبية مطابقة تماماً في `_vp_point_on_seg` (مُثبت باختبار بفروق <1e-9)، smooth=C1 استمرارية (مقبضان collinear 180°)، cusp=Alt فك تناظر |
| مزامنة النقل (CRITICAL P4) | **نقل المستخدم الأصلي (السحب) كان لا يُخزّن في الحمولة — عيب قديم أصلي!** الحل: `sync_item_payload_pos` (تدمج pos في الحمولة + إعادة ربط rect/line + pos=0)؛ تُستدعى داخل `_payloads` و`copy_selection` عبر `sync_scene_payloads` (على `_item_refs` الحية فقط)؛ `_payloads` الجديد: يجمع من `_item_refs` الحية (تقليم الميتة بـ`it.scene() is self.scene`) + dedupe بـ`shiboken_key`(getCppPointer) + ترتيب zValue |

## 7) صيغة المستند .wbd
```json
{"app":"InteractiveWhiteboard","version":1,"theme":"dark","fg_color":"#..",
 "current_page":0,"layers":[{"name":"Layer 1","visible":true}],"current_layer":0,
 "pages":[{"bg_kind":"dots","bg_image":null,"objects":[payload,...]}]}
```
متوافقة عكسياً مع نسخة Tkinter (الأنواع غير المعروفة تُتجاهل هناك).

## 8) التبعيات والبناء
```
pillow arabic-reshaper python-bidi sympy numpy imageio imageio-ffmpeg
pymupdf reportlab PySide6 matplotlib
```
بناء exe (مُجرَّب):
```
pyinstaller --noconfirm --clean --windowed --onefile --name WhiteboardPro \
  --icon icon.ico --collect-data matplotlib --collect-data arabic_reshaper \
  --hidden-import matplotlib.textpath --hidden-import matplotlib.path \
  --hidden-import matplotlib.font_manager whiteboard_qt.py
```
النتيجة ~180MB. ملاحظات: أول استدعاء matplotlib يبني كاش خطوط (التطبيق يسخّنه بـQTimer.singleShot(200) عند الإقلاع).

**الطريقة المفضّلة الآن** (الـspec متتبَّع في git منذ `b46b3fb`):
```
pyinstaller WhiteboardPro.spec --noconfirm --clean     # ~5 د، الناتج dist/WhiteboardPro.exe ~207MB
```
⚠ لا تعتمد على سطر الأوامر اليدوي أعلاه إلا لو تغيّرت قائمة الـhidden-imports — الـspec هو المصدر الوحيد للحقيقة.
⚠ `.gitignore` فيه `*.spec` مع استثناءين (`!Whiteboard.spec` و`!WhiteboardPro.spec`) — أي spec جديد يحتاج استثناءً وإلا خرج من المستودع بصمت.

## 9) الاختبارات (كلها offscreen جاهزة)

### ⚠ أولاً: مجلد `%TEMP%\opencode` **يُمحى تلقائياً**
تنظيف Windows حذف **19 ملف اختبار** من هناك (2026-09-14)؛ لم ينجُ إلا ما
عُدِّل حديثاً. **لا تضع اختباراً يحرس ثابتة مهمّة في `%TEMP%`.** الاختبارات
الدائمة صارت في `tests/` داخل المستودع — انظر `tests/README.md`.

```
cd <جذر المشروع>
QT_QPA_PLATFORM=offscreen python tests/test_pen_tool.py      # 21 فحصاً (أداة القلم)
QT_QPA_PLATFORM=offscreen python tests/wb_penmath_test.py    #  7 فحوص
QT_QPA_PLATFORM=offscreen python tests/wb_penfix_test.py     #  5 فحوص
QT_QPA_PLATFORM=offscreen python test_nav_tools.py           # 37 فحصاً (التنقّل)
QT_QPA_PLATFORM=offscreen python _smoke_nav_integration.py   # فحص تكامل
```

### قائمة `%TEMP%\opencode` الأصلية (محذوفة — للمرجع فقط)
ما يلي كان موجوداً ويُستحسن إعادة كتابته في `tests/` عند الحاجة إليه:
```
wb_qt2_test.py  صفحات/طبقات/مكتبات/worksheet
wb_qt3_test.py  أدوات+ليزر+حبر متغير+ثيم
wb_clip_test.py wb_word_test.py   الحافظة والصيغ
wb_flat_test.py  wb_pdfin_test.py  wb_overlay_test.py  wb_unlock_test.py
wb_latex_test.py wb_group_test.py  wb_props_test.py
wb_rec_test.py   تسجيل REC → mp4 صالح (عدد إطارات + fps + أبعاد 1080 دقيقة)
wb_snap_test.py  SnapEngine (11 حالة: نقاط/زوايا/ortho/grid/alt/zoom/mؤشرات)
wb_ink_test.py   RDP+Catmull عبر أحداث view حقيقية + brush متزامن
wb_tbox_test.py  TransformBox (10 حالات: مقابض/uniform/حافة/دوران/تتبع/إخفاء)
wb_vpath_test.py V-Pen+NodeEdit (14 حالة: split bbox/roundtrip/SVG-c/bbox/إغلاق/asym/del/toggle/ink2path/old-files)
wb_color_test.py التلوين (12 حالة: norm/qbrush/عناصر/SVG-defs/roundtrip/resize-تدرج/dash-join-α/vpath-dash/swatches/dialog/توافق-خلفي)

wb_p4_test.py  التحرير (13 حالة: boolean×4/office-table/plain-text/text-edit/dblclick/align×2/distribute/gradient-boolean)
wb_p5_test.py  الطبقات+الأشكال (12 حالة: لوحة/عدادات/قفل/تسمية/نقل/إظهار/ترتيب-مبادلة/حذف/12-شكل/إدراج-حوار/roundtrip)
wb_pen2_test.py V-Pen Pro (10 حالات: rubber/45°/smooth-drag/space-toggle/backspace/dblclick/استكمال×2/rubber-أثناء-سحب/escape)
wb_penmath_test.py المواصفة الرياضية (6 حالات: B(t) مطابقة/C1/Shift-قفل-مقبض/Space-ارتكاز/Ctrl-مباشر/دليل-ثلث)
dbg_draw.py      رسم صناعي بـQMouseEvent (لأخطاء القلم)
```
اختبارا التنقّل — في **جذر المشروع** لا في `%TEMP%`:
```
cd <مجلد المشروع>
test_nav_tools.py         37 حالة: النموذج الرياضي (زوم/تمرير/دوران/fit/سلّم الزوم/cursors)
_smoke_nav_integration.py فحص تكامل: يبني MainWindow الحقيقي offscreen ويقود التنقّل
                          (يثبّت النقطة تحت المؤشر · ١:١ · Space · دوران · Fit/100% · القلم)
                          النتيجة الحالية: 37 ناجح / كل فحوص التكامل ناجحة
```
⚠ كلا الملفين يحتاج `QT_QPA_PLATFORM=offscreen` ولا يحتاج عرضاً حقيقياً.
**قاعدة**: أي تعديل → شغّل المتعلق بها + `wb_qt2` و`wb_qt3` كرجression.

## 10) فخاخ مكتسبة بالدم (CRITICAL — تجنبها)
1. **PySide `setData(0,dict)` ينسخ القاموس** — التعديل عبر data(0) يضيع. الحل الحالي: `_payload` attribute + `pl_of()`. لا ترجع لنظام data.
2. **QT_QPA_PLATFORM=offscreen يحوّل النص لمسارات** — اختبارات استخراج نص PDF يجب أن تعمل على المنصة الحقيقية.
3. **PowerShell 5.1 يفسد الترميز** (cp1252): Get/Set-Content بدون -Encoding دمّرا العربية/الإيموجي سابقاً. أي إعادة كتابة ملف = عبر Python بـ`open(...,encoding='utf-8')`. (وصفة إصلاح mojibake موجودة بسجل المحادثة).
4. **QPen ترتيب موضعي**: (brush,width, PenStyle, PenCapStyle, PenJoinStyle) — Cap قبل Style يكسر.
5. **QGraphicsItemGroup** يحتاج راية `ItemSendsGeometryChanges` ليصل ItemPositionChange.
6. **QPageSize(size, Unit, name)** بالترتيب؛ وQPdfWriter لا يملك paintRect → `pageLayout().paintRectPixels(resolution())`.
7. **Compass**: arc_a0 عند الضغط لا عند أول حركة (وإلا span=0).
8. **Instrument hit**: المقابض قبل contains (bounding أكبر من الشكل يخطف الضغط).
9. **محوّل النص العربي**: PIL/reportlab يحتاج `_shape_bidi_text` + كشف `_has_arabic` لكل سطر (RTL يمين، معادلات LTR يسار). Qt نصوصه سليمة native.
10. **legacy PDF writer**: `_write_worksheet_pdf` method → استدعِ عبر `type("_H",(),{"_worksheet_pdf_fonts":legacy.WhiteboardApp._worksheet_pdf_fonts})()`.
11. **Undo**: `push_undo()` قبل أي تعديل؛ العمليات الملغاة تستدعي `pop_undo()`.
12. **حبر Brush متغير**: تغيير السمك = نسبة من old_width (اقرأ القديم قبل الكتابة) + إعادة بناء `_var_stroke_path`.
13. **الملفات**: أي سكربت يلمس المصدر يجب أن يحافظ على UTF-8 بدون BOM.
14. **Shiboken wrapper GC**: عنصر QGraphics بلا مرجع Python يفقد `_payload` عند أول GC بعد موت الـ wrapper الأول (سلوك غير حتمي!). **كل إضافة عنصر عبر `MainWindow._add_item`** (يحفظ في `_item_refs`). اختباراتك أيضاً يجب أن تحفظ مراجع أو تستخدم `_add_item`.
15. **`QWheelEvent` في PySide6 6.11**: `pixelDelta` و`angleDelta` يجب أن تكون **`QPoint`** (أعداد صحيحة) لا `QPointF` — وإلا `TypeError: called with wrong argument types` ويُسقط الفحص كله.
16. **حوار نمطي يُجمّد الفحص الصامت**: `MainWindow.add_text_at()` يفتح `QInputDialog.getMultiLineText` — أي فحص offscreen يستدعيها يتوقف للأبد بلا رسالة. اكتمها: `QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("x", True))`.
17. **Space/M modifiers يجب تحريرها**: `nav.key_press` يضبط `nav._space=True`، وإن لم تُنادِ `nav.key_release` يبقى مفعّلاً فتبتلع `nav.press(e)` كل ضغطة يسرى لاحقة — والفحص يُبلّغ كذباً «لا رسم». نفس القاعدة لأي مفتاح مُعدِّل (Shift/Ctrl/Alt).
18. **عند الإنهاء**: `update_props_panel` و`_update_tbox` كانتا تلمسان `self.scene` بعد حذفه ⇒ `RuntimeError: Internal C++ object (QGraphicsScene) already deleted` في stderr (يحدث في الـexe المجمّد أيضاً). **أُصلح** بإضافة `scene_alive(scene)` (تستعمل `shiboken6.isValid`) كحارس في `update_props_panel` · `_update_tbox` · `_iter_sel_payload_items`. اختبار الحماية: الفحص 11.
19. **إشارة مقبض `in`** — أخطر عطل في المشروع حتى الآن: العقدة «الناعمة» كانت تُرسم كسراً بـ180° يلتفّ على نفسه. التفاصيل الكاملة والاصطلاح في §4. **لا تُعِد `anchor - in`.**
20. **`_vp_split_segment` لم يكن يكتب `B`**: كان يحسب `B["in"] = q2 - B.p` ثم **يُهمل الكتابة**، فيتغيّر شكل المنحنى عند كل إدراج عقدة. الإصلاح: `new_nodes[j] = B` **قبل** `insert(i+1, M)` (لأن الإدراج يزيح الفهارس). اختبار الحماية: الفحص 5 في `tests/test_pen_tool.py` (انحراف < 1e-9 على 41 عيّنة).
21. **`QGraphicsPathItem.path()` لا يعطي عيّنات متساوية العدد** بعد تعديل المسار: لا تقارن `toSubpathPolygons()` نقطة-بنقطة للتحقق من «حفظ الشكل». قارن **بارامترياً** عبر `_vp_point_on_seg` (كما في الفحص 5).
22. **`_qpath_to_vpath_nodes` كان يُسقط مقبض الدخول للعقدة الأولى في المسارات المغلقة**: العقدة الأخيرة في تدفّق Qt هي نفسها العقدة الأولى هندسياً وتحمل `in` للضلع الأخير، و`nodes.pop()` كان يرميها ⇒ دائرة ذهاب-وإياب تخرج **20 px** خارج الاستدارة. الإصلاح: انقل `closing["in"]` إلى `nodes[0]["in"]` قبل الحذف. اختبار الحماية: الفحص 10 (‎0.040 → 0.040‎).
23. **المستورد يُستعمل في عمليات Boolean فقط** (`_qpath_to_vpath_nodes` له مستدعٍ واحد عند سطر ~2528)، أما «Unlock to vector» فيُنتج `pen`/`polygon` لا `vpath`. لذلك تغيير اصطلاح المقابض لا يمسّ ملفات `.wbd` المحفوظة عبر القلم (بل **يُصلحها**)، لكنه يمسّ أي `vpath` نتج عن Boolean وحُفظ قبل 2026-09-14.
24. **الشريط الجانبي كان بلا تمرير** (`_build_sidebar`): ارتفاع محتواه ~1440px (17 زر أداة بارتفاع مثبّت 56px) و`QVBoxLayout` **يرفض التقلّص تحت ~1300** ⇒ الأب يقصّه بصمت، فلوحات **PROPERTIES · NODE X/Y · SWATCHES · Shape Library غير قابلة للوصول** على أي نافذة أقصر من ~1450px. **أُصلح** بلفّه في `QScrollArea` (`objectName="sidebarScroll"`) + إزالة `side.setFixedWidth`. اختبار الحماية: الفحص 19.
25. **أحداث الفأرة مُكمَّمة**: `QMouseEvent` يحمل بكسلات نافذة صحيحة و`mapToScene` يكمّمها ⇒ أي اختبار يقارن نقطة مشهد «اسمية» قد ينجح أو يفشل حسب عرض النافذة. قارن دائماً بالنقطة المرتدّة `mapToScene(mapFromScene(p))` (انظر `scene_pt()` في `tests/test_pen_tool.py`).
26. **معاينة القلم كانت تكذب**: `_vpen_rubber` كان يجمع `last["in"]` في نقطة التحكّم الواصلة، لكن `in` تخصّ **الضلع السابق** لا الضلع المعروض. النتيجة: معاينة تُظهر منحنى بينما النقرة تُنتج **خطاً مستقيماً** (لأن النقرة تُنشئ عقدة زاوية بلا مقابض). الصحيح `c2 = end` مباشرة. اختبار الحماية: الفحص 22 (يقارن عناصر مسار المعاينة بالمقطع المُنشأ فعلاً).

## 11) الحالة الحالية والفجوات
- Git: main، ~27 commit، رسائل نمط "Phase/feat: ...". الريموت: `github.com/ouannoughidjamel10-png/whiteboard-pro`.
- يعمل: كل ما في القسم 6 + REC + **طبقة التنقّل `nav_tools`** (Hand/Zoom/Rotate/Navigator/Space) + **أداة القلم بمستوى احترافي** (عُقد ناعمة صحيحة، إغلاق مرئي، إدراج/حذف عقدة على مسار قائم، تحويل نوع العقدة، قفل 45°، مقابض عند المرور، **كسر المقبض بـAlt ⇒ إكمال بخط مستقيم**) + **انعكاس ⇋⇵** (المفرد/المجموعات/النص) + **طبقة دقّة** (مؤشّر X/Y حيّ + طول/زاوية + إدخال رقمي للعقدة) + **أداة Curve ◠** (تحويل مستقيم إلى منحنى بالسحب).
- **فجوات معروفة**: Unlock لا يطابق خطوط الـPDF الأصلية · لا تراخيص · لا مزامنة سحابية · MSIX غير جاهز · group children تبقى flags مغلقة حتى ungroup · أداة القلم لا تُدرج عقدة على مسار **أداة القلم الحالية أثناء جلسة رسم** (فقط على مسارات منتهية) · المؤشّر الحيّ لا يعرض إحداثيات لأدوات الرسم الحر (pen/highlighter) عمداً (تفادي الفوضى) · أداة Curve لا تعمل إلا على `vpath` (لا على `pen` الحر — استعمل Ink→Path أولاً).
- نمط التطوير المتبع: ميزة → اختبار دخان offscreen → إصلاح → رجرession qt2+qt3 → commit → PyInstaller → إطلاق للمستخدم.

### درسان مدفوعان الثمن (2026-09-13)
1. **المستودع قد يكون مكسوراً وهو يعمل عندك.** كان `whiteboard_qt.py` المُلتزَم يستورد `nav_tools`، و`nav_tools.py` **غير مُضاف إلى git** (وكذلك `WhiteboardPro.spec` بسبب `*.spec` في `.gitignore`). كل شيء يعمل محلياً، لكن أي `git clone` يفشل عند الاستيراد. **القاعدة: بعد كل ميزة، شغّل `git status` وتأكّد أن كل ملف يستورده الكود المُلتزَم مُضاف فعلاً** — والإثبات النهائي: `git clone` في مجلد مؤقت ثم `import whiteboard_qt` + تشغيل `test_nav_tools.py`.
2. **لا تختبر exe أقدم من الكود.** قارن دائماً تاريخ `dist/WhiteboardPro.exe` بتاريخ `whiteboard_qt.py`. البناء بالـspec المتتبَّع: `pyinstaller WhiteboardPro.spec --noconfirm --clean` (~5 د).

## 12) طلبات المستخدم الدائمة
يريد: مستوى احترافي بصرياً (معايير Illustrator/المتنافس)، دقة رياضية مضمونة، دعم عربي كامل، وأي ميزة جديدة تُختبر قبل التسليم. يفضل الردود العربية المختصرة مع جداول، والتنفيذ الفوري بعد موافقته ("ابدأ/اكمل/نعم").
