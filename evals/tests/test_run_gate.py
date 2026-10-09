import json

from evals import run


def _report(recall, mrr):
    return {
        "suite": "tool_search",
        "primary": {"name": "recall@5", "value": recall},
        "secondary": {"mrr": mrr, "cjk_queries": 3},
        "n": 3,
    }


def test_the_baseline_records_the_gated_secondary_metric_only(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "BASELINES", tmp_path)

    run._evaluate(_report(0.8, 0.6), update=True)

    saved = json.loads((tmp_path / "tool_search.json").read_text())
    assert saved["secondary"] == {"mrr": 0.6}


def test_a_drop_in_mrr_fails_the_gate_even_when_recall_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "BASELINES", tmp_path)
    run._evaluate(_report(0.8, 0.6), update=True)

    assert run._evaluate(_report(0.8, 0.58), update=False) is True
    assert run._evaluate(_report(0.8, 0.5), update=False) is False
    assert run._evaluate(_report(0.7, 0.6), update=False) is False
