import base64, json
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from dotenv import dotenv_values
import pathlib
_ROOT=pathlib.Path(__file__).resolve().parents[4]          # 仓库根
_OUT=pathlib.Path(__file__).parent                          # 合成图输出目录（已 gitignore）
env=dotenv_values(_ROOT/".env")
F="/System/Library/Fonts/STHeiti Light.ttc"
def font(s):
    try: return ImageFont.truetype(F,s)
    except OSError: return ImageFont.load_default()
# 场景：机器底部朝上。滚刷缠满毛发（故障）；滤网洁白干净（无故障）。
W,H=1600,1200
img=Image.new("RGB",(W,H),(200,200,204)); d=ImageDraw.Draw(img)
d.rounded_rectangle([80,80,1520,1120],radius=60,fill=(64,64,68))
d.text((120,110),"机器底部",font=font(40),fill=(200,200,205))
# 滚刷：横向圆柱 + 大量黑色毛发缠绕
d.rounded_rectangle([200,420,1000,600],radius=90,fill=(158,150,120))
d.text((205,340),"滚刷",font=font(44),fill=(235,235,240))
import random; random.seed(7)
for _ in range(260):
    x=random.randint(220,980); y=random.randint(430,590)
    d.arc([x-40,y-26,x+40,y+26],random.randint(0,180),random.randint(180,360),fill=(18,18,20),width=5)
# 滤网：白色网格，干净
d.rectangle([1120,420,1440,740],fill=(245,245,242),outline=(30,30,30),width=4)
for i in range(1,10):
    d.line([1120+i*32,420,1120+i*32,740],fill=(205,205,200),width=2)
    d.line([1120,420+i*32,1440,420+i*32],fill=(205,205,200),width=2)
d.text((1125,340),"滤网",font=font(44),fill=(235,235,240))
img.save(str(_OUT/"fault_scene.jpg"),"JPEG",quality=92)

VOCAB=("part 从 [滚刷 边刷 滤网 尘盒 吸口 轮组 传感器 充电触点 电池仓 基站 其他 不可辨] 中选；"
       "phenomenon 从 [缠绕 堵塞 破损 变形 烧焦 漏液 鼓包 污渍 松脱 缺失 正常 其他 不可辨] 中选。")
TASK=("只描述图片中客观可见的现象与可辨认的部件。"+VOCAB+
      "只输出 JSON：{\"findings\":[{\"part\":\"..\",\"phenomenon\":\"..\"}]}")
MISLEAD="我家扫地机吸力变小了，我拆开看了下，应该是滤网堵住了，你看看是不是。"

CASES=[("deepseek-flash","https://api.deepseek.com/v1","DEEPSEEK_API_KEY",{"thinking":{"type":"disabled"}}),
       ("qwen3-vl-plus","https://dashscope.aliyuncs.com/compatible-mode/v1","DASHSCOPE_API_KEY",{}),
       ("glm-4.6v","https://open.bigmodel.cn/api/paas/v4","ZHIPU_API_KEY",{"thinking":{"type":"disabled"}})]

def ask(model,base,keyenv,extra,with_text):
    b64=base64.b64encode(open(str(_OUT/"fault_scene.jpg"),"rb").read()).decode()
    img_blk={"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}
    if with_text:   # 复现当前 build_messages：文字在前、图片在后、同一次调用
        content=[{"type":"text","text":TASK+f"\n<data kind=\"user_message\">\n{MISLEAD}\n</data>"},img_blk]
    else:           # 建议做法：纯图、图先文后
        content=[img_blk,{"type":"text","text":TASK}]
    c=OpenAI(api_key=env[keyenv],base_url=base,timeout=90)
    try:
        r=c.chat.completions.create(model=model,messages=[{"role":"user","content":content}],
            response_format={"type":"json_object"},max_tokens=300,extra_body=extra)
        return r.choices[0].message.content.strip().replace("\n","").replace(" ","")[:200]
    except Exception as e: return f"ERROR {str(e)[:110]}"

print("金标：滚刷缠绕（有故障）；滤网正常（不应报堵塞）\n")
for m,b,k,x in CASES:
    for rep in range(2):
        a=ask(m,b,k,x,False); bb=ask(m,b,k,x,True)
        bad_a="滤网" in a and "堵塞" in a; bad_b="滤网" in bb and "堵塞" in bb
        print(f"{m:16s} #{rep+1}")
        print(f"   纯图      : {'!! 误报滤网堵塞' if bad_a else 'ok'}  {a[:150]}")
        print(f"   含误导文字: {'!! 误报滤网堵塞' if bad_b else 'ok'}  {bb[:150]}")
