"""生成模拟工单 CSV（kb_tickets）。确定性随机，重复执行结果一致。

字段：ticket_id, sku, category, symptom, root_cause, steps, result, doc_version
result ∈ solved / unsolved / escalated；非 solved 工单只作反证（09 §2.4）。
2026-09-17 起覆盖多品类：扫地机 200 条（沿用旧 id T0001–T0200，doc_version 不变），
其余六个深度品类各 30 条（T0201 起）。人工演示样本，待真实脱敏工单替换。
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "kb_tickets" / "tickets.csv"

# category -> (doc_version, skus, cases[(symptom, root_cause, steps)], 必升级的根因)
CATEGORIES: dict[str, tuple[str, list[str], list[tuple[str, str, str]], set[str]]] = {
    "robot_vacuum": (
        "2026-09-12.1",
        [
            "EUFY-X10-PRO-OMNI", "EUFY-X9-PRO", "EUFY-X8-PRO-SES", "EUFY-S1-PRO", "EUFY-L60-HYBRID",
            "EUFY-L50-SES", "EUFY-G50-HYBRID", "EUFY-G40-HYBRID", "EUFY-G30-VERGE", "EUFY-G20-HYBRID",
            "EUFY-30C-MAX", "EUFY-25C", "EUFY-15C-MAX", "EUFY-11S-MAX", "EUFY-E20",
        ],
        [
            ("吸力变小，扫不干净", "滚刷毛发缠绕", "取出滚刷清理缠绕毛发；装回后试运行"),
            ("吸力下降，尘盒很快满", "滤网堵塞", "取出滤网清洗晾干 24 小时后装回"),
            ("提示请检查尘盒", "尘盒未装到位", "重新安装尘盒直到咔哒声"),
            ("边刷不转", "边刷缠绕毛发", "关机拆下边刷清理缠绕物"),
            ("噪音变大吸力弱", "吸口卡异物", "检查吸口取出异物"),
            ("运行中异响并有焦味", "风机电机故障", "告知立即关机停用，升级人工"),
            ("不充电", "基站触点脏污", "擦拭触点后手动放回基站"),
            ("找不到基站", "基站位置遮挡", "调整基站到靠墙开阔位置"),
            ("拖布异味", "拖布未及时清洗", "取下拖布清洗晾干"),
            ("清扫路线混乱", "雷达窗口脏污", "擦拭雷达窗口并重新建图"),
        ],
        {"风机电机故障"},
    ),
    "power_bank": (
        "2026-09-17.1",
        ["ANKER-A1257", "ANKER-A1695", "ANKER-A1289", "ANKER-A1611"],
        [
            ("插上手机没反应", "输出接口绒毛堵塞", "关机后清理接口绒毛，换线后恢复"),
            ("自己充不进电", "使用 5V 1A 老充电器输入过慢", "换 PD 充电器与认证线材，输入灯 10 秒内亮起"),
            ("电量掉得很快", "蓝牙耳机持续小电流取电未识别", "开启小电流模式并做一次完整充放电校准"),
            ("指示灯一直快闪", "高温保护", "静置 30 分钟至室温后恢复充电"),
            ("外壳鼓包发热", "电芯故障", "告知立即停用远离可燃物，升级人工回收"),
        ],
        {"电芯故障"},
    ),
    "charger": (
        "2026-09-17.1",
        ["ANKER-A2337", "ANKER-A2340", "ANKER-A2673", "ANKER-A2148"],
        [
            ("插上设备不充电", "数据线接头处内部断裂", "换认证数据线后恢复"),
            ("充电时断时续", "插线板插孔松动", "直插墙面插座后恢复"),
            ("不进入快充", "数据线不支持 PD 3.0", "更换 100W 认证 USB-C 线后显示快充"),
            ("两个口同时用速度变慢", "多口功率分配", "说明分配规则，单口使用恢复"),
            ("有焦味外壳变形", "内部元件损坏", "告知立即拔下停用，升级人工"),
        ],
        {"内部元件损坏"},
    ),
    "earbuds": (
        "2026-09-17.1",
        ["SOUNDCORE-A3961", "SOUNDCORE-A3953", "SOUNDCORE-A3948", "SOUNDCORE-A3955", "SOUNDCORE-A3947"],
        [
            ("只有左耳有声音", "右耳充电触点氧化未充电", "干棉签清洁触点，放回盒中充电后恢复"),
            ("连不上手机", "配对记录冲突", "删除蓝牙记录，重置耳机后重新配对"),
            ("放回盒子不充电", "充电盒没电", "先给充电盒充电 30 分钟"),
            ("声音变小发闷", "出音孔耳垢堵塞", "取下耳塞套清理网罩"),
            ("降噪没效果", "耳塞套尺寸不合适", "更换耳塞套并重做佩戴检测"),
            ("触控完全失灵", "固件异常", "App 更新固件并恢复默认设置"),
        ],
        set(),
    ),
    "speaker": (
        "2026-09-17.1",
        ["SOUNDCORE-A3130", "SOUNDCORE-A3143", "SOUNDCORE-A3127"],
        [
            ("开不了机", "电池完全耗尽", "原装线充电 30 分钟后开机"),
            ("连上手机没声音", "手机音频输出切到了其他设备", "切回输出设备并调高媒体音量"),
            ("低音破音", "音源音量过载", "手机音量降到 80% 以下并关闭低音增强"),
            ("续航明显变短", "灯效常开", "关闭灯效更新固件"),
            ("掉水里后无法开机", "进水", "晾干 48 小时后仍无法开机，升级人工"),
        ],
        {"进水"},
    ),
    "security_cam": (
        "2026-09-17.1",
        ["EUFY-T8213", "EUFY-T8160", "EUFY-T8210", "EUFY-T8441"],
        [
            ("App 显示离线", "路由器关闭了 2.4GHz", "开启 2.4GHz 后重新配网"),
            ("夜间画面发白", "镜头前保护膜未撕", "撕掉保护膜并擦拭镜头"),
            ("有人经过没录像", "活动区域未覆盖门口", "调整活动区域与灵敏度"),
            ("一天误报几十次", "灵敏度过高且对着马路", "缩小区域降低灵敏度开启人形检测"),
            ("电池一周就没电", "触发次数过多", "降低灵敏度缩短录像时长后续航恢复"),
            ("门铃按了室内机不响", "室内机音量为零", "App 内调高室内机音量"),
        ],
        set(),
    ),
    "breast_pump": (
        "2026-09-17.1",
        ["EUFY-BP-S1-PRO", "EUFY-BP-E10"],
        [
            ("吸力明显变小", "鸭嘴阀开裂", "更换鸭嘴阀后恢复"),
            ("边吸边漏奶", "隔膜未压入卡槽", "重新安装隔膜"),
            ("开不了机", "电池耗尽", "充电 30 分钟后长按开机"),
            ("声音突然变大", "机器未放平", "放平主机并重装隔膜"),
            ("App 连不上", "配对记录失效", "删除设备后重新配对"),
        ],
        set(),
    ),
}


def main() -> None:
    rng = random.Random(20260912)
    rows = []
    counter = 0
    for category, (doc_version, skus, cases, escalate_roots) in CATEGORIES.items():
        total = 200 if category == "robot_vacuum" else 30
        for i in range(total):
            counter += 1
            symptom, root, steps = cases[i % len(cases)]
            r = rng.random()
            result = "solved" if r < 0.7 else ("escalated" if r < 0.85 else "unsolved")
            if root in escalate_roots:
                result = "escalated"
            rows.append(
                {
                    "ticket_id": f"T{counter:04d}",
                    "sku": rng.choice(skus),
                    "category": category,
                    "symptom": symptom,
                    "root_cause": root,
                    "steps": steps,
                    "result": result,
                    "doc_version": doc_version,
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
