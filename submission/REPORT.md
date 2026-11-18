# Báo cáo Day 09 — Trần Đức Kỳ, 2A202603277

## 1. Kết luận trước
Pipeline kết luận **Hold** (`08_summary.json`: `n_errors = 0`, `n_warn_images = 38`, `n_images = 202`, `warn_ratio = 0.1881`).

- **Vào / ra:** 224 ảnh raw → cửa vào nhận **202**, loại **22** (ảnh trùng từng byte, rò rỉ từ kho test, trùng gần đúng, ảnh hỏng/quá nhỏ). Dataset nháp xuất ra `submission/export/clean_v1` gồm 202 ảnh (bản **nháp**, chưa được phát hành vì Hold).
- **Lý do:** không còn lỗi bắt buộc, nhưng **38/202 ảnh (18,81%)** còn cảnh báo chưa qua mắt người, vượt ngưỡng 10%. Hàng đợi duyệt có 125 ảnh nhưng ngân sách chỉ 80 ảnh (đã duyệt đủ 80/80), nên 38 ảnh còn lại vẫn tính vào tỉ lệ cảnh báo.

## 2. Lỗi và phân việc
Số liệu lấy từ `01_intake.csv`, `03_fixes.csv` và `07_error_list_v3.txt`.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT` | 8 ảnh | máy (`remove_image`) | trùng từng byte, quy tắc rõ ràng, an toàn khi xoá |
| `LEAK_TEST` | 5 ảnh | máy (`remove_image`) | trùng ảnh kho test/val, giữ lại sẽ làm hỏng phép đo cuối |
| `DUP_IMAGE_NEAR` | 4 ảnh | máy (`remove_image`) | phash ≤ 10 (đã mở xem 2 cặp khó, xem mục 3) |
| Lỗi dòng nhãn (`BAD_FORMAT`, `BAD_CLASS_ID`, `BOX_ZERO`, `DUP_BOX`, `BOX_OUT_OF_IMAGE`), `BAD_CLASS_NAME` | vòng 1 có 36 lỗi bắt buộc; autofix ghi 35 thay đổi, còn 6 lỗi sau vòng 2 | máy (xoá dòng / cắt box / ghi lại `names`) | sửa theo quy tắc, ghi log trước → sau trong `03_fixes.csv` |
| `MISSING_LABEL_FILE` | xem `03_fixes.csv` (action `needs_label`) | **người** | máy không bịa nhãn; tạo file rỗng sẽ nhầm thành "ảnh nền" |
| Cảnh báo ngữ nghĩa còn lại sau người duyệt (v3) | 38 ảnh: `POSSIBLE_FALSE_POS` 21, `POSSIBLE_LOOSE_BOX` 20, `POSSIBLE_MISSING` 13, `POSSIBLE_WRONG_CLASS` 3, `BOX_TINY` 7, `EMPTY_LABEL` 4, `BOX_HUGE` 3 (đếm theo dòng cảnh báo) | **người** | máy chỉ có "ý kiến thứ hai", model lớn cũng có thể sai |

Hàng đợi `05_review_queue.csv` xếp ảnh theo tổng trọng số của cảnh báo (`review.weights` trong cấu hình): `NEEDS_LABEL` (10) đứng đầu, rồi `POSSIBLE_WRONG_CLASS` (3), `POSSIBLE_MISSING` và `POSSIBLE_FALSE_POS` (2), `FIXED_DROP_LINE` (2)… và cuối cùng là `BOX_TINY`, `DENSE_IMAGE` (0,3). Ảnh nghiêm trọng nhất được xem trước. Với ngân sách 80 trên 125 ảnh trong hàng đợi, người duyệt xem được 64% hàng đợi; 45 ảnh cuối hàng đợi (ưu tiên thấp) không được xem, và sau duyệt còn 38 ảnh có cảnh báo.

## 3. Calibration (2 ngưỡng)
Nguồn: `submission/calibration/calibration_report.md` (bộ calib 39 ảnh có đáp án lỗi).

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **10** | `DUP_IMAGE_NEAR`: 1,00 / 0,50 → 1,00 / 0,67; `DUP_IMAGE_EXACT` giữ 1,00 / 1,00 | F1 đi ngang từ 4 đến 14, chọn giữa vùng phẳng. Ngưỡng 20 làm recall ảnh trùng y hệt tụt xuống 0,33 nên không dám chọn gần mép |
| `second_opinion.conf` | 0.25 | **0.6** | `WRONG_CLASS` 0,56 / 0,83 → 0,62 / 0,83; `MISSING` 0,50 / 1,00 → 0,57 / 1,00; `LOOSE_BOX` 0,29 / 0,40 → 0,20 / 0,20 | giữ recall `MISSING` = 1,00 (lớp có trọng số cao). Đánh đổi: `LOOSE_BOX` tệ đi (recall 0,40 → 0,20). Ngưỡng 0,8 cho `WRONG_CLASS` precision 1,00 nhưng `MISSING` recall tụt còn 0,75 |

Hiệu quả trên lô raw: cảnh báo vòng 1 giảm từ 273 xuống 153, hàng đợi từ 145 xuống 125 ảnh, ảnh còn cảnh báo sau duyệt từ 29,27% xuống 18,81% (vẫn Hold).

**Một chỗ calibration có thể đánh lừa:** bộ calib chỉ có 39 ảnh và chỉ 6 ảnh trùng gần đúng được chèn vào, nên ngưỡng `phash_dist = 16` cho F1 cao nhất (0,91) chỉ nhờ hơn đúng 1 ảnh, và nằm sát mép (20 thì hỏng). Mình chọn 10 rồi kiểm trên dữ liệu thật: `01_intake.csv` có 4 ảnh `DUP_IMAGE_NEAR`. Hai ca khó, mình đã mở xem bằng mắt:
- `img_0186` ↔ `img_0061` (phash 10): `img_0061` là bản **bị cắt** của `img_0186`;
- `img_0223` ↔ `img_0077` (phash 6): `img_0223` là bản **thu nhỏ** của `img_0077`.

Cả hai đúng là ảnh trùng; ngưỡng khởi đầu 2 sẽ bỏ sót cả hai (hai ca còn lại phash = 0). Hạn chế: mình chỉ kiểm các ảnh đã bị loại, chưa biết còn ảnh trùng nào ở khoảng cách lớn hơn mà ngưỡng 10 vẫn bỏ sót.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb (không có người duyệt): sau autofix vòng 2 còn 6 lỗi bắt buộc, người duyệt không xử lý được ảnh nào nên các lỗi này còn nguyên, gate kết luận Rework (“Còn 6 lỗi bắt buộc chưa sửa được”), mã thoát 20, và pipeline không xuất dataset. Các thư mục work/rep_nb và work/exp_nb chỉ là kết quả thử nghiệm, không nộp. Với lần chạy chính (ngân sách 80 ảnh), người duyệt xử lý hết 6 lỗi này (vòng 3 không còn lỗi bắt buộc), nên gate cho Hold (mã thoát 10) vì còn 18,81% ảnh cảnh báo ≥ 10%.

**(b) Điểm mù, có bằng chứng:**
1. **Box lỏng nhẹ bị bỏ sót nhiều.** Calibration cho `POSSIBLE_LOOSE_BOX` recall chỉ 0,40 (ở conf 0,25) và 0,20 (ở conf 0,6): trong 5 box lỏng được chèn, bỏ sót 3–4 box. Ngược lại cờ này cũng nhiễu (precision 0,20–0,29): trong v3 còn 20 cảnh báo box lỏng với IoU 0,30–0,49, người duyệt chưa chắc xem hết.
2. **Cờ `POSSIBLE_FALSE_POS` nhiễu.** Calibration: precision 0,31 (5 đúng, 11 sai) và không đổi theo `conf` vì dùng `fp_conf` cố định. 21 cảnh báo loại này trong v3 phần lớn có thể là nhãn đúng mà model không thấy; máy không tự phân biệt được.
3. **Ảnh trùng biến đổi mạnh.** `DUP_IMAGE_NEAR` recall chỉ 0,67 trên calib (precision 1,00): vẫn có ảnh trùng bị cắt/thu nhỏ mạnh không bị bắt. Ví dụ ngay trong lô này `img_0061` là bản cắt, chỉ bắt được vì phash đúng 10.
4. **Phụ thuộc vào model lớn.** 11/13 cảnh báo `POSSIBLE_MISSING` trong v3 là lớp 1 (person); nếu guideline dự án không gán vật nhỏ/xa thì phần lớn là cờ giả, nếu có thì là thiếu nhãn thật; model không trả lời được câu hỏi này, chỉ người đọc guideline mới trả lời.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Cấu hình: `yolo26n.pt`, 20 epoch, `imgsz` 640, batch 16, GPU T4 trên Colab, 2 seed (0 và 1); val = `data/gold_val` (40 ảnh), test = `data/test` (100 ảnh); mỗi lần train khoảng 90–130 giây. Dữ liệu `clean` là bản **nháp** (pipeline kết luận Hold, `manifest.json` ghi rõ). Số liệu lấy từ `submission/results/comparison.md` và các file `*_seed*.json`.

| biến thể | #ảnh đưa vào | số seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) | precision | recall |
|---|---:|---:|---|---|---|---|
| raw | 224 | 2 | 0,726 ± 0,000 | 0,512 ± 0,004 | 0,764 ± 0,061 | 0,649 ± 0,028 |
| clean | 202 | 2 | 0,701 ± 0,025 | 0,487 ± 0,008 | 0,759 ± 0,003 | 0,625 ± 0,019 |

Từng seed (mAP50): raw 0,7256 và 0,7259; clean 0,7180 và 0,6832. AP50 theo lớp (trung bình 2 seed): car 0,738 (raw) / 0,738 (clean); person 0,822 / 0,823; bus 0,695 / 0,703; **truck 0,648 / 0,538**.

**Kết luận (trung thực): chưa kết luận được là `clean` tốt hơn `raw`; số liệu còn nghiêng nhẹ về `raw`.**
- Chênh mAP50 (clean − raw) = **−0,025**, tức clean thấp hơn. Chênh này xấp xỉ 1 độ lệch chuẩn của clean (0,025) giữa 2 seed: seed 0 của clean (0,718) chỉ thấp hơn raw 0,008, seed 1 (0,683) thấp hơn 0,043. Với mAP50-95 chênh −0,024 lớn hơn cả hai độ lệch chuẩn (0,004 và 0,008), nhưng độ lệch chuẩn tính từ **chỉ 2 seed** không đáng tin (raw có hai giá trị gần như trùng nhau chỉ là ngẫu nhiên có thể xảy ra). Vì vậy mình không khẳng định raw tốt hơn clean, càng không thể nói clean tốt hơn.
- Phần lớn chênh lệch đến từ lớp **truck** (−0,111; clean seed 0 là 0,590 còn seed 1 chỉ 0,486). Ba lớp còn lại gần như bằng nhau (chênh ≤ 0,008).

**`raw` thật sự train trên bao nhiêu ảnh?** Trường `train_images = 224` trong JSON là số ảnh đưa vào, không phải số ảnh được dùng. Log Ultralytics ở ô train `raw` báo `11 corrupt` và bỏ qua 11 ảnh: `img_0010` (không mở được), `img_0014` và `img_0022` (toạ độ ngoài khoảng), `img_0020`, `img_0104`, `img_0194`, `img_0199` (id lớp 93, 7, 4, 4 ngoài 0–3), `img_0099` và `img_0117` (giá trị âm), `img_0136` (ảnh cắt cụt), `img_0179` (dòng nhãn hỏng). Vậy raw thực tế học khoảng 213 ảnh (224 − 11; mình suy ra bằng phép trừ, log ghi "216 images" nên con số chính xác có thể lệch vài ảnh). Với `clean`, log báo `202 images, 0 corrupt`.

**Giả thuyết giải thích và cách kiểm:**
1. **Truck ít mẫu nên rất nhiễu.** `class_stats.csv` của dữ liệu clean chỉ có 41 box truck (car 101, person 574, bus 32), nên AP của truck có thể nhảy hơn 0,1 giữa hai seed (0,590 → 0,486). Cách kiểm: train ≥ 5 seed, báo cáo AP theo lớp kèm độ lệch chuẩn, và đếm số box truck trong `raw` so với `clean`.
2. **`raw` có thể được thổi phồng do rò rỉ test.** Cửa vào tìm thấy 5 ảnh `raw` trùng ảnh trong kho test (`LEAK_TEST`: `test_033`, `test_039`, `test_044`, `test_085`, `test_009`), cộng thêm 8 ảnh trùng từng byte và 4 ảnh trùng gần đúng. `raw` học thuộc những ảnh này còn `clean` đã loại chúng. Cách kiểm: đánh giá lại cả hai mô hình trên test sau khi bỏ 5 ảnh bị rò rỉ và xem khoảng cách có thu hẹp không (mình chưa làm).
3. **Test chỉ 100 ảnh**, nên 1–2 ảnh khó cũng đủ làm mAP lệch vài phần trăm, nhất là với lớp ít mẫu.
4. **`clean` chưa thật sự sạch.** Pipeline kết luận Hold: còn 38/202 ảnh cảnh báo chưa được duyệt, và người duyệt là mô phỏng. Để biết "dữ liệu sạch hoàn toàn" giúp được bao nhiêu cần so thêm biến thể `oracle` (nhãn người), mình chưa chạy.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối: Hold, không phát hành.** Để thành Release cần giảm tỉ lệ ảnh còn cảnh báo xuống dưới 10% (≤ 20/202 ảnh), tức người duyệt cần xử lý thêm khoảng 18 ảnh nữa, hoặc tăng ngân sách duyệt. Không chỉnh `gate.warn_ratio_hold`, `review.budget_images` hay ngưỡng `conf` chỉ để ép ra Release (conf cao làm tụt recall `MISSING`). Trước khi phát hành nên duyệt ưu tiên: 3 `POSSIBLE_WRONG_CLASS` (IoU 0,91–0,97, rất đáng tin: `img_0078`, `img_0083`, `img_0220`), 4 `EMPTY_LABEL`, và các `POSSIBLE_MISSING` có conf ≥ 0,7.

**(b) Dùng AI viết code: có.** Claude giúp viết 4 module (`label_format`, `gate`, `autofix`, `second_opinion`) và hỗ trợ đọc kết quả calibration:
- Prompt chính: nhờ Claude xem repo, kiểm tra kết quả Bước 1, rồi viết 4 module (label_format, gate, autofix, second_opinion) theo docstring, đặt tên biến và hàm tường minh bằng tiếng Việt để mình đọc hiểu.
- Cách kiểm: chạy python -m pytest -q (79 test qua), đọc từng đoạn code, chạy python -m pipeline.run và đối chiếu 07_error_list_v3.txt, mở xem các cặp ảnh bị coi là trùng, và chạy lại pipeline với --budget 0 để kiểm cửa chặn.
