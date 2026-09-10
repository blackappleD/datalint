"""性能验证 (SC-005): 10 万行输入 60 秒内处理完成."""

import json
import time

import pytest

from datalint import cli


@pytest.mark.slow
def test_100k_lines_under_60_seconds(tmp_path):
    path = tmp_path / "big.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(100_000):
            if i % 10 == 7:
                fh.write("not valid json\n")  # 掺入约 10% 非法行
            else:
                record = {
                    "id": str(i),
                    "name": f"  user-{i}  ",
                    "category": "ABC"[i % 3],
                    "score": i / 10,
                    "timestamp": "2026/09/10 08:00:00",
                }
                fh.write(json.dumps(record) + "\n")

    start = time.perf_counter()
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(path), "--dedup-by", "id", "--report-format", "json",
                  "--report-file", str(tmp_path / "report.json")])
    elapsed = time.perf_counter() - start

    assert exc_info.value.code == 0
    assert elapsed < 60, f"处理耗时 {elapsed:.1f}s, 超出 60s 目标"
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["total"] == 100_000
    assert payload["total"] == payload["passed"] + payload["rejected"]
