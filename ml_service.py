"""Machine Learning จาก dataset มือถือ (train จริงทุกครั้งที่แอปเริ่ม แล้ว cache ไว้)

1) Random Forest Regression ทำนาย "ราคาที่ควรเป็น" จากสเปก
   - เป้าหมาย: log(ราคาอินเดีย) เพราะราคากระจายเบ้มาก (5 พัน ถึง 4 แสนรูปี)
   - ประเมินผล: แบ่ง train/test 80/20 วัด MAE, RMSE, MAPE, R² เทียบกับ baseline (ทายค่ามัธยฐาน)
   - ราคายุติธรรมของแต่ละรุ่นใช้ out-of-fold prediction (5-fold) รุ่นนั้นจึงไม่เคยถูกใช้สอนโมเดลที่ทายตัวเอง
   - อธิบายโมเดล: permutation importance บนชุดทดสอบ
2) K-Means Clustering แบ่งกลุ่มมือถือตามสเปกและราคา เลือกจำนวนกลุ่มด้วย silhouette score แล้วตั้งชื่อกลุ่มอัตโนมัติ
ไม่พึ่ง Streamlit เพื่อให้ทดสอบแยกได้
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, silhouette_score
from sklearn.model_selection import KFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
NUMERIC_FEATURES = {
    "perf_score": "ประสิทธิภาพชิป", "ram_gb": "RAM", "storage_gb": "ความจุ", "camera_mp": "กล้องหลัก",
    "front_mp": "กล้องหน้า", "battery_mah": "แบตเตอรี่", "charging_w": "ชาร์จเร็ว", "display_in": "ขนาดจอ",
    "refresh_hz": "รีเฟรชเรต", "rear_cams": "จำนวนกล้องหลัง",
}
FLAG_FEATURES = {"has_5g": "5G", "has_nfc": "NFC", "has_ir": "IR Blaster"}
MIN_BRAND_ROWS = 8          # แบรนด์ที่มีน้อยกว่านี้รวมเป็น "อื่นๆ"
DEAL_CHEAP, DEAL_PRICEY = 0.85, 1.15
CLUSTER_FEATURES = ["perf_score", "ram_gb", "storage_gb", "camera_mp", "battery_mah", "charging_w", "refresh_hz",
                    "log_price"]


# ---------------------------------------------------------------------------
# เตรียมฟีเจอร์
# ---------------------------------------------------------------------------
def make_features(df: pd.DataFrame, brands: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """ตารางฟีเจอร์ตัวเลขล้วน: สเปก + ธง 5G/NFC/IR + iOS + แบรนด์แบบ one-hot"""
    X = df[list(NUMERIC_FEATURES)].apply(pd.to_numeric, errors="coerce").astype(float)
    for col in FLAG_FEATURES:
        X[col] = df[col].astype(float)
    X["is_ios"] = df["os"].astype(str).str.lower().str.contains("ios").astype(float)
    fam = df["family"].astype(str)
    if brands is None:
        counts = fam.value_counts()
        brands = sorted(counts[counts >= MIN_BRAND_ROWS].index)
    for b in brands:
        X[f"brand_{b}"] = (fam == b).astype(float)
    return X, brands


def feature_group(col: str) -> str:
    if col.startswith("brand_"):
        return "แบรนด์"
    if col == "is_ios":
        return "ระบบ iOS"
    return {**NUMERIC_FEATURES, **FLAG_FEATURES}.get(col, col)


# ---------------------------------------------------------------------------
# 1) Regression: ราคาที่ควรเป็น
# ---------------------------------------------------------------------------
@dataclass
class PriceModel:
    metrics: dict
    baseline: dict
    importance: pd.DataFrame
    test_pred: pd.DataFrame          # ราคาจริง vs ทำนาย บนชุดทดสอบ (INR)
    fair_inr: pd.Series              # ราคายุติธรรม (out-of-fold) ทุกรุ่น index ตรงกับ df
    n_train: int
    n_test: int
    features: list[str] = field(default_factory=list)


def _model() -> object:
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                         RandomForestRegressor(n_estimators=200, min_samples_leaf=2, max_features=0.5,
                                               random_state=SEED, n_jobs=-1))


def _scores(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {"MAE": float(mean_absolute_error(y_true, y_pred)),
            "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "MAPE": float(np.mean(np.abs(y_pred - y_true) / y_true) * 100),
            "R2": float(r2_score(y_true, y_pred))}


def train_price_model(df: pd.DataFrame) -> PriceModel:
    d = df[df["price_inr"] > 0].copy()
    X, _ = make_features(d)
    y = np.log(d["price_inr"].to_numpy(float))
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED)
    model = _model().fit(X_tr, y_tr)
    pred_te = np.exp(model.predict(X_te))
    true_te = np.exp(y_te)
    metrics = _scores(true_te, pred_te)
    baseline = _scores(true_te, np.full_like(true_te, np.exp(np.median(y_tr))))

    perm = permutation_importance(model, X_te, y_te, n_repeats=5, random_state=SEED, n_jobs=-1)
    imp = pd.DataFrame({"feature": X.columns, "value": np.clip(perm.importances_mean, 0, None)})
    imp["group"] = imp["feature"].map(feature_group)
    imp = imp.groupby("group", as_index=False)["value"].sum()
    imp["percent"] = imp["value"] / imp["value"].sum() * 100 if imp["value"].sum() > 0 else 0
    imp = imp.sort_values("percent", ascending=False).reset_index(drop=True)

    oof = cross_val_predict(_model(), X, y, cv=KFold(5, shuffle=True, random_state=SEED))
    test_pred = pd.DataFrame({"name": d.loc[X_te.index, "name"].to_numpy(), "actual": true_te, "predicted": pred_te})
    return PriceModel(metrics=metrics, baseline=baseline, importance=imp[["group", "percent"]], test_pred=test_pred,
                      fair_inr=pd.Series(np.exp(oof), index=d.index), n_train=len(X_tr), n_test=len(X_te),
                      features=list(X.columns))


def deal_label(ratio: float) -> str:
    if ratio is None or pd.isna(ratio):
        return ""
    if ratio <= DEAL_CHEAP:
        return f"ถูกกว่าสเปก {round((1 - ratio) * 100)}%"
    if ratio >= DEAL_PRICEY:
        return f"แพงกว่าสเปก {round((ratio - 1) * 100)}%"
    return "ราคาสมเหตุสมผล"


# ---------------------------------------------------------------------------
# 2) Clustering: กลุ่มมือถือ
# ---------------------------------------------------------------------------
@dataclass
class Segments:
    labels: pd.Series                # ชื่อกลุ่มของแต่ละรุ่น index ตรงกับ df
    profile: pd.DataFrame            # ค่าเฉลี่ยของแต่ละกลุ่ม
    coords: pd.DataFrame             # PCA 2 มิติ สำหรับกราฟ
    k: int
    silhouette: dict                 # k → silhouette score


TIER_NAMES = ["รุ่นประหยัด", "ระดับกลาง", "ระดับกลางบน", "พรีเมียม", "เรือธง", "เรือธงสุดหรู"]
STRENGTH_NAMES = {"perf_score": "สายแรง", "camera_mp": "สายกล้อง", "battery_mah": "สายแบตอึด",
                  "charging_w": "สายชาร์จไว", "storage_gb": "สายความจุเยอะ", "refresh_hz": "สายจอลื่น"}


def _name_clusters(profile: pd.DataFrame, z: pd.DataFrame) -> dict[int, str]:
    """ตั้งชื่อจากระดับราคาเฉลี่ย + จุดเด่นที่สุดของกลุ่ม (เทียบค่ามาตรฐาน z)"""
    order = profile["price_inr"].rank(method="first").astype(int) - 1
    tiers = {c: TIER_NAMES[min(int(order[c] * len(TIER_NAMES) / len(profile)), len(TIER_NAMES) - 1)] for c in profile.index}
    names, used = {}, set()
    for c in profile.index:
        strengths = z.loc[c, list(STRENGTH_NAMES)].sort_values(ascending=False)
        for col in strengths.index:
            candidate = f"{tiers[c]} {STRENGTH_NAMES[col]}"
            if candidate not in used:
                break
        names[c] = candidate
        used.add(candidate)
    return names


def segment_phones(df: pd.DataFrame, k_range: range = range(4, 8)) -> Segments:
    d = df.copy()
    d["log_price"] = np.log(d["price_inr"])
    X = d[CLUSTER_FEATURES].apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median())
    Z = StandardScaler().fit_transform(X)
    sil = {}
    best_k, best_s, best_model = None, -1, None
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(Z)
        s = float(silhouette_score(Z, km.labels_, sample_size=min(len(Z), 2000), random_state=SEED))
        sil[k] = round(s, 3)
        if s > best_s:
            best_k, best_s, best_model = k, s, km
    labels = pd.Series(best_model.labels_, index=d.index)
    raw = d.assign(cluster=labels)
    profile = raw.groupby("cluster").agg(
        price_inr=("price_inr", "median"), perf_score=("perf_score", "mean"), ram_gb=("ram_gb", "median"),
        storage_gb=("storage_gb", "median"), camera_mp=("camera_mp", "median"), battery_mah=("battery_mah", "median"),
        charging_w=("charging_w", "median"), refresh_hz=("refresh_hz", "median"), count=("name", "size"))
    zprof = pd.DataFrame(Z, index=d.index, columns=CLUSTER_FEATURES).assign(cluster=labels).groupby("cluster").mean()
    names = _name_clusters(profile, zprof)
    profile.insert(0, "segment", profile.index.map(names))
    pcs = PCA(n_components=2, random_state=SEED).fit_transform(Z)
    coords = pd.DataFrame({"x": pcs[:, 0], "y": pcs[:, 1], "segment": labels.map(names).to_numpy(),
                           "name": d["name"].to_numpy()}, index=d.index)
    return Segments(labels=labels.map(names), profile=profile.sort_values("price_inr").reset_index(drop=True),
                    coords=coords, k=best_k, silhouette=sil)


# ---------------------------------------------------------------------------
# รวมผล ML เข้ากับตารางมือถือ
# ---------------------------------------------------------------------------
def apply_ml(phones: pd.DataFrame, model: PriceModel, seg: Segments, inr_to_thb: float) -> pd.DataFrame:
    """เพิ่มคอลัมน์ fair_price_thb, deal_ratio, deal_label, segment (index ต้องตรงกับตอน train)"""
    out = phones.copy()
    out["fair_price_thb"] = (model.fair_inr.reindex(out.index) * inr_to_thb).round(-1)
    out["deal_ratio"] = out["price_thb"] / out["fair_price_thb"]
    out["deal_label"] = out["deal_ratio"].map(deal_label)
    out["segment"] = seg.labels.reindex(out.index).fillna("")
    return out
