"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.

Test:  pytest tests/test_autofix.py -q
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

MA_LOI_XOA_DONG = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
MA_LOI_XOA_ANH = {"CORRUPT_IMAGE", "BAD_SIZE", "LEAK_TEST"}   # DUP_IMAGE_* xử lý bằng startswith


def _ghi_nhan(ten_anh, so_dong, hanh_dong, truoc, sau):
    return {"image": ten_anh, "line": so_dong, "action": hanh_dong, "before": truoc, "after": sau}


def _can_xoa_anh(ma_loi):
    return ma_loi in MA_LOI_XOA_ANH or ma_loi.startswith("DUP_IMAGE")


def _cat_box_vao_trong_anh(tam_x, tam_y, rong, cao):
    """Cắt box về trong [0,1]. Trả về (cx, cy, w, h) mới, hoặc None nếu box nằm hẳn ngoài ảnh."""
    trai, phai = max(0.0, tam_x - rong / 2), min(1.0, tam_x + rong / 2)
    tren, duoi = max(0.0, tam_y - cao / 2), min(1.0, tam_y + cao / 2)
    rong_moi, cao_moi = phai - trai, duoi - tren
    if rong_moi <= 1e-9 or cao_moi <= 1e-9:
        return None
    return (trai + phai) / 2, (tren + duoi) / 2, rong_moi, cao_moi


def fix(ds, issues, cfg):
    """Sửa trực tiếp vào `ds`, trả về list thay đổi (image, line, action, before, after)."""
    nhat_ky = []
    loi_bat_buoc = [loi for loi in issues if loi.severity == ERROR]

    # --- 1) Xoá ảnh (+ nhãn) trước tiên; các lỗi khác của ảnh đó sẽ bị bỏ qua
    tap_anh_da_xoa = set()
    for loi in loi_bat_buoc:
        if _can_xoa_anh(loi.code) and loi.image not in tap_anh_da_xoa:
            tap_anh_da_xoa.add(loi.image)
            duong_dan_anh = ds.image_path(loi.image)
            duong_dan_nhan = ds.label_path(loi.image)
            ten_file = duong_dan_anh.name if duong_dan_anh else loi.image
            if duong_dan_anh and duong_dan_anh.exists():
                duong_dan_anh.unlink()
            if duong_dan_nhan.exists():
                duong_dan_nhan.unlink()
            nhat_ky.append(_ghi_nhan(loi.image, "", "remove_image", ten_file, f"(đã xoá, lý do {loi.code})"))

    # --- 2) Gom lỗi theo dòng của từng file nhãn: {ảnh: {số dòng gốc: {mã lỗi}}}
    loi_theo_dong = defaultdict(lambda: defaultdict(set))
    for loi in loi_bat_buoc:
        if loi.image in tap_anh_da_xoa or loi.line is None:
            continue
        if loi.code in MA_LOI_XOA_DONG or loi.code == "BOX_OUT_OF_IMAGE":
            loi_theo_dong[loi.image][loi.line].add(loi.code)

    # --- 3) Mỗi file nhãn chỉ đọc và ghi MỘT lần để số dòng gốc không bị lệch
    for ten_anh, cac_dong_loi in loi_theo_dong.items():
        duong_dan_nhan = ds.label_path(ten_anh)
        if not duong_dan_nhan.exists():
            continue
        # splitlines giữ cả dòng trống => chỉ số i tương ứng số dòng gốc i+1
        tat_ca_dong = duong_dan_nhan.read_text(encoding="utf-8", errors="replace").splitlines()
        dong_moi = list(tat_ca_dong)
        chi_so_can_xoa = set()
        thay_doi_file = False

        for so_dong in sorted(cac_dong_loi):
            if not (1 <= so_dong <= len(tat_ca_dong)):
                continue
            noi_dung_cu = tat_ca_dong[so_dong - 1]
            ma_loi_cua_dong = cac_dong_loi[so_dong]

            if ma_loi_cua_dong & MA_LOI_XOA_DONG:             # xoá thắng cắt
                chi_so_can_xoa.add(so_dong - 1)
                nhat_ky.append(_ghi_nhan(ten_anh, so_dong, "drop_line", noi_dung_cu, "(đã xoá dòng)"))
                continue

            try:
                id_lop, tam_x, tam_y, rong, cao = parse_yolo_line(noi_dung_cu)
            except ValueError:
                continue
            box_moi = _cat_box_vao_trong_anh(tam_x, tam_y, rong, cao)
            if box_moi is None:                                # nằm hẳn ngoài ảnh -> xoá dòng
                chi_so_can_xoa.add(so_dong - 1)
                nhat_ky.append(_ghi_nhan(ten_anh, so_dong, "drop_line", noi_dung_cu, "(box nằm ngoài ảnh, đã xoá dòng)"))
            else:
                noi_dung_moi = f"{id_lop} " + " ".join(f"{v:.6f}" for v in box_moi)
                dong_moi[so_dong - 1] = noi_dung_moi
                nhat_ky.append(_ghi_nhan(ten_anh, so_dong, "clip_box", noi_dung_cu, noi_dung_moi))
            thay_doi_file = True

        if chi_so_can_xoa or thay_doi_file:
            giu_lai = [d for i, d in enumerate(dong_moi) if i not in chi_so_can_xoa]
            duong_dan_nhan.write_text("".join(d + "\n" for d in giu_lai), encoding="utf-8")

    # --- 4) Ảnh thiếu file nhãn: KHÔNG bịa nhãn, chỉ ghi lại để chuyển cho người
    da_ghi_thieu_nhan = set()
    for loi in loi_bat_buoc:
        if loi.code == "MISSING_LABEL_FILE" and loi.image not in tap_anh_da_xoa and loi.image not in da_ghi_thieu_nhan:
            da_ghi_thieu_nhan.add(loi.image)
            nhat_ky.append(_ghi_nhan(loi.image, "", "needs_label", "(không có file)", "chuyển người gán"))

    # --- 5) Tên lớp trong data.yaml sai -> ghi lại đúng cfg["classes"]
    if any(loi.code == "BAD_CLASS_NAME" for loi in loi_bat_buoc) and ds.yaml_path.exists():
        noi_dung_yaml = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        ten_lop_cu = noi_dung_yaml.get("names")
        ten_lop_dung = list(cfg["classes"])
        noi_dung_yaml["names"] = ten_lop_dung if isinstance(ten_lop_cu, list) else dict(enumerate(ten_lop_dung))
        ds.yaml_path.write_text(yaml.safe_dump(noi_dung_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")
        nhat_ky.append(_ghi_nhan("data.yaml", "", "rename_classes", str(ten_lop_cu), str(ten_lop_dung)))

    return nhat_ky

