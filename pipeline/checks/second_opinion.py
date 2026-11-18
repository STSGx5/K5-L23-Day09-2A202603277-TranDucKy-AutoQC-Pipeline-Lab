"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
"""CHECK 6 — Ý kiến thứ hai: so nhãn với model lớn hơn (yolo26l). Chỉ CẢNH BÁO.

Test:  pytest tests/test_second_opinion.py -q
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

TEN_CHECK = "second_opinion"


def run(ds, cfg, preds=None):
    """So từng ảnh với dự đoán của model; trả về list[Issue] (toàn bộ severity WARN)."""
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    cau_hinh = cfg["second_opinion"]
    conf_toi_thieu = cau_hinh["conf"]
    dien_tich_toi_thieu_px = cau_hinh["min_area_px"]
    conf_cho_false_pos = cau_hinh["fp_conf"]
    iou_thieu_nhan = cau_hinh["iou_missing"]
    iou_cung_vat = cau_hinh["iou_match"]
    iou_box_long = cau_hinh["iou_loose"]
    so_lop = len(ds.classes)

    danh_sach_loi = []

    for duong_dan_anh in ds.image_files():
        ten_anh = duong_dan_anh.stem
        if ten_anh not in preds:
            continue
        cac_dong_nhan = ds.read_label_lines(ten_anh)
        if cac_dong_nhan is None:                 # chưa có file nhãn: việc của autofix/needs_label
            continue
        kich_thuoc = ds.image_size(ten_anh)
        if kich_thuoc is None:
            continue
        rong_anh_px, cao_anh_px = kich_thuoc

        # Nhãn hợp lệ kèm số dòng gốc: [(số dòng, id_lớp, (cx, cy, w, h))]
        cac_nhan = []
        for so_dong, noi_dung in cac_dong_nhan:
            try:
                id_lop, tam_x, tam_y, rong, cao = parse_yolo_line(noi_dung)
            except ValueError:
                continue
            if 0 <= id_lop < so_lop:
                cac_nhan.append((so_dong, id_lop, (tam_x, tam_y, rong, cao)))

        cac_du_doan = preds[ten_anh]

        # A) Duyệt dự đoán đáng tin: tìm MISSING / LOOSE_BOX / WRONG_CLASS
        for du_doan in cac_du_doan:
            id_lop_model, conf, tam_x, tam_y, rong, cao = du_doan
            if conf < conf_toi_thieu or (rong * rong_anh_px) * (cao * cao_anh_px) < dien_tich_toi_thieu_px:
                continue
            box_model = (tam_x, tam_y, rong, cao)

            # Các nhãn chồng lên vật này: [(iou, id_lớp_nhãn)]
            ung_vien = []
            for _, id_lop_nhan, box_nhan in cac_nhan:
                iou = iou_xywh(box_model, box_nhan)
                if iou >= iou_thieu_nhan:
                    ung_vien.append((iou, id_lop_nhan))

            if not ung_vien:
                danh_sach_loi.append(Issue(TEN_CHECK, WARN, "POSSIBLE_MISSING", ten_anh,
                                           f"model thấy lớp {id_lop_model} (conf {conf:.2f}) nhưng nhãn không có box nào ở đó",
                                           None, {"conf": conf}))
                continue

            iou_tot_nhat_cung_lop = max((i for i, c in ung_vien if c == id_lop_model), default=None)
            iou_tot_nhat_khac_lop = max((i for i, c in ung_vien if c != id_lop_model), default=None)

            if iou_tot_nhat_cung_lop is not None:
                if iou_tot_nhat_cung_lop < iou_box_long:
                    danh_sach_loi.append(Issue(TEN_CHECK, WARN, "POSSIBLE_LOOSE_BOX", ten_anh,
                                               f"box đúng lớp nhưng lỏng/lệch (IoU {iou_tot_nhat_cung_lop:.2f})",
                                               None, {"conf": conf, "iou": round(iou_tot_nhat_cung_lop, 4)}))
            elif iou_tot_nhat_khac_lop is not None and iou_tot_nhat_khac_lop >= iou_cung_vat:
                danh_sach_loi.append(Issue(TEN_CHECK, WARN, "POSSIBLE_WRONG_CLASS", ten_anh,
                                           f"model nói lớp {id_lop_model}, nhãn gán lớp khác (IoU {iou_tot_nhat_khac_lop:.2f})",
                                           None, {"conf": conf, "iou": round(iou_tot_nhat_khac_lop, 4)}))

        # B) Duyệt nhãn: box không khớp dự đoán nào (không lọc diện tích) => POSSIBLE_FALSE_POS
        box_du_doan_de_doi_chieu = [(d[2], d[3], d[4], d[5]) for d in cac_du_doan if d[1] >= conf_cho_false_pos]
        for so_dong, id_lop_nhan, box_nhan in cac_nhan:
            if all(iou_xywh(box_nhan, bm) < iou_thieu_nhan for bm in box_du_doan_de_doi_chieu):
                danh_sach_loi.append(Issue(TEN_CHECK, WARN, "POSSIBLE_FALSE_POS", ten_anh,
                                           "box nhãn không khớp vật nào model nhìn thấy",
                                           so_dong, {"conf": conf_cho_false_pos}))

    return danh_sach_loi

