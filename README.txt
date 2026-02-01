# NLP - Data Crawling Scripts (DMX + Steam)

Repo này hiện có **2 script chính** để thu thập dữ liệu:

1) `dmx_crawl.py` – Cào review sản phẩm từ **Điện Máy Xanh** (Selenium + Microsoft Edge)
2) `steam_crawl.py` – Cào review từ **Steam** (requests, JSON API)

> Lưu ý: README cũ có nhắc các file như `scraping_data.py`, `merging_data.py`, `cleaning_normalizing_data.py`, ... nhưng **các file đó không có trong repo hiện tại**. Tài liệu dưới đây được chỉnh lại để khớp với code đang có.

---

## 1) DMX crawler (`dmx_crawl.py`)

### Mục đích
- Mở trang review ("/danh-gia") của một sản phẩm trên dienmayxanh.com
- Scroll để load comment
- Phân trang và lấy toàn bộ comment ở các trang
- Xuất ra file CSV

### Cài đặt
```bash
pip install -r requirements-scraper.txt
```

### Yêu cầu
- Cần có **Microsoft Edge**.
- Cần có **msedgedriver** đúng phiên bản.

Trong code hiện đang **hard-code** đường dẫn driver:
```py
EDGE_DRIVER_PATH = r"D:\\msedgedriver.exe"
```
Bạn cần sửa `EDGE_DRIVER_PATH` cho đúng máy bạn.

### Cấu hình cần sửa trong file
Các biến quan trọng ở đầu file:
- `BASE_URL` (đang là 1 link review, nhưng thực tế chỉ dùng để load trang ban đầu)
- `EDGE_DRIVER_PATH` (đường dẫn đến `msedgedriver.exe`)
- `OUTPUT_FOLDER` (thư mục output)
- `OUTPUT_FILE` (tên file CSV)

Trong `main()` hiện đang cào **1 sản phẩm cố định**:
```py
product_url = "https://www.dienmayxanh.com/quat-dieu-hoa/ava-rpd-80"
```
Bạn sửa `product_url` thành URL sản phẩm bạn muốn cào.

### Chạy
```bash
python dmx_crawl.py
```

### Output
Mặc định:
- `raw_data_all_fans/quat_dieu_hoa_comments.csv`

Các cột CSV:
- `Index`
- `Product_URL`
- `Author`
- `Shop`
- `Rating` (số sao, tính bằng số icon sao)
- `Used_Time`
- `Comment`

---

## 2) Steam crawler (`steam_crawl.py`)

### Mục đích
- Gọi Steam Reviews API để lấy review (hiện đang set `language="english"`)
- Chuẩn hoá dữ liệu review thành JSONL
- Xuất `reviews.jsonl` + `reviews.csv`
- Lưu raw response từng trang dưới dạng `*.json.gz`

### Cài đặt
```bash
pip install -r requirements-steam.txt
```

### Cấu hình trong code
Trong `steam_crawl.py`:
- Danh sách game được cào nằm trong `APP_MAP` (appid + meta)
- Output dir mặc định: `steam_darkest_dungeon_reviews/`
- `MAX_REVIEWS` đang để rất lớn (`1_000_000`) → có thể chạy lâu
- `DELAY` để chống rate-limit

Nếu bạn muốn cào ít hơn, hãy giảm `MAX_REVIEWS`.

### Chạy
```bash
python steam_crawl.py
```

### Output
Thư mục output theo từng lần chạy:
```
steam_darkest_dungeon_reviews/<YYYYMMDD_HHMMSS>/
  games/
    <appid>_<slug>/
      raw/page_0001.json.gz ...
      reviews.jsonl
      reviews.csv
```

---

## Gợi ý nhanh
- Nếu bạn muốn README dạng GitHub chuẩn, có thể đổi tên `README.txt` → `README.md`.
- Nếu bạn muốn script DMX cào nhiều sản phẩm/category (như README cũ mô tả), hiện **code chưa có**; cần viết thêm logic/CLI.
