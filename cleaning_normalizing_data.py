import pandas as pd
import re
import tkinter as tk
import os

# Define stopwords
STOPWORDS = {
    "và", "là", "có", "những", "của", "cho", "này", "đó", "đc", "dc",
    "cái", "rất", "bên", "nên", "sẽ", "với", "tại", "ra", "vào", "để", "đang",
    "vẫn", "thì", "mình", "tôi", "ta", "bạn", "chúng", "anh", "chị", "em", "ông",
    "bà", "họ", "ai", "đây", "kia", "ấy", "nọ", "nữa", "luôn", "cũng", "hết", "gì",
    "sao", "ừ", "à", "ừm", "mà", "thôi", "rồi", "nha", "nhé", "vậy", "lăm",
    "thế", "đi", "lại", "đang", "cần", "chỉ", "kiểu", "như", "khi", "nào", "để",
    "trong", "ngoài", "trên", "dưới", "quá", "hơi", "nhưng", "tất", "cả", "đều",
    "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười"
}

# Function to convert time strings to days
def convert_time_to_days(time):
    match = re.search(r'(\d+)\s*(năm|tháng|tuần|ngày)', str(time).lower())
    if match:
        value, unit = int(match.group(1)), match.group(2)
        if unit == "năm":
            value *= 365
        elif unit == "tháng":
            value *= 30
        elif unit == "tuần":
            value *= 7
        return str(value)
    return "N/A"

# Function to remove stopwords from comments
def remove_stopwords(comment):
    words = comment.split()
    filtered_words = [word for word in words if word not in STOPWORDS]
    return " ".join(filtered_words)

# Function to clean and normalize comments
def clean_and_normalize_comment(comment):
    
    # Remove HTML tags and phone numbers
    comment = re.sub(r"\b\d{10,11}\b", '[hidden]', comment)
    
    # Remove special characters (. " ' \n ❤️)
    comment = re.sub(r"[\"'\n❤️]", ' ', comment)
    
    # Convert . to space
    comment = re.sub(r"\.", ' ', comment)
    
    # Remove extra spaces
    comment = re.sub(r"\s+'", ' ', comment)
    
    # Remove emojis and URLs
    comment = re.sub(r'http[s]?://\S+', '', comment)
    comment = re.sub(r'[\U00010000-\U0010ffff]', '', comment, flags=re.UNICODE)
    
    # Remove email addresses
    comment = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[hidden]', comment)
    
    # Lowercase and strip
    comment = comment.lower().strip()
    
    # Remove in-short words
    comment = normalize_text(comment)
    
    # Remove stopwords
    comment = remove_stopwords(comment)
    

    return comment

def normalize_text(text):
    # Remove in-short words
    replacements = {
        r"\bko\b": "không",
        r"\bk\b": "không",
        r"\bkh\b": "không",
        r"\bkhg\b": "không",
        r"\bkhg?\b": "không",
        r"\bkg\b": "không",
        r"\bko?\s+dc\b": "không được",
        r"\bđc\b": "được",
        r"\bdk\b": "được",
        r"\bdc\b": "được",
        r"\bbth\b": "bình thường",
        r"\bbt\b": "bình thường",
        r"\bsp\b": "sản phẩm",
        r"\bquạt đh\b": "quạt điều hòa",
        r"\bđmx\b": "điện máy xanh",
        r"\bdmx\b": "điện máy xanh",
        r"\bsdt\b": "số điện thoại",
        r"\bsđt\b": "số điện thoại",
        r"\bthanks\b": "cảm ơn",
        r"\btks\b": "cảm ơn",
        r"\bok\b": "ổn",
        r"\bokela\b": "ổn",
        r"\bsài\b": "xài",
        r"\bsài\b": "xài",
        r"\bsử dung\b": "sử dụng",
        r"\bđc\b": "được",
        r"\bhj\b": "",
        r"\bạ\b": "",
        r"\bạ\b": "",
        r"\btgian\b": "thời gian",
        r"\bremot\b": "remote",
        r"\btốt\b": "tốt",
        r"\btôt\b": "tốt",
        r"\btott?\b": "tốt",
        r"\bsx\b": "sản xuất",
        r"\bqc\b": "quảng cáo",
        r"\bhđ\b": "hoạt động",
        r"\bhư\b": "hỏng",
        r"\bngon\b": "tốt",
        r"\bmát lịm\b": "mát lạnh",
        r"\bmát lịm tim\b": "mát lạnh",
        r"\brẻ tiền\b": "rẻ",
        r"\bbố láo\b": "nói chuyện hỗn",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    return text

# Function to clean and normalize data
def clean_and_normalize_data():
    mode = mode_var.get()
    if mode == 'train':
        search_folders = ["raw_data_train_merged", "raw_data_train"]
        output_folder = "clean_data_train"
    else:
        search_folders = ["raw_data_test_merged", "raw_data_test"]
        output_folder = "clean_data_test"

    input_file_name = entry_input.get().strip()
    output_file_name = entry_output.get().strip()

    if input_file_name == "":
        result_label.config(text="Hãy nhập tên file input!", fg="red")
        return
    if output_file_name == "":
        result_label.config(text="Hãy nhập tên file output!", fg="red")
        return

    if not input_file_name.endswith('.csv'):
        input_file_name += ".csv"
    if not output_file_name.endswith('.csv'):
        output_file_name += ".csv"
        
    input_path = None
    for folder in search_folders:
        file_path = os.path.join(folder, f"{input_file_name}")
        if os.path.exists(file_path):
            input_path = file_path
            break
    if input_path is None:
        result_label.config(text=f"Không tìm thấy file {input_file_name} trong thư mục {search_folders}", fg="red")
        return

    try:
        df = pd.read_csv(input_path)
    except Exception as e:
        result_label.config(text=f"Lỗi khi đọc file CSV: {e}", fg="red")
        return


    # Clean and normalize data
    df = df.dropna(subset=['Author', 'Comment'])
    
    # Remove duplicates
    df['Shop'] = df['Shop'].fillna('Không rõ')
    
    # Convert 'Rating' to numeric and fill NaN with 0
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0).astype(int)
    
    # Apply cleaning function to 'Comment'
    df['Comment'] = df['Comment'].apply(clean_and_normalize_comment)
    df = df.dropna(subset=['Comment'])
    
    #
    df = df[df['Comment'].str.strip() != ""]
    
    # Convert 'Time' to days and remove rows with 'Time' as NaN
    df['Time'] = df['Time'].apply(convert_time_to_days)
    df = df[df['Time'] != "N/A"]

    if 'Index' in df.columns:
        df.drop(columns=['Index'], inplace=True)

    df = df.reset_index(drop=True)
    df.index += 1
    df.insert(0, 'Index', df.index)

    os.makedirs(output_folder, exist_ok=True)
    df.to_csv(os.path.join(output_folder, f"{output_file_name}"), index=False, encoding="utf-8")

    result_label.config(text=f"Đã làm sạch và chuẩn hóa dữ liệu, lưu vào file {output_file_name} trong thư mục {output_folder}", fg="green")

# GUI
root = tk.Tk()
root.title("Làm sạch và chuẩn hóa file CSV")

mode_var = tk.StringVar(value='train')  # default train

frame_mode = tk.Frame(root)
frame_mode.pack(pady=5)

tk.Label(frame_mode, text="Chọn loại dữ liệu:").pack(side="left")

radio_train = tk.Radiobutton(frame_mode, text="Train", variable=mode_var, value='train')
radio_train.pack(side="left", padx=10)

radio_test = tk.Radiobutton(frame_mode, text="Test", variable=mode_var, value='test')
radio_test.pack(side="left", padx=10)

tk.Label(root, text="Nhập tên file cần làm sạch và chuẩn hóa :").pack(pady=5)
entry_input = tk.Entry(root, width=40)
entry_input.pack(pady=5)

tk.Label(root, text="Nhập tên file sau khi xử lí :").pack(pady=5)
entry_output = tk.Entry(root, width=40)
entry_output.pack(pady=5)

tk.Button(root, text="Thực hiện", command=clean_and_normalize_data).pack(pady=5)

result_label = tk.Label(root, text="", width=80, height=20, justify="left", anchor="w")
result_label.pack(pady=5)

root.mainloop()
