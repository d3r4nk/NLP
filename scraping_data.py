import time
import tkinter as tk
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.keys import Keys
import os
import json
import gzip
import datetime as dt
import re
import argparse
from collections import Counter
from urllib.parse import urlparse, urlunparse

# Sample review URLs:
#   https://www.dienmayxanh.com/quat-dieu-hoa/sunhouse-shd7727-kg/danh-gia
#   https://www.dienmayxanh.com/quat-dieu-hoa/ava-rpd-80/danh-gia
#
# Sample category URLs (batch mode):
#   https://www.dienmayxanh.com/tivi
#   https://www.dienmayxanh.com/quat-dieu-hoa


def _now_ts() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _vn_now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat()


def _strip_query_fragment(url: str) -> str:
    try:
        p = urlparse(url)
        p = p._replace(query="", fragment="")
        return urlunparse(p)
    except Exception:
        return url


def _slug_from_url(url: str) -> str:
    # lấy phần path để đặt tên folder
    try:
        url = _strip_query_fragment(url)
        path = re.sub(r"^https?://", "", url)
        path = path.replace("/", "_")
        path = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", path)
        return path.strip("_")[:120] or "dienmayxanh"
    except Exception:
        return "dienmayxanh"


def _write_gz_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)


def _append_jsonl(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _init_edge_driver(edge_options: Options):
    """Khởi tạo Edge WebDriver theo thứ tự ưu tiên:
    1) Nếu có env EDGEWEBDRIVER=/path/to/msedgedriver.exe -> dùng path đó.
    2) Nếu không: dùng Selenium Manager (Selenium >= 4.6) để tự tải driver.

    Lưu ý: cách (2) là cách chạy được trên máy khác mà không hard-code đường dẫn.
    """

    edgedriver_path = os.environ.get("EDGEWEBDRIVER")
    if edgedriver_path:
        service = Service(edgedriver_path)
        return webdriver.Edge(service=service, options=edge_options)

    # Selenium Manager
    return webdriver.Edge(options=edge_options)


def _build_edge_options(headless: bool = False) -> Options:
    edge_options = Options()
    edge_options.add_argument("--start-maximized")
    edge_options.add_argument("--ignore-certificate-errors")
    edge_options.add_argument("--ignore-ssl-errors")
    edge_options.add_argument("--disable-web-security")
    if headless:
        # Edge/Chromium headless
        edge_options.add_argument("--headless=new")
        edge_options.add_argument("--window-size=1920,1080")
    return edge_options


def _ensure_review_url(url: str) -> str:
    url = _strip_query_fragment(url)
    if url.endswith("/danh-gia"):
        return url
    return url.rstrip("/") + "/danh-gia"


def _looks_like_product_url(href: str, category_path: str) -> bool:
    """Heuristic: product page thường nằm trong category và có thêm slug."""
    try:
        p = urlparse(href)
        if p.netloc and p.netloc != "www.dienmayxanh.com":
            return False
        path = (p.path or "").strip("/")
        if not path:
            return False

        # loại các trang không liên quan
        bad = ("tin-tuc", "hoi-dap", "khuyen-mai", "wiki", "video", "gio-hang", "lich-su-mua-hang", "sitemap")
        if any(path.startswith(x) for x in bad):
            return False

        # nếu đang crawl từ category /tivi, ưu tiên link bắt đầu bằng /tivi/
        cat = category_path.strip("/")
        if cat and not path.startswith(cat + "/"):
            return False

        # cần ít nhất 2 segment: category/slug
        if path.count("/") < 1:
            return False

        # loại link /danh-gia luôn (ta tự append sau)
        if path.endswith("/danh-gia"):
            return False

        return True
    except Exception:
        return False


def collect_product_urls_from_category(driver, category_url: str, max_products: int = 20, scroll_rounds: int = 10, delay_s: float = 1.5) -> list:
    """Mở trang category, scroll để load thêm, nhặt link sản phẩm."""

    category_url = _strip_query_fragment(category_url)
    category_path = urlparse(category_url).path

    driver.get(category_url)
    time.sleep(3)

    # scroll để load thêm sản phẩm
    for _ in range(scroll_rounds):
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
        except Exception:
            pass
        time.sleep(delay_s)

    links = driver.find_elements(By.CSS_SELECTOR, "a")

    urls = []
    seen = set()
    for a in links:
        href = a.get_attribute("href")
        if not href:
            continue
        href = _strip_query_fragment(href)
        if href in seen:
            continue
        if _looks_like_product_url(href, category_path=category_path):
            seen.add(href)
            urls.append(href)
        if len(urls) >= max_products:
            break

    return urls


def _looks_like_not_found(page_source: str) -> bool:
    if not page_source:
        return False
    s = page_source.lower()
    # DMX 404 message
    if "không tìm thấy trang" in s or "khong tim thay trang" in s:
        return True
    if "404" in s and "forbidden" not in s:
        # best-effort
        if "trở về trang chủ" in s or "tro ve trang chu" in s:
            return True
    return False


def scrape_review_url(driver, review_url: str, run_dir: str, base_name: str = "comments", scroll_times: int = 5, scroll_delay_s: float = 2.0):
    """Cào 1 URL /danh-gia. Lưu raw HTML + JSONL + CSV + stats trong run_dir.

    Nếu trang /danh-gia không tồn tại (404 UI), sẽ ghi stats với error và total_comments=0 để batch không bị crash.
    """

    review_url = _ensure_review_url(review_url)

    csv_path = os.path.join(run_dir, f"{base_name}.csv")
    jsonl_path = os.path.join(run_dir, f"{base_name}.jsonl")
    stats_path = os.path.join(run_dir, "stats.json")
    html_dir = os.path.join(run_dir, "html")
    os.makedirs(run_dir, exist_ok=True)

    index = 1
    data = []
    rating_counter = Counter()
    pages_crawled = 0

    driver.get(review_url)
    time.sleep(3)

    # Nếu /danh-gia không tồn tại
    try:
        src0 = driver.page_source or ""
    except Exception:
        src0 = ""

    if _looks_like_not_found(src0):
        # vẫn lưu raw để audit
        try:
            _write_gz_text(os.path.join(html_dir, "page_001.html.gz"), src0)
        except Exception:
            pass

        # tạo CSV rỗng đúng schema để pipeline train/merge không bị gãy
        df = pd.DataFrame([], columns=["Index", "Author", "Shop", "Rating", "Time", "Comment"])
        df.to_csv(csv_path, index=False, encoding="utf-8")

        stats = {
            "source_url": review_url,
            "run_dir": run_dir,
            "pages_crawled": 1,
            "total_comments": 0,
            "rating_distribution": {},
            "error": "REVIEW_PAGE_NOT_FOUND",
            "generated_files": {
                "csv": os.path.basename(csv_path),
                "jsonl": os.path.basename(jsonl_path),
                "html_dir": "html/",
            },
        }
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        return stats

    while True:
        pages_crawled += 1

        # lưu HTML thô mỗi trang
        try:
            html = driver.page_source or ""
            _write_gz_text(os.path.join(html_dir, f"page_{pages_crawled:03d}.html.gz"), html)
        except Exception:
            pass

        for _ in range(scroll_times):
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SPACE)
            time.sleep(scroll_delay_s)

        comment_list = driver.find_elements(By.CSS_SELECTOR, "ul.comment-list li")
        if not comment_list:
            break

        for comment in comment_list:
            try:
                author = comment.find_element(By.CLASS_NAME, "cmt-top-name").text
                author = author.strip() if author else "N/A"
            except Exception:
                author = "N/A"

            try:
                shop = comment.find_element(By.CLASS_NAME, "confirm-buy").text.strip()
                shop = shop.replace("Đã mua tại ", "") if shop else "N/A"
            except Exception:
                shop = "N/A"

            try:
                rating = len(comment.find_elements(By.CSS_SELECTOR, ".cmt-top-star .iconcmt-starbuy"))
                if rating:
                    rating_counter[str(rating)] += 1
            except Exception:
                rating = "N/A"

            try:
                text = comment.find_element(By.CLASS_NAME, "cmt-txt").text
                text = text.strip() if text else "N/A"
            except Exception:
                text = "N/A"

            try:
                used_time = comment.find_element(By.CSS_SELECTOR, "span.cmtd.dot-line").text.strip()
                used_time = used_time.replace("Đã dùng khoảng ", "") if used_time else "N/A"
            except Exception:
                used_time = "N/A"

            data.append([index, author, shop, rating, used_time, text])

            _append_jsonl(
                jsonl_path,
                {
                    "index": index,
                    "author": author,
                    "shop": shop,
                    "rating": rating,
                    "used_time": used_time,
                    "comment": text,
                    "source_url": review_url,
                    "page": pages_crawled,
                    "crawled_at": _vn_now_iso(),
                },
            )

            index += 1

        # phân trang
        try:
            current_page = int(driver.find_element(By.XPATH, '//span[@class="active"]').text.strip())
        except Exception:
            current_page = 1

        page_links = driver.find_elements(By.XPATH, '//div[@class="pagcomment"]/a')
        next_page = None
        for page in page_links:
            try:
                page_num = page.text.strip()
                if page_num.isdigit() and int(page_num) == int(current_page) + 1:
                    next_page = page
                    break
            except Exception:
                continue

        if next_page:
            next_page.click()
            time.sleep(3)
        else:
            break

    df = pd.DataFrame(data, columns=["Index", "Author", "Shop", "Rating", "Time", "Comment"])
    df.to_csv(csv_path, index=False, encoding="utf-8")

    stats = {
        "source_url": review_url,
        "run_dir": run_dir,
        "pages_crawled": pages_crawled,
        "total_comments": len(data),
        "rating_distribution": dict(rating_counter),
        "generated_files": {
            "csv": os.path.basename(csv_path),
            "jsonl": os.path.basename(jsonl_path),
            "html_dir": "html/",
        },
    }
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def run_cli(args) -> int:
    session = _now_ts()
    out_base = f"raw_data_{args.mode}"
    os.makedirs(out_base, exist_ok=True)

    edge_options = _build_edge_options(headless=args.headless)
    driver = _init_edge_driver(edge_options)

    try:
        if args.category:
            cat_url = args.category.strip()
            run_dir = os.path.join(out_base, f"batch__{_slug_from_url(cat_url)}__{session}")
            os.makedirs(run_dir, exist_ok=True)

            products = collect_product_urls_from_category(
                driver,
                category_url=cat_url,
                max_products=args.max_products,
                scroll_rounds=args.category_scrolls,
                delay_s=args.category_scroll_delay,
            )

            # lưu danh sách sản phẩm
            products_path = os.path.join(run_dir, "products.json")
            with open(products_path, "w", encoding="utf-8") as f:
                json.dump(products, f, ensure_ascii=False, indent=2)

            batch_stats = {
                "mode": args.mode,
                "category": cat_url,
                "max_products": args.max_products,
                "products_collected": len(products),
                "started_at": _vn_now_iso(),
                "products": [],
            }

            total_comments = 0
            rating_total = Counter()

            # output layout tối ưu cho train:
            # - csv/ <product_slug>.csv
            # - jsonl/ <product_slug>.jsonl
            # - stats/ <product_slug>.stats.json
            # - raw_html/ <product_slug>/page_XXX.html.gz
            csv_dir = os.path.join(run_dir, "csv")
            jsonl_dir = os.path.join(run_dir, "jsonl")
            stats_dir = os.path.join(run_dir, "stats")
            raw_html_dir = os.path.join(run_dir, "raw_html")
            os.makedirs(csv_dir, exist_ok=True)
            os.makedirs(jsonl_dir, exist_ok=True)
            os.makedirs(stats_dir, exist_ok=True)
            os.makedirs(raw_html_dir, exist_ok=True)

            for i, p in enumerate(products, start=1):
                review_url = _ensure_review_url(p)
                slug = f"{i:04d}__{_slug_from_url(p)}"

                # scrape vào folder tạm theo sản phẩm để có html/
                prod_tmp_dir = os.path.join(run_dir, "_products_tmp", slug)
                st = scrape_review_url(
                    driver,
                    review_url=review_url,
                    run_dir=prod_tmp_dir,
                    base_name=args.file_prefix,
                    scroll_times=args.scroll_times,
                    scroll_delay_s=args.scroll_delay,
                )

                # move/rename outputs sang layout train-friendly
                # csv/jsonl
                src_csv = os.path.join(prod_tmp_dir, f"{args.file_prefix}.csv")
                src_jsonl = os.path.join(prod_tmp_dir, f"{args.file_prefix}.jsonl")
                dst_csv = os.path.join(csv_dir, f"{slug}.csv")
                dst_jsonl = os.path.join(jsonl_dir, f"{slug}.jsonl")
                if os.path.exists(src_csv):
                    os.replace(src_csv, dst_csv)
                if os.path.exists(src_jsonl):
                    os.replace(src_jsonl, dst_jsonl)

                # stats
                src_stats = os.path.join(prod_tmp_dir, "stats.json")
                dst_stats = os.path.join(stats_dir, f"{slug}.stats.json")
                if os.path.exists(src_stats):
                    os.replace(src_stats, dst_stats)

                # raw html folder
                src_html_dir = os.path.join(prod_tmp_dir, "html")
                dst_html_dir = os.path.join(raw_html_dir, slug)
                if os.path.isdir(src_html_dir):
                    os.makedirs(dst_html_dir, exist_ok=True)
                    # move all files
                    for fn in os.listdir(src_html_dir):
                        os.replace(os.path.join(src_html_dir, fn), os.path.join(dst_html_dir, fn))

                # cleanup tmp dir (best-effort)
                try:
                    for root_, dirs_, files_ in os.walk(prod_tmp_dir, topdown=False):
                        for f_ in files_:
                            try:
                                os.remove(os.path.join(root_, f_))
                            except Exception:
                                pass
                        for d_ in dirs_:
                            try:
                                os.rmdir(os.path.join(root_, d_))
                            except Exception:
                                pass
                    try:
                        os.rmdir(prod_tmp_dir)
                    except Exception:
                        pass
                except Exception:
                    pass

                # record stats (update run_dir to new locations)
                st["run_dir"] = os.path.join(run_dir, "(see csv/jsonl/stats/raw_html)")
                batch_stats["products"].append(st)

                total_comments += int(st.get("total_comments", 0) or 0)
                for k, v in (st.get("rating_distribution") or {}).items():
                    try:
                        rating_total[k] += int(v)
                    except Exception:
                        pass

                if args.delay_between_products > 0:
                    time.sleep(args.delay_between_products)

            batch_stats["finished_at"] = _vn_now_iso()
            batch_stats["total_comments"] = total_comments
            batch_stats["rating_distribution_total"] = dict(rating_total)

            with open(os.path.join(run_dir, "batch_stats.json"), "w", encoding="utf-8") as f:
                json.dump(batch_stats, f, ensure_ascii=False, indent=2)

            print("DONE")
            print("Run dir:", run_dir)
            print("Products:", products_path)
            print("Batch stats:", os.path.join(run_dir, "batch_stats.json"))
            return 0

        if args.url:
            url = args.url.strip()
            run_dir = os.path.join(out_base, f"single__{_slug_from_url(url)}__{session}")
            st = scrape_review_url(
                driver,
                review_url=url,
                run_dir=run_dir,
                base_name=args.file_prefix,
                scroll_times=args.scroll_times,
                scroll_delay_s=args.scroll_delay,
            )
            print("DONE")
            print("Run dir:", run_dir)
            print("Stats:", os.path.join(run_dir, "stats.json"))
            return 0

        print("Bạn cần truyền --url (1 sản phẩm) hoặc --category (nhiều sản phẩm).")
        return 2

    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ===================== GUI mode (giữ để tương thích) =====================

def scrape_comments_gui():
    URL = url_entry.get().strip()
    file_name = file_name_entry.get().strip() or "comments"
    mode = mode_var.get()

    if not URL:
        result_label.config(text="Vui lòng nhập URL trang đánh giá của sản phẩm!", fg="red")
        return

    session = _now_ts()
    out_base = f"raw_data_{mode}"
    run_dir = os.path.join(out_base, f"single__{_slug_from_url(URL)}__{session}")

    result_label.config(
        text=(
            "Đang lấy dữ liệu...\n"
            f"Output folder: {run_dir}\n"
            "(Nếu lỗi driver: đặt biến môi trường EDGEWEBDRIVER trỏ tới msedgedriver.exe)"
        ),
        fg="blue",
    )
    root.update()

    edge_options = _build_edge_options(headless=False)
    driver = _init_edge_driver(edge_options)

    try:
        scrape_review_url(driver, review_url=URL, run_dir=run_dir, base_name=file_name)
        result_label.config(
            text=(
                "DONE\n"
                f"- Output folder: {run_dir}\n"
                f"- CSV/JSONL/HTML/Stats nằm trong thư mục này."
            ),
            fg="green",
        )
    except Exception as e:
        result_label.config(text=f"Error: {e}", fg="red")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def launch_gui():
    global root, url_entry, file_name_entry, mode_var, result_label

    root = tk.Tk()
    root.title("Cào dữ liệu bình luận từ Điện Máy Xanh (Selenium)")

    tk.Label(root, text="Nhập URL trang đánh giá (/danh-gia):").pack(pady=5)
    url_entry = tk.Entry(root, width=70)
    url_entry.pack(pady=5)

    tk.Label(root, text="Nhập tên file (không cần .csv, mặc định: comments):").pack(pady=5)
    file_name_entry = tk.Entry(root, width=70)
    file_name_entry.pack(pady=5)

    mode_var = tk.StringVar(value="train")
    mode_frame = tk.Frame(root)
    mode_frame.pack(pady=5)

    tk.Label(mode_frame, text="Chọn chế độ lưu dữ liệu:").pack(side=tk.LEFT)
    tk.Radiobutton(mode_frame, text="Train", variable=mode_var, value="train").pack(side=tk.LEFT, padx=10)
    tk.Radiobutton(mode_frame, text="Test", variable=mode_var, value="test").pack(side=tk.LEFT)

    scrape_button = tk.Button(root, text="Lấy dữ liệu", command=scrape_comments_gui)
    scrape_button.pack(pady=10)

    result_label = tk.Label(root, text="", width=100, height=14, justify="left", anchor="w")
    result_label.pack(pady=5)

    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description="Cào bình luận Điện Máy Xanh bằng Selenium (Edge)")
    ap.add_argument("--url", help="URL sản phẩm hoặc /danh-gia (cào 1 sản phẩm)")
    ap.add_argument("--category", help="URL category (vd https://www.dienmayxanh.com/tivi) để cào nhiều sản phẩm")
    ap.add_argument("--max-products", type=int, default=20)
    ap.add_argument("--mode", choices=["train", "test"], default="train")
    ap.add_argument("--file-prefix", default="comments", help="Tên file output (không gồm đuôi)")

    ap.add_argument("--headless", action="store_true")

    ap.add_argument("--scroll-times", type=int, default=5, help="Số lần SPACE scroll mỗi trang comment")
    ap.add_argument("--scroll-delay", type=float, default=2.0)
    ap.add_argument("--delay-between-products", type=float, default=0.5)

    ap.add_argument("--category-scrolls", type=int, default=10, help="Số lần END scroll trên trang category")
    ap.add_argument("--category-scroll-delay", type=float, default=1.5)

    args = ap.parse_args()

    # Nếu có tham số CLI -> chạy batch/single bằng 1 lệnh.
    if args.url or args.category:
        raise SystemExit(run_cli(args))

    # Không có args -> mở GUI.
    launch_gui()


if __name__ == "__main__":
    main()
