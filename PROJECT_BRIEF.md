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
| `icon.ico`, `Whiteboard.spec`, `WhiteboardPro.spec` | بناء |
| `README.md` | وصف تسويقي/مستخدم |
| الاختبارات | `%TEMP%\opencode\wb_*.py` (قائمة أدناه) |

## 3) البنية المعمارية (Qt)
- `MainWindow(QMainWindow)`: يملك `QGraphicsScene(-100k..200k)` و `BoardView`.
- `BoardView(QGraphicsView)`: زوم بالعجلة عند المؤشر (1/20..40x)، pan بالزر الأوسط، وكل منطق الضغط/السحب/الإفلات حسب `win.tool`.
- ترتيب معالجة mousePressEvent: pan(أوسط) → latex(فتح حوار) → laser → instrument_press → snap_pen → select(سوبر) → زر أيسر → eraser → pen/highlighter → shapes.
- العناصر = عناصر Qt حقيقية (QGraphicsPathItem/Line/Rect/Ellipse/TextItem/PixmapItem) — **لا إعادة رسم كاملة**؛ GPU يكفي حتى آلاف الكائنات.

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
```
- `translate_payload(pl,dx,dy)` يترجم كل الأنواع (تستخدمها المجموعات).
- `payload_to_item(pl)` يبني العنصر ويضبط `_payload=deepcopy(pl)` + flags(Selectable|Movable).
- `_payloads()` يجمّع من المشهد (مع تفكيك المجموعات إلى {type:group,items} وتخطي الأبناء).

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
| Chalkboard | `toggle_theme` → `win.dark` يغير drawBackground |

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

## 9) الاختبارات (كلها offscreen جاهزة)
```
$env:QT_QPA_PLATFORM="offscreen"; python %TEMP%\opencode\<file>
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
dbg_draw.py      رسم صناعي بـQMouseEvent (لأخطاء القلم)
```
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

## 11) الحالة الحالية والفجوات
- Git: main، ~25 commit، رسائل نمط "Phase/feat: ...".
- يعمل: كل ما في القسم 6 + REC.
- **فجوات معروفة**: Unlock لا يطابق خطوط الـPDF الأصلية · لا تراخيص · لا مزامنة سحابية · MSIX غير جاهز · group children تبقى flags مغلقة حتى ungroup.
- نمط التطوير المتبع: ميزة → اختبار دخان offscreen → إصلاح → رجرession qt2+qt3 → commit → PyInstaller → إطلاق للمستخدم.

## 12) طلبات المستخدم الدائمة
يريد: مستوى احترافي بصرياً (معايير Illustrator/المتنافس)، دقة رياضية مضمونة، دعم عربي كامل، وأي ميزة جديدة تُختبر قبل التسليم. يفضل الردود العربية المختصرة مع جداول، والتنفيذ الفوري بعد موافقته ("ابدأ/اكمل/نعم").
