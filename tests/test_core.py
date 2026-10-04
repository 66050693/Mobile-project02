"""ทดสอบโดยไม่ต้องใช้ API key: python tests/test_core.py  (หรือ python -m pytest tests -q)"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
for k in ("GROQ_API_KEY", "YOUTUBE_API_KEY"):
    os.environ.pop(k, None)

import ai_service  # noqa: E402
import youtube_service  # noqa: E402
from dataset_service import apply_prices, chip_score, coverage, load_dataset, load_prices  # noqa: E402
from scoring_service import Request, filter_candidates, pros_cons, recommend, score, youtube_search_url  # noqa: E402
from thailand_filter import match_thai, model_key  # noqa: E402


def phones(rate=0.37, prices=None):
    return apply_prices(load_dataset(), prices if prices is not None else load_prices(), rate)


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, url, params=None, timeout=None, **_):
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
def test_model_key_normalises_variants():
    assert model_key("SAMSUNG Galaxy S26 5G", "samsung") == "galaxy s26"
    assert model_key("Samsung Galaxy S26 Ultra (12GB RAM + 512GB)", "samsung") == "galaxy s26 ultra"
    assert model_key("Galaxy S26+", "Samsung") == model_key("Samsung Galaxy S26 Plus", "samsung")
    assert model_key("Xiaomi Redmi Note 15 Pro 5G", "xiaomi") == "redmi note 15 pro"
    assert match_thai("oppo", "Oppo Find X9 5G") == ("OPPO", "Find X9")
    assert match_thai("oneplus", "OnePlus 17") is None  # ต้องไม่ไปจับคู่กับ "Xiaomi 17"
    assert match_thai("samsung", "Samsung Galaxy S26 FE") is None


def test_chip_score():
    assert chip_score("Snapdragon 8 Elite Gen 5") == 95 and chip_score("Snapdragon 8Elite") == 95
    assert chip_score("Apple A19 Pro") == 95 and chip_score("Bionic A18") == 90
    assert chip_score("Dimensity 7300") == 52 and chip_score("Octa Core Processor") is None


def test_dataset_loads_and_merges_variants():
    d = phones()
    assert d["name"].is_unique and len(d) > 500
    s26u = d[d["name"] == "Samsung Galaxy S26 Ultra"].iloc[0]
    assert s26u["variants"] == 3 and s26u["price_inr"] <= s26u["price_inr_max"] and s26u["in_thailand"]
    cov = coverage(d)
    assert cov["thai_matched"] >= 18 and cov["catalog_models"] == 42
    assert set(d["price_kind"]) <= {"ประมาณจากราคาอินเดีย", "ราคาไทย"}
    assert (d.loc[~d["in_thailand"], "price_kind"] == "ประมาณจากราคาอินเดีย").all()


def test_thai_price_overrides_estimate():
    p = pd.DataFrame({"brand": ["Samsung"], "model": ["Galaxy A57"], "price_thb": [13999.0], "updated": ["2026-10-01"],
                      "source": ["samsung.com/th"]})
    d = phones(prices=p)
    row = d[d["name"] == "Samsung Galaxy A57"].iloc[0]
    assert row["price_thb"] == 13999 and row["price_kind"] == "ราคาไทย"
    assert coverage(d)["thai_priced"] >= 1
    assert phones(rate=0.5).loc[lambda x: x["name"] == "Samsung Galaxy S26 FE", "price_thb"].iloc[0] > \
        phones(rate=0.3).loc[lambda x: x["name"] == "Samsung Galaxy S26 FE", "price_thb"].iloc[0]


def test_filters():
    d = phones()
    req = Request(budget_min=10000, budget_max=20000, thailand_only=False, need_5g=True, need_nfc=True, min_storage=256)
    c = filter_candidates(d, req)
    assert len(c) > 0 and c["price_thb"].between(10000, 20000).all() and c["has_5g"].all() and c["has_nfc"].all()
    assert filter_candidates(d, Request(budget_max=99999, thailand_only=True))["in_thailand"].all()
    assert filter_candidates(d, Request(budget_max=99999, brands=["Apple"], thailand_only=False))["brand"].eq("Apple").all()


def test_scoring_follows_use_case():
    d = phones()
    game, n = recommend(d, Request(budget_max=25000, use_case="เล่นเกม", thailand_only=False))
    assert n > 50 and len(game) == 5 and game["score"].is_monotonic_decreasing
    pool = score(filter_candidates(d, Request(budget_max=25000, thailand_only=False)), Request(budget_max=25000, thailand_only=False))
    assert game["perf_score"].mean() > pool["perf_score"].mean()
    cam, _ = recommend(d, Request(budget_max=25000, use_case="ถ่ายรูป/วิดีโอ", thailand_only=False))
    assert cam["camera_mp"].mean() > pool["camera_mp"].mean()
    bat, _ = recommend(d, Request(budget_max=25000, use_case="แบตอึด/เดินทาง", thailand_only=False))
    assert bat["battery_mah"].mean() > pool["battery_mah"].mean()


def test_missing_data_is_penalised_and_reported():
    d = filter_candidates(phones(), Request(budget_max=25000, thailand_only=False)).copy()
    req = Request(budget_max=25000, use_case="เล่นเกม", thailand_only=False)
    top = score(d, req).iloc[0]["name"]
    full = score(d, req).set_index("name").loc[top, "score"]
    d.loc[d["name"] == top, ["perf_score", "refresh_hz"]] = None
    part = score(d, req).set_index("name").loc[top]
    assert part["score"] < full
    assert any("ไม่มีข้อมูล" in c for c in pros_cons(part, req)[1])


def test_ai_validate_and_fallback():
    picks = [{"model": "OPPO Find X9s", "score": 90, "ข้อดีจากการคำนวณ": ["a"], "ข้อเสียจากการคำนวณ": []},
             {"model": "OPPO A6", "score": 70, "ข้อดีจากการคำนวณ": [], "ข้อเสียจากการคำนวณ": ["b"]}]
    out = ai_service.validate({"summary": "s", "items": [
        {"model": "iPhone 99 Ultra", "why": "fake", "pros": [], "cons": []},
        {"model": "oppo find x9s", "why": "ok", "pros": ["x"], "cons": ["y"]}]}, picks)
    assert [i["model"].lower() for i in out["items"]] == ["oppo find x9s", "oppo a6"] and out["dropped"] == 1
    assert ai_service.explain({}, picks)["source"] == "rules"
    d = phones()
    req = Request(budget_max=20000)
    top, _ = recommend(d, req)
    row = ai_service.compact(top.iloc[0], *pros_cons(top.iloc[0], req))
    json.dumps(row, ensure_ascii=False)  # ต้องแปลงเป็น JSON ได้ (ไม่มีชนิด numpy)


def test_youtube():
    assert youtube_search_url("Samsung Galaxy S26").startswith("https://www.youtube.com/results?search_query=")
    assert youtube_service.review_videos("x") == []
    os.environ["YOUTUBE_API_KEY"] = "k"
    http = FakeHTTP([Resp(200, {"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "รีวิว &amp; ทดสอบ",
                                                                                   "channelTitle": "ช่อง"}}]})])
    v = youtube_service.review_videos("Samsung Galaxy S26", session=http)
    assert v[0]["url"].endswith("abc") and v[0]["title"] == "รีวิว & ทดสอบ"
    assert youtube_service.review_videos("x", session=FakeHTTP([Resp(500, {})])) == []
    os.environ.pop("YOUTUBE_API_KEY")



# ---------------------------------------------------------------------------
# ฟีเจอร์ใหม่: รูป, แปลงคำขอ, ทำไมไม่ใช่รุ่นนี้, เพิ่มงบ, เส้นความคุ้มค่า, แชท
# ---------------------------------------------------------------------------
from assistant_service import ChatTools, apply_parsed, parse_rules  # noqa: E402
from dataset_service import apply_images  # noqa: E402
from insight_service import budget_upgrade, value_frontier, why_not  # noqa: E402


def test_images_loaded_for_known_models():
    d = apply_images(phones())
    assert d.loc[d["name"] == "Apple iPhone 17", "image"].iloc[0].startswith("https://")
    assert (d["image"] == "").sum() > 0  # รุ่นที่ไม่มีรูปเป็นค่าว่าง (ใช้รูปสำรอง)


def test_parse_rules_thai_phrases():
    brands = ["Apple", "Samsung", "OPPO", "vivo", "Xiaomi"]
    p = parse_rules("อยากได้มือถือไม่เกินหมื่น เล่น ROV ลื่น แบตอึด", brands)
    assert p.budget_max == 10000 and p.use_case == "เล่นเกม" and "แบตเตอรี่" in p.priorities
    p = parse_rules("งบ 1.5 หมื่น ถ่ายรูปสวย ขอ samsung หรือ oppo 256GB", brands)
    assert p.budget_max == 15000 and p.brands == ["OPPO", "Samsung"] and p.min_storage == 256
    p = parse_rules("ซื้อให้แม่ งบ 8000-12000 บาท มี NFC", brands)
    assert (p.budget_min, p.budget_max) == (8000, 12000) and p.need_nfc and p.use_case == "ผู้สูงอายุ/ใช้ง่าย"
    p = parse_rules("15k เล่นเกม 120hz 5G", brands)
    assert p.budget_max == 15000 and p.need_5g and "จอลื่น" in p.priorities
    req = apply_parsed(Request(budget_max=20000, use_case="ทำงาน"), parse_rules("ไอโฟน", brands))
    assert req.budget_max == 20000 and req.use_case == "ทำงาน" and req.brands == ["Apple"]


def test_why_not_explains_filters_and_rank():
    d = phones()
    req = Request(budget_max=20000, use_case="เล่นเกม", thailand_only=False, need_nfc=True)
    w = why_not(d, req, "Apple iPhone 16")
    assert w["status"] == "filtered" and any("เกินงบ" in r for r in w["reasons"])
    ranked = score(filter_candidates(d, req), req)
    low = ranked.iloc[20]["name"]
    w = why_not(d, req, low)
    assert w["status"] == "ranked" and w["rank"] == 21 and w["reasons"]
    assert why_not(d, req, ranked.iloc[0]["name"])["status"] == "in_top"
    assert why_not(d, req, "ไม่มีรุ่นนี้")["status"] == "not_found"


def test_budget_upgrade_and_frontier():
    d = phones()
    found = False
    for budget in (8000, 10000, 12000, 15000, 20000, 25000):
        for uc in ("เล่นเกม", "ถ่ายรูป/วิดีโอ", "ใช้งานทั่วไป/เรียน"):
            for u in budget_upgrade(d, Request(budget_max=budget, use_case=uc, thailand_only=False)):
                found = True
                assert budget < u["price"] <= budget + u["extra"] and u["gain"] >= 5
    assert found
    ranked = score(filter_candidates(d, Request(budget_max=20000, thailand_only=False)), Request(budget_max=20000, thailand_only=False))
    f = ranked[value_frontier(ranked)]
    assert 0 < len(f) < len(ranked)
    cheapest = ranked.loc[ranked["price_thb"].idxmin()]
    assert bool(value_frontier(ranked)[ranked["price_thb"].idxmin()]) or pd.isna(cheapest["spec_score"])
    for _, r in f.iterrows():  # ไม่มีรุ่นที่ถูกกว่าและคะแนนสเปกสูงกว่ารุ่นบนเส้น
        assert not ((ranked["price_thb"] < r["price_thb"]) & (ranked["spec_score"] > r["spec_score"])).any()


def test_chat_tools_and_agent_loop():
    import types as pytypes
    d = phones()
    req = Request(budget_max=20000, use_case="เล่นเกม", thailand_only=False)
    tools = ChatTools(d, req)
    assert len(tools.run("get_ranking", {"n": 3})["อันดับ"]) == 3
    assert tools.run("get_phone", {"name": "iphone 16"})["name"] == "Apple iPhone 16"
    assert "error" in tools.run("nope", {})
    json.dumps(tools.run("compare", {"names": ["OPPO A6", "vivo X300"]}), ensure_ascii=False)

    import assistant_service
    call = {"id": "c1", "type": "function", "function": {"name": "get_ranking", "arguments": '{"n": 2}'}}
    replies = [{"role": "assistant", "content": None, "tool_calls": [call]},
               {"role": "assistant", "content": "อันดับ 1 คือ ..."}]
    sent = []
    assistant_service._generate = lambda messages, tools=None: (sent.append(list(messages)), replies.pop(0))[1]
    out = assistant_service.chat("อันดับ 1 คืออะไร", [], tools)
    assert out["answer"] == "อันดับ 1 คือ ..." and out["trace"][0]["tool"] == "get_ranking"
    assert sent[1][-1]["role"] == "tool" and sent[1][-1]["tool_call_id"] == "c1"


def test_groq_client_schema_and_errors():
    import llm_client
    s = llm_client.json_schema({"type": "OBJECT", "properties": {"x": {"type": "INTEGER", "nullable": True}}})
    assert s == {"type": "object", "properties": {"x": {"type": ["integer", "null"]}}}
    assert "GROQ_API_KEY" in llm_client._friendly(401, "")
    try:
        llm_client.complete([{"role": "user", "content": "hi"}])
        raise AssertionError("ต้อง error เมื่อไม่มี key")
    except llm_client.LLMError:
        pass


# ---------------------------------------------------------------------------
# Machine Learning
# ---------------------------------------------------------------------------
from ml_service import apply_ml, deal_label, segment_phones, train_price_model  # noqa: E402

_ML = {}


def ml():
    if not _ML:
        d = phones()
        _ML.update(d=d, m=train_price_model(d), s=segment_phones(d))
    return _ML["d"], _ML["m"], _ML["s"]


def test_price_model_beats_baseline():
    d, m, _ = ml()
    assert m.n_train + m.n_test == len(d) and m.n_test > 100
    assert m.metrics["R2"] > 0.7 and m.metrics["MAE"] < m.baseline["MAE"] * 0.6
    assert abs(m.importance["percent"].sum() - 100) < 1e-6
    assert m.fair_inr.notna().all() and len(m.fair_inr) == len(d)


def test_deal_labels_and_scoring_use_ml():
    d, m, s = ml()
    out = apply_ml(d, m, s, 0.37)
    assert deal_label(0.8).startswith("ถูกกว่าสเปก") and deal_label(1.3).startswith("แพงกว่าสเปก")
    assert deal_label(1.0) == "ราคาสมเหตุสมผล"
    req = Request(budget_max=20000, thailand_only=False)
    ranked = score(filter_candidates(out, req), req)
    ratio = ranked["fair_price_thb"] / ranked["price_thb"]
    assert ranked.loc[ratio.idxmax(), "s_value"] == 100  # คุ้มที่สุดตาม ML ได้คะแนนความคุ้มค่าเต็ม


def test_segments():
    d, _, s = ml()
    assert 4 <= s.k <= 7 and s.labels.nunique() == s.k and s.labels.notna().all()
    assert s.profile["price_inr"].is_monotonic_increasing and s.profile["count"].min() >= 5
    assert s.profile["count"].sum() == len(d) and len(s.coords) == len(d)

if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception:
                failed += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name)
    sys.exit(1 if failed else 0)
