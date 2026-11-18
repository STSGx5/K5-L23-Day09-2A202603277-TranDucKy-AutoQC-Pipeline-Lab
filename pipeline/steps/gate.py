"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.

Test:  pytest tests/test_gate.py -q
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    """Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio, reasons."""
    nguong_hold = cfg["gate"]["warn_ratio_hold"]
    tap_ten_anh = set(image_stems)
    tong_so_anh = len(tap_ten_anh)

    # Lỗi bắt buộc: đếm tất cả, KHÔNG bỏ qua dù ảnh đã được người duyệt
    so_loi_bat_buoc = sum(1 for loi in issues if loi.severity == ERROR)

    # Ảnh còn cảnh báo = ảnh nằm trong lô, chưa được duyệt, có >= 1 cảnh báo
    tap_anh_con_canh_bao = {
        loi.image
        for loi in issues
        if loi.severity == WARN and loi.image in tap_ten_anh and loi.image not in reviewed
    }
    so_anh_con_canh_bao = len(tap_anh_con_canh_bao)
    ti_le_canh_bao = round(so_anh_con_canh_bao / tong_so_anh, 4) if tong_so_anh else 0

    ly_do = []
    if so_loi_bat_buoc >= 1:
        quyet_dinh = "Rework"
        ly_do.append(f"Còn {so_loi_bat_buoc} lỗi bắt buộc chưa sửa được -> Rework.")
    elif tong_so_anh and so_anh_con_canh_bao / tong_so_anh >= nguong_hold - 1e-9:
        quyet_dinh = "Hold"
        ly_do.append(
            f"Không còn lỗi bắt buộc, nhưng {so_anh_con_canh_bao}/{tong_so_anh} ảnh "
            f"({ti_le_canh_bao:.2%}) còn cảnh báo chưa được duyệt, >= ngưỡng {nguong_hold:.0%} -> Hold."
        )
    else:
        quyet_dinh = "Release"
        ly_do.append(
            f"Không còn lỗi bắt buộc; {so_anh_con_canh_bao}/{tong_so_anh} ảnh "
            f"({ti_le_canh_bao:.2%}) còn cảnh báo, < ngưỡng {nguong_hold:.0%} -> Release."
        )

    return {
        "decision": quyet_dinh,
        "n_errors": so_loi_bat_buoc,
        "n_warn_images": so_anh_con_canh_bao,
        "n_images": tong_so_anh,
        "warn_ratio": ti_le_canh_bao,
        "reasons": ly_do,
    }

