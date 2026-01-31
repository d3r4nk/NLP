Hướng dẫn chạy trình tự chạy chương trình

1. Thu thập dữ liệu
- File thu thập dữ liệu : scraping_data.py

Ghi chú (đã sửa để chạy trên máy khác):
- Không còn hard-code đường dẫn msedgedriver.
- Nếu Selenium Manager tự tải driver không hoạt động, đặt biến môi trường:
  EDGEWEBDRIVER=C:\\path\\to\\msedgedriver.exe
- Script giờ lưu thêm dữ liệu thô (raw HTML) + JSONL + stats.json trong thư mục output theo từng phiên.

- Input : 
  + URL trang đánh giá của sản phẩm
  vd : https://www.dienmayxanh.com/quat-dieu-hoa/may-lam-mat-khong-khi-kangaroo-kg50f62/danh-gia

  + Tên file (định dạng .csv)
  + Chế độ lưu dữ liệu (Train - Test)

- Output (đã mở rộng):
  + CSV (như cũ)
  + JSONL (mỗi bình luận 1 dòng)
  + raw HTML (.html.gz)
  + stats.json / batch_stats.json

- Output layout khi chạy --category (tối ưu cho train):
  + csv/*.csv (mỗi sản phẩm 1 file CSV, đặt theo slug -> dễ merge/train)
  + jsonl/*.jsonl
  + stats/*.stats.json
  + raw_html/<product_slug>/*.html.gz

Chạy bằng 1 lệnh (cào N sản phẩm từ 1 category):
  python scraping_data.py --category "https://www.dienmayxanh.com/tivi" --max-products 20 --mode train

Chạy 1 sản phẩm:
  python scraping_data.py --url "https://www.dienmayxanh.com/quat-dieu-hoa/ava-rpd-80/danh-gia" --mode train

Có thể thêm --headless để chạy ẩn.

---

(Thêm) Cào TOP game theo số lượng đánh giá (User Reviews) + lấy review TIẾNG VIỆT (Bước 1: Thu thập + raw + thống kê)
- File: steam_crawl_vi_top10_and_stats.py
- Cài:
  pip install -r requirements-steam.txt
- Chạy ví dụ:
  py steam_crawl_vi_top10_and_stats.py --top 10 --max-reviews-per-game 500
- Output:
  steam_raw/batch_top_reviews_vi_<timestamp>/
    appids.json
    batch_stats.json
    games/<rank>_<appid>_<slug>/
      raw/page_0001.json.gz ...
      reviews.jsonl
      reviews.csv
      stats.json

2. Kết hợp dữ tập dữ liệu
- File kết hợp tập dữ liệu : merging_data.py
- Phạm vi kết hợp :
  + Train -> Các file .csv nằm trong thư mục raw_data_train
  + Test -> Các file .csv nằm trong thư mục raw_data_test

- Input : 
  + Loại dữ liệu (Train - Test) -> Lưu vào raw_data_train_merged hoặc raw_data_test_merged
  + Tên file sau khi gộp (định dạng .csv)

- Output : File với tên và định dạng .csv được lưu vào đúng thư mục theo chế độ đã chọn

- Mục đích : Vì tập dataset của một sản phẩm là không đủ để thực hiện huấn luyện mô hình có độ chính xác cao, nên nhóm quyết định kết hợp
các dataset của nhiều sản phẩm cùng loại (ví dụ: các mẫu mã khác nhau của quạt điều hòa) để phân cụm sự nhất quán trong cách đánh giá của khách
hàng, cũng như dự đoán số sao đánh giá sản phẩm (ở đây là đánh giá về quạt điều hòa nói chung)

3. Làm sạch và chuẩn hóa dữ liệu
- File chuẩn hóa : cleaning_normalizing_data.py

- Input :
  + Loại dữ liệu (Train - Test) -> Lưu vào thư mục clean_data_train hoặc clean_data_test
  + Tên file cần làm sạch và chuẩn hóa (định dạng .csv)
  + Tên file sau khi làm sạch và chuẩn hóa (định dạng .csv)

- Output : File được chuẩn hóa với tên và định dạng .csv được lưu vào đúng thư mục theo chế độ đã chọn

4. Phân cụm dữ liệu tính nhất quán trong cách đánh giá của khách hàng.
- File phân cụm dữ liệu: clustering.py
- File csv dùng để phân cụm : clean_data_train/quat_dieu_hoa_train_clean.csv
- Mục đích: Thực hiện phân cụm dữ liệu sử dụng các mô hình KMeans và Gaussian Mixture Models (GMM)
- Các bước thực hiện:
  + Tải dữ liệu.
  + Tiền xử lý cột Comment (làm sạch và phân tích cảm xúc).
  + Thực hiện trích xuất đặc trưng (TF-IDF và các đặc trưng dựa trên cảm xúc).
  + Chạy phân cụm với KMeans và GMM.
  + Tạo và lưu các chỉ số phân cụm (ví dụ: Silhouette Score, Davies-Bouldin).
  + Hiển thị kết quả phân cụm của mô hình KMeans và GMM trong thư mục cluster_result.
  
- Kết quả:
  + Ảnh comparison_clustering.png gồm các biểu đồ về:

    1. Biểu đồ phân cụm PCA (Biểu đồ đầu tiên của hàng 1 - KMeans và hàng 3 - GMM)
    -> So sánh sự phân tách giữa các cụm của KMeans và GMM sau khi giảm chiều dữ liệu với PCA.

    2. Biểu đồ về tính nhất quán (Biểu đồ thứ hai của hàng 1 - KMeans và hàng 3 - GMM)
    -> Đánh giá mức độ nhất quán trong các cụm giữa KMeans và GMM.

    3. Biểu đồ phân bố đánh giá số sao (Biểu đồ thứ ba của hàng 1 - KMeans và hàng 3 - GMM)
    -> So sánh phân bố các đánh giá trong các cụm của KMeans và GMM.

    4. Biểu đồ cảm xúc (sentiment) theo cluster (Biểu đồ đầu tiên của hàng 2 - KMeans và hàng 4 - GMM)
    -> So sánh sự phân phối cảm xúc (sentiment) trong các cụm giữa KMeans và GMM.

    5. Biểu đồ ma trận Cluster theo tính nhất quán (Consistency) (Biểu đồ thứ hai của hàng 2 - KMeans và hàng 4 - GMM)
    -> So sánh sự phù hợp giữa các cụm và mức độ nhất quán trong KMeans và GMM.

    6. Biểu đồ phân bố tính nhất quán (Biểu đồ thứ ba của hàng 2 - KMeans và hàng 4 - GMM)
    -> So sánh tỷ lệ sự nhất quán trong các cụm giữa KMeans và GMM.
  
  + Ảnh cluster_metrics_comparison.png gồm biểu đồ so sánh các chỉ số silhouette, calinski_harabasz_score và davies_bouldin_score
  của 2 mô hình KMeans và GMM

  + 2 file .csv phân cụm từ 2 mô hình KMeans và GMM

  + file clustering_comparison_report.txt chứa phân bố nhãn về tính nhất quán của 2 mô hình phân cụm

  + file cluster_detailed_report.txt chứa phân tích chi tiết về các cluster cũng như phân bố về tính nhất quán của 2 mô hình

5. Thử nghiệm mô hình phân cụm
- File thử nghiệm : test_cluster.py
- File csv dùng để thử nghiệm mô hình tốt nhất : clean_data_test/merged_data_for_test.csv (tổng hợp từ quat_dieu_hoa_test_clean.csv
 và bep_gas_clean.csv vì số record quá ít sẽ gây ra overfitting)
- Mục đích: Kiểm tra kết quả phân cụm và đánh giá mô hình.
- Cách bước thực hiện
  + Tải mô hình tốt nhất đã huấn luyện từ cluster_result/models. (KMeans)
  + Tải và tiền xử lý dữ liệu test.
  + Dự đoán nhãn phân cụm cho dữ liệu test.
  + Tính toán các chỉ số phân cụm (ví dụ: Silhouette Score).
  + Vẽ các biểu đồ kết quả phân cụm
  + Lưu kết quả phân cụm và báo cáo vào thư mục test_cluster_results.

- Kết quả :
  + File test_clustering_results.csv gồm các record sau khi phân cụm bằng mô hình tốt nhất (KMeans)

  + Ảnh test_clustering_visualization.png gồm các biểu đồ kết quả phân cụm KMeans.

  + File test_performance_report.txt chứa các báo cáo hiệu suất phân cụm chi tiết.

6. Huấn luyện mô hình dự đoán
- File huấn luyện : prediction.py
- Flie csv dùng để train : clean_data_train/quat_dieu_hoa_train_clean.csv
- File csv dùng để test : clean_data_test/quat_dieu_hoa_test_clean.csv
- Mục đích: Huấn luyện 3 mô hình hồi quy dự đoán số sao dựa trên các bình luận, so sánh và chọn ra mô hình tốt nhất.
- Các bước thực hiện:
  + Tải và tiền xử lý dữ liệu (sử dụng các đặc trưng từ Comment).
  + Huấn luyện 3 mô hình hồi quy như Ridge, RandomForest, GradientBoosting.
  + Chạy cross-validation và chọn mô hình tốt nhất.
  + Dự đoán số sao cho dữ liệu test.
  + Đánh giá mô hình bằng các chỉ số như R², RMSE, MAE.
  + Lưu các kết quả vào thư mục excepted_result.

- Kết quả :
  + File detailed_predictions.csv chứa các record sau khi dự đoán số sao.

  + Mô hình best_model.pkl chứa mô hình có hiệu suất tốt nhất trong 3 mô hình (GradientBoosting)

  + File model_comparison chứa các chỉ số đánh giá như R², RMSE, MAE, ...

  + Ảnh comprehensive_analysis.png chứa các biểu đồ so sánh 3 mô hình (biểu đồ 1, 2, 3, 7 từ trái qua phải, trên xuống dưới)
  và các biểu đồ khác (so sánh đánh giá thực và dự đoán bởi GradientBoosting, biểu đồ Residuals, biểu đồ 10 đặc trưng quan trọng nhất
  và biểu đồ phân bố lỗi)

  + Ảnh additional_analysis.png chứa heatmap so sánh đánh giá thực - dự đoán và phân phối lỗi dự đoán theo đánh giá thực 

7. Thử nghiệm mô hình dự đoán
- File thử nghiệm : test_predict.py
- File csv dùng để thử nghiệm mô hình : clean_data_test/bep_gas_clean.csv
- Mục đích: Đánh giá kết quả dự đoán và mô hình đã huấn luyện.
- Các bước thực hiện:
  + Tải mô hình dự đoán từ excepted_result/best_model.pkl. (GradientBoosting)
  + Tiền xử lý dữ liệu test và dự đoán số sao cho mỗi bình luận.
  + Tính toán các chỉ số hiệu suất (R², RMSE, MAE, ...) cho kết quả dự đoán.
  + Vẽ biểu đồ phân tán, lỗi dự đoán và các chỉ số tổng hợp.
  + Lưu các kết quả đánh giá vào thư mục prediction_result.

- Kết quả :
  + Ảnh prediction_evaluation chứa các biểu đồ như so sánh đánh giá thật - dự đoán, phân bố lỗi, ma trận nhầm lẫn, phân phối
  sai số dự đoán, phân phối dự đoán số sao đánh giá.

  + File prediction_metrics.csv chứa các chỉ số hiệu suất của kết quả dự đoán.
  + File test_predictions.csv chứa các record sau khi dự đoán bằng GradientBoosting.
