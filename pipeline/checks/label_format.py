"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.

Test:  pytest tests/test_label_format.py -q
(Phần docstring mô tả chi tiết của đề đã được rút gọn; bảng mã lỗi xem trong đề gốc.)
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line

TEN_CHECK = "label_format"


def run(ds, cfg):
    """Duyệt mọi file nhãn trong `ds`, trả về danh sách Issue."""
    danh_sach_loi = []

    # Ngưỡng lấy từ cấu hình, KHÔNG viết cứng số vào code
    cau_hinh = cfg["label_format"]
    nguong_tran_anh = cau_hinh["overflow_tol"]
    canh_ngan_toi_thieu_px = cau_hinh["min_box_px"]
    ti_le_dien_tich_toi_da = cau_hinh["max_box_frac"]
    iou_toi_da_de_coi_la_lap = cau_hinh["dup_box_iou"]
    so_lop = len(ds.classes)

    for duong_dan_file_nhan in ds.label_files():
        ten_anh = duong_dan_file_nhan.stem                       # tên không đuôi
        cac_dong = ds.read_label_lines(ten_anh) or []            # [(số dòng gốc, nội dung)], đã bỏ dòng trống
        kich_thuoc_anh = ds.image_size(ten_anh)                  # (rộng, cao) px hoặc None nếu ảnh hỏng

        # Các box hợp lệ ở những dòng TRƯỚC, dùng để phát hiện DUP_BOX: (id_lớp, (cx, cy, w, h))
        cac_box_da_gap = []

        for so_dong, noi_dung_dong in cac_dong:

            def them_loi(muc_do, ma_loi, thong_diep, **thong_tin_them):
                danh_sach_loi.append(Issue(TEN_CHECK, muc_do, ma_loi, ten_anh, thong_diep, so_dong, thong_tin_them))

            # 1) Sai định dạng: không đủ 5 cột số -> bỏ qua dòng này
            try:
                id_lop, tam_x, tam_y, rong, cao = parse_yolo_line(noi_dung_dong)
            except ValueError as loi:
                them_loi(ERROR, "BAD_FORMAT", f"dòng nhãn sai định dạng: {loi}")
                continue

            # 2) ID lớp ngoài khoảng 0..so_lop-1
            if not (0 <= id_lop < so_lop):
                them_loi(ERROR, "BAD_CLASS_ID", f"id lớp {id_lop} ngoài khoảng 0..{so_lop - 1}")
                continue

            # 3) Box rỗng (rộng hoặc cao <= 0)
            if rong <= 0 or cao <= 0:
                them_loi(ERROR, "BOX_ZERO", f"box có kích thước không dương (w={rong}, h={cao})")
                continue

            box_hien_tai = (tam_x, tam_y, rong, cao)

            # 4) Box tràn ảnh: tính mức tràn ở cả 4 mép
            mep_trai = tam_x - rong / 2
            mep_phai = tam_x + rong / 2
            mep_tren = tam_y - cao / 2
            mep_duoi = tam_y + cao / 2
            muc_tran_lon_nhat = max(-mep_trai, mep_phai - 1.0, -mep_tren, mep_duoi - 1.0)
            if muc_tran_lon_nhat > nguong_tran_anh:
                them_loi(ERROR, "BOX_OUT_OF_IMAGE",
                         f"box tràn ra ngoài ảnh {muc_tran_lon_nhat:.4f}",
                         overflow=round(muc_tran_lon_nhat, 6))

            # 5) Box lặp: cùng lớp với một dòng TRƯỚC và IoU cao -> báo ở dòng SAU
            for id_lop_truoc, box_truoc in cac_box_da_gap:
                if id_lop_truoc == id_lop and iou_xywh(box_truoc, box_hien_tai) > iou_toi_da_de_coi_la_lap:
                    them_loi(ERROR, "DUP_BOX", "box trùng với một dòng phía trên (cùng lớp, IoU cao)")
                    break

            # 6) Cảnh báo box quá nhỏ (cạnh ngắn tính bằng pixel)
            if kich_thuoc_anh is not None:
                rong_anh_px, cao_anh_px = kich_thuoc_anh
                canh_ngan_px = min(rong * rong_anh_px, cao * cao_anh_px)
                if canh_ngan_px < canh_ngan_toi_thieu_px:
                    them_loi(WARN, "BOX_TINY", f"cạnh ngắn của box chỉ {canh_ngan_px:.1f}px")

            # 7) Cảnh báo box quá to
            if rong * cao > ti_le_dien_tich_toi_da:
                them_loi(WARN, "BOX_HUGE", f"box chiếm {rong * cao:.2f} diện tích ảnh")

            cac_box_da_gap.append((id_lop, box_hien_tai))

    return danh_sach_loi
