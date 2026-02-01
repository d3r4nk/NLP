import time
import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.keys import Keys

BASE_URL = "https://www.dienmayxanh.com/quat-dieu-hoa/ava-rpd-80/danh-gia"
OUTPUT_FOLDER = "raw_data_all_fans"
OUTPUT_FILE = "quat_dieu_hoa_comments.csv"

EDGE_DRIVER_PATH = r"D:\msedgedriver.exe"

def init_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    service = Service(EDGE_DRIVER_PATH)
    return webdriver.Edge(service=service, options=options)

def get_all_product_links(driver):
    driver.get(BASE_URL)
    time.sleep(3)

    product_links = set()

    while True:
        products = driver.find_elements(By.CSS_SELECTOR, "a.main-contain")
        for p in products:
            link = p.get_attribute("href")
            if link and "/quat-dieu-hoa/" in link:
                product_links.add(link)

        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "a.view-more")
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(3)
        except:
            break

    return list(product_links)

def scrape_comments_of_product(driver, product_url, start_index):
    data = []
    index = start_index

    comment_url = product_url + "/danh-gia"
    driver.get(comment_url)
    time.sleep(3)

    while True:
        for _ in range(4):
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
            time.sleep(1.5)

        comments = driver.find_elements(By.CSS_SELECTOR, "ul.comment-list li")
        if not comments:
            break

        for c in comments:
            try:
                author = c.find_element(By.CLASS_NAME, "cmt-top-name").text.strip()
            except:
                author = "N/A"

            try:
                shop = c.find_element(By.CLASS_NAME, "confirm-buy").text.replace("Đã mua tại ", "").strip()
            except:
                shop = "N/A"

            try:
                rating = len(c.find_elements(By.CSS_SELECTOR, ".cmt-top-star .iconcmt-starbuy"))
            except:
                rating = "N/A"

            try:
                used_time = c.find_element(By.CSS_SELECTOR, "span.cmtd.dot-line").text.replace("Đã dùng khoảng ", "").strip()
            except:
                used_time = "N/A"

            try:
                comment_text = c.find_element(By.CLASS_NAME, "cmt-txt").text.strip()
            except:
                comment_text = "N/A"

            data.append([
                index,
                product_url,
                author,
                shop,
                rating,
                used_time,
                comment_text
            ])
            index += 1

        try:
            current_page = int(driver.find_element(By.CSS_SELECTOR, "span.active").text)
        except:
            break

        next_page = None
        pages = driver.find_elements(By.CSS_SELECTOR, "div.pagcomment a")
        for p in pages:
            if p.text.isdigit() and int(p.text) == current_page + 1:
                next_page = p
                break

        if next_page:
            driver.execute_script("arguments[0].click();", next_page)
            time.sleep(3)
        else:
            break

    return data, index

def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    driver = init_driver()
    all_data = []
    index = 1

    product_url = "https://www.dienmayxanh.com/quat-dieu-hoa/ava-rpd-80"

    product_data, index = scrape_comments_of_product(driver, product_url, index)
    all_data.extend(product_data)

    driver.quit()

    df = pd.DataFrame(
        all_data,
        columns=[
            "Index",
            "Product_URL",
            "Author",
            "Shop",
            "Rating",
            "Used_Time",
            "Comment"
        ]
    )

    df.to_csv(
        os.path.join(OUTPUT_FOLDER, OUTPUT_FILE),
        index=False,
        encoding="utf-8-sig"
    )


if __name__ == "__main__":
    main()
