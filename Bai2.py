import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import PorterStemmer, WordNetLemmatizer
    from nltk.tokenize import word_tokenize
except ImportError as exc:
    raise SystemExit(
        "Thiếu thư viện nltk. Cài bằng lệnh: python -m pip install nltk"
    ) from exc

VI_STOPWORDS = {
    "và",
    "là",
    "có",
    "cho",
    "của",
    "một",
    "những",
    "các",
    "được",
    "đang",
    "trong",
    "khi",
    "thì",
    "đã",
    "này",
    "đó",
    "rất",
    "với",
    "ở",
    "vì",
    "ra",
    "nên",
    "như",
    "tôi",
    "mình",
    "bạn",
    "anh",
    "chị",
    "em",
    "lại",
    "cũng",
    "chỉ",
    "để",
}


EN_CONTRACTIONS = {
    "i'm": "i am",
    "can't": "cannot",
    "won't": "will not",
    "don't": "do not",
    "didn't": "did not",
    "isn't": "is not",
    "it's": "it is",
    "you're": "you are",
    "they're": "they are",
    "we're": "we are",
    "i've": "i have",
    "that's": "that is",
}

COMMON_MISSPELLINGS = {
    "inttroduction": "introduction",
    "electrcity": "electricity",
    "langauage": "language",
    "mussage": "message",
    "sirvice": "service",
    "wierd": "weird",
    "teh": "the",
    "recieve": "receive",
}


def ensure_nltk_resource(resource: str, download_name: str) -> None:
    try:
        nltk.data.find(resource)
    except LookupError:
        nltk.download(download_name, quiet=True)


def setup_nltk() -> None:
    ensure_nltk_resource("corpora/stopwords", "stopwords")
    ensure_nltk_resource("tokenizers/punkt", "punkt")
    try:
        ensure_nltk_resource("tokenizers/punkt_tab", "punkt_tab")
    except Exception:
        pass
    ensure_nltk_resource("corpora/wordnet", "wordnet")
    ensure_nltk_resource("corpora/omw-1.4", "omw-1.4")


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8", "utf-8-sig", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def load_dmx_data(root: Path) -> pd.DataFrame:
    records: List[Dict[str, object]] = []
    csv_files = sorted(root.glob("*.csv"))
    for csv_file in csv_files:
        df = read_csv_with_fallback(csv_file)
        if "Comment" not in df.columns:
            continue
        text_series = df["Comment"].fillna("").astype(str)
        for row_idx, text in enumerate(text_series):
            records.append(
                {
                    "doc_id": f"dmx_{csv_file.stem}_{row_idx}",
                    "source": "dmx",
                    "language": "vi",
                    "dataset_file": str(csv_file),
                    "raw_text": text,
                }
            )
    return pd.DataFrame(records)


def load_steam_data(root: Path) -> pd.DataFrame:
    records: List[Dict[str, object]] = []
    csv_files = sorted(root.glob("**/reviews.csv"))
    for csv_file in csv_files:
        df = read_csv_with_fallback(csv_file)
        if "review_text" not in df.columns:
            continue
        text_series = df["review_text"].fillna("").astype(str)
        game_key = csv_file.parent.name
        for row_idx, text in enumerate(text_series):
            records.append(
                {
                    "doc_id": f"steam_{game_key}_{row_idx}",
                    "source": "steam",
                    "language": "en",
                    "dataset_file": str(csv_file),
                    "raw_text": text,
                }
            )
    return pd.DataFrame(records)


def remove_punctuation(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text)


def normalize_text(text: str, lang: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"https?://\S+|www\.\S+", " ", normalized)
    if lang == "en":
        for short, full in EN_CONTRACTIONS.items():
            normalized = normalized.replace(short, full)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def remove_stopwords_text(text: str, lang: str, en_stopwords: set) -> str:
    tokens = text.split()
    if lang == "en":
        filtered = [tok for tok in tokens if tok not in en_stopwords]
    else:
        filtered = [tok for tok in tokens if tok not in VI_STOPWORDS]
    return " ".join(filtered)


def spell_correct_text(
    text: str,
    lang: str,
    correction_cache: Dict[str, str],
) -> Tuple[str, int]:
    if lang != "en":
        return text, 0
    corrected_tokens: List[str] = []
    changed_count = 0
    tokens = text.split()
    lookup_tokens = [tok for tok in tokens if tok not in correction_cache]
    for tok in lookup_tokens:
        lowered = tok.lower()
        if lowered in COMMON_MISSPELLINGS:
            correction_cache[tok] = COMMON_MISSPELLINGS[lowered]
        else:
            correction_cache[tok] = re.sub(r"([a-z])\1{2,}", r"\1\1", tok)

    for tok in tokens:
        corrected = correction_cache.get(tok, tok)
        corrected_tokens.append(corrected)
        if corrected != tok:
            changed_count += 1
    return " ".join(corrected_tokens), changed_count


def tokenize_text(text: str, lang: str) -> List[str]:
    if not text:
        return []
    if lang == "en":
        return [tok for tok in word_tokenize(text) if tok.strip()]
    return [tok for tok in text.split() if tok.strip()]


def stem_tokens(tokens: List[str], lang: str, stemmer: PorterStemmer) -> List[str]:
    if lang != "en":
        return tokens
    return [stemmer.stem(tok) for tok in tokens]


def lemmatize_tokens(
    tokens: List[str], lang: str, lemmatizer: WordNetLemmatizer
) -> List[str]:
    if lang != "en":
        return tokens
    return [lemmatizer.lemmatize(tok) for tok in tokens]


def get_top_tokens(token_lists: Iterable[List[str]], top_n: int = 20) -> List[Tuple[str, int]]:
    counter: Counter = Counter()
    for tokens in token_lists:
        counter.update(tokens)
    return counter.most_common(top_n)


def build_raw_stats(df: pd.DataFrame) -> Dict[str, object]:
    temp = df.copy()
    temp["raw_words"] = temp["raw_text"].fillna("").astype(str).apply(lambda x: len(x.split()))
    temp["raw_chars"] = temp["raw_text"].fillna("").astype(str).str.len()
    raw_tokens = (
        temp["raw_text"]
        .fillna("")
        .astype(str)
        .str.lower()
        .apply(remove_punctuation)
        .str.split()
    )
    return {
        "total_documents": int(len(temp)),
        "documents_by_source": temp["source"].value_counts().to_dict(),
        "documents_by_language": temp["language"].value_counts().to_dict(),
        "missing_or_empty_raw_text": int((temp["raw_text"].fillna("").str.strip() == "").sum()),
        "avg_raw_characters": float(temp["raw_chars"].mean()),
        "avg_raw_words": float(temp["raw_words"].mean()),
        "median_raw_words": float(temp["raw_words"].median()),
        "raw_vocabulary_size": int(len(set(tok for tokens in raw_tokens for tok in tokens))),
        "top_20_raw_tokens": get_top_tokens(raw_tokens, top_n=20),
    }


def build_processed_stats(df: pd.DataFrame, raw_vocab_size: int) -> Dict[str, object]:
    final_vocab = len(set(tok for tokens in df["tokens_lemmatized"] for tok in tokens))
    avg_tokens = float(df["tokens"].apply(len).mean()) if len(df) else 0.0
    avg_final_tokens = float(df["tokens_lemmatized"].apply(len).mean()) if len(df) else 0.0
    empty_final = int((df["final_text"].fillna("").str.strip() == "").sum())
    by_source = {}
    for source, gdf in df.groupby("source"):
        by_source[source] = {
            "documents": int(len(gdf)),
            "avg_tokens_after_tokenize": float(gdf["tokens"].apply(len).mean()),
            "avg_tokens_final": float(gdf["tokens_lemmatized"].apply(len).mean()),
            "top_10_final_tokens": get_top_tokens(gdf["tokens_lemmatized"], top_n=10),
        }
    reduction = 0.0
    if raw_vocab_size > 0:
        reduction = (raw_vocab_size - final_vocab) / raw_vocab_size * 100.0
    return {
        "processed_documents": int(len(df)),
        "empty_after_processing": empty_final,
        "avg_tokens_after_tokenize": avg_tokens,
        "avg_tokens_final": avg_final_tokens,
        "processed_vocabulary_size": int(final_vocab),
        "vocabulary_reduction_percent": reduction,
        "by_source": by_source,
    }


def process_dataset(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object]]:
    en_stopwords = set(stopwords.words("english"))
    stemmer = PorterStemmer()
    lemmatizer = WordNetLemmatizer()
    correction_cache: Dict[str, str] = {}

    processed_rows: List[Dict[str, object]] = []
    corrected_token_total = 0
    failed_rows = 0

    for row in df.to_dict(orient="records"):
        try:
            raw_text = str(row["raw_text"] or "")
            lang = row["language"]

            text_lower = raw_text.lower()
            text_no_punct = remove_punctuation(text_lower)
            text_no_stop = remove_stopwords_text(text_no_punct, lang, en_stopwords)
            text_normalized = normalize_text(text_no_stop, lang)
            text_spell, changed_count = spell_correct_text(
                text_normalized, lang, correction_cache
            )
            corrected_token_total += changed_count

            tokens = tokenize_text(text_spell, lang)
            tokens_stem = stem_tokens(tokens, lang, stemmer)
            tokens_lemma = lemmatize_tokens(tokens, lang, lemmatizer)
            final_text = " ".join(tokens_lemma)

            processed_rows.append(
                {
                    **row,
                    "text_lower": text_lower,
                    "text_no_punctuation": text_no_punct,
                    "text_no_stopwords": text_no_stop,
                    "text_normalized": text_normalized,
                    "text_spell_corrected": text_spell,
                    "tokens": tokens,
                    "tokens_stemmed": tokens_stem,
                    "tokens_lemmatized": tokens_lemma,
                    "final_text": final_text,
                }
            )
        except Exception:
            failed_rows += 1

    processed_df = pd.DataFrame(processed_rows)
    processing_stats = {
        "spell_correction_method": "rule_based_dictionary",
        "spelling_corrections_applied": int(corrected_token_total),
        "failed_rows": int(failed_rows),
    }
    return processed_df, processing_stats


def save_outputs(
    processed_df: pd.DataFrame,
    raw_stats: Dict[str, object],
    processed_stats: Dict[str, object],
    processing_stats: Dict[str, object],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    processed_csv = output_dir / "processed_reviews.csv"
    export_df = processed_df.copy()
    for col in ("tokens", "tokens_stemmed", "tokens_lemmatized"):
        export_df[col] = export_df[col].apply(lambda x: " ".join(x))
    export_df.to_csv(processed_csv, index=False, encoding="utf-8-sig")

    (output_dir / "raw_stats.json").write_text(
        json.dumps(raw_stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "processed_stats.json").write_text(
        json.dumps(processed_stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "processing_stats.json").write_text(
        json.dumps(processing_stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline tiền xử lý văn bản cho dữ liệu DMX + Steam."
    )
    parser.add_argument(
        "--dmx-dir",
        default="raw_data_all_fans",
        help="Thư mục chứa dữ liệu CSV từ DMX.",
    )
    parser.add_argument(
        "--steam-dir",
        default="steam_darkest_dungeon_reviews",
        help="Thư mục gốc chứa dữ liệu Steam (reviews.csv).",
    )
    parser.add_argument(
        "--output-dir",
        default="processed_output",
        help="Thư mục xuất dữ liệu và thống kê.",
    )
    args = parser.parse_args()

    setup_nltk()

    dmx_df = load_dmx_data(Path(args.dmx_dir))
    steam_df = load_steam_data(Path(args.steam_dir))
    all_df = pd.concat([dmx_df, steam_df], ignore_index=True)

    raw_stats = build_raw_stats(all_df)
    processed_df, processing_stats = process_dataset(all_df)
    processed_stats = build_processed_stats(processed_df, raw_stats["raw_vocabulary_size"])

    save_outputs(
        processed_df=processed_df,
        raw_stats=raw_stats,
        processed_stats=processed_stats,
        processing_stats=processing_stats,
        output_dir=Path(args.output_dir),
    )

    print("Da hoan tat pipeline.")
    print(f"So van ban goc: {raw_stats['total_documents']}")
    print(f"So van ban sau xu ly: {processed_stats['processed_documents']}")
    print(f"So van ban rong sau xu ly: {processed_stats['empty_after_processing']}")
    print(f"Tu vung goc: {raw_stats['raw_vocabulary_size']}")
    print(f"Tu vung sau xu ly: {processed_stats['processed_vocabulary_size']}")
    print(f"Giam tu vung (%): {processed_stats['vocabulary_reduction_percent']:.2f}")
    print(f"Da xuat ket qua tai: {args.output_dir}")


if __name__ == "__main__":
    main()
