# Vietnamese Legal Document Crawler

Crawler tự động tải văn bản pháp luật Việt Nam từ thuvienphapluat.vn.

## Công nghệ sử dụng

| Công nghệ | Mục đích |
|-----------|----------|
| **Python 3.10+** | Ngôn ngữ lập trình |
| **Playwright** | Browser automation, xử lý download |
| **Pydantic** | Validation và configuration management |
| **structlog** | Structured logging |
| **python-dotenv** | Quản lý biến môi trường |

## Cài đặt

```bash
# 1. Tạo virtual environment
python3 -m venv .venv

# 2. Kích hoạt virtual environment
source .venv/bin/activate

# 3. Cài đặt dependencies
pip install -e .

# 4. Cài đặt Playwright browsers
playwright install chromium
```

## Cấu hình

Tạo file `.env` với nội dung:

```env
CRAWLER_USERNAME=your_username
CRAWLER_PASSWORD=your_password
```

## Cách chạy

### Chạy đầy đủ (325 documents)

```bash
source .venv/bin/activate
python main.py
```

### Chạy với giới hạn số lượng

```bash
# Chỉ tải 10 documents đầu tiên
python main.py --limit 10
```

### Chạy với browser hiển thị (debug)

```bash
python main.py --no-headless
```

### Test authentication

```bash
python main.py --test-auth
```

### Chạy với verbose logging

```bash
python main.py -v
```

## Chạy vào ban đêm (background)

```bash
# Chạy trong background với nohup
source .venv/bin/activate
nohup python main.py > crawl.log 2>&1 &

# Xem log realtime
tail -f crawl.log

# Kiểm tra process
ps aux | grep main.py
```

## Cấu trúc thư mục

```
crawl/
├── src/
│   ├── config.py              # Cấu hình
│   ├── models/                # Data models
│   ├── extractors/            # Trích xuất URL từ file
│   ├── crawler/
│   │   ├── auth.py            # Xử lý đăng nhập
│   │   └── downloader.py      # Tải documents
│   ├── storage/               # Progress tracking
│   └── utils/                 # Utilities (logging, retry)
├── data/                      # Thư mục chứa files đã tải
├── .auth/                     # Session state (gitignored)
├── .env                       # Credentials (gitignored)
├── main.py                    # Entry point
└── pyproject.toml             # Dependencies
```

## Output

Files được lưu trong thư mục `data/` với định dạng:

```
{số_thứ_tự}_{tên_văn_bản}.doc
```

Ví dụ:
- `1_Luat_Thue_gia_tri_gia_tang_sua_doi_2025.doc`
- `2_Luat_Giao_duc_sua_doi_2025_so_123_2025_QH15.doc`

## Trạng thái download

| Status | Ý nghĩa |
|--------|---------|
| **OK** | Tải thành công |
| **SKIP** | Trang không có nút download (bài viết tin tức) |
| **FAIL** | Lỗi timeout hoặc network |

## Lưu ý

- Crawler sử dụng delays ngẫu nhiên (1-3 giây) giữa các requests để tránh bị block
- Session được lưu tự động, không cần đăng nhập lại mỗi lần chạy
- Một số URL trong danh sách là bài viết tin tức (không phải văn bản pháp luật) nên sẽ bị SKIP
