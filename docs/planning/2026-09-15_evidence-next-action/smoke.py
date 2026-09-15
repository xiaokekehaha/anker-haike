"""Live local regression using new smoke sessions; original sessions stay untouched."""
import json
import sys
import uuid
from pathlib import Path

import httpx

results = []
output = Path(__file__).with_name("smoke-result.json")


def send(client, sid, text, image=None):
    snapshot = client.get(f"/sessions/{sid}").json()
    data = {"input_id": uuid.uuid4().hex, "expected_version": snapshot["version"],
            "text": text, "evaluation_source": "smoke", "purpose": "fault"}
    files = {"images": ("device.png", Path(image).read_bytes(), "image/png")} if image else None
    response = client.post(f"/sessions/{sid}/messages", data=data, files=files)
    response.raise_for_status()
    rows = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    result = {"session_id": sid, "input": text, "has_image": bool(image),
              "reply": "".join(e.get("delta", "") for e in rows),
              "types": [e["type"] for e in rows],
              "tools": [{k: e.get(k) for k in ("name", "status", "summary")} for e in rows if e["type"] == "tool_call"],
              "reasons": [e["summary"]["reason"] for e in rows if e["type"] == "escalation_summary"],
              "errors": [e for e in rows if e["type"] == "error"]}
    results.append(result)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    assert not result["errors"], result
    assert "订单号" not in result["reply"], result
    assert rows[-1]["type"] == "done", result
    assert not any(r["rule_id"] == "R7" for r in result["reasons"]), result
    print(json.dumps({"session": sid, "input": text, "reply": result["reply"], "reasons": result["reasons"]}, ensure_ascii=False), flush=True)
    return result


with httpx.Client(base_url="http://localhost:8000", timeout=60) as client:
    symptom_sid = client.post("/sessions").json()["session_id"]
    send(client, symptom_sid, "eufy X10 Pro Omni 不能正常工作")
    send(client, symptom_sid, "可以")
    result = send(client, symptom_sid, "效果不好")
    assert "可多选" in result["reply"], result
    send(client, symptom_sid, "两者都有")

    product_sid = client.post("/sessions").json()["session_id"]
    result = send(client, product_sid, "", sys.argv[1])
    assert "输入为空" not in result["reply"] and "品类" in result["reply"], result
    assert any(t["name"] == "diagnose.vision" for t in result["tools"]), result
    assert "retake_card" not in result["types"], result
    send(client, product_sid, "有点问题", sys.argv[1])
    send(client, product_sid, "运行异响")
    send(client, product_sid, "x00001")
    final = send(client, product_sid, "扫地机器人")
    assert "step_card" in final["types"], final
    print(json.dumps({"passed": True, "sessions": [symptom_sid, product_sid], "turns": len(results)}, ensure_ascii=False))
