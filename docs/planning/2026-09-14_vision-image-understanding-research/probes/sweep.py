import base64, os, sys, time
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

W,H=3000,2250
GOLD=["Model: X10 Pro","S/N: A2637K8J2","14.4V 5200mAh"]

def make(fs, contrast, path):
    """fs=铭牌字号；contrast=high(黑字白牌) / low(深灰字 灰牌，仿激光蚀刻)"""
    img=Image.new("RGB",(W,H),(205,205,208)); d=ImageDraw.Draw(img)
    d.rounded_rectangle([300,250,2700,1900],radius=120,fill=(70,70,74))
    d.ellipse([1100,700,1900,1500],fill=(45,45,48))
    pw,ph=int(fs*11.5),int(fs*4.6); nx,ny=2650-pw,1850-ph
    plate,ink=((238,238,236),(10,10,10)) if contrast=="high" else ((96,96,100),(52,52,56))
    d.rectangle([nx,ny,nx+pw,ny+ph],fill=plate,outline=(20,20,20),width=2)
    for i,line in enumerate(GOLD):
        d.text((nx+int(fs*0.45),ny+int(fs*0.35)+i*int(fs*1.35)),line,font=font(fs),fill=ink)
    img.save(path,"JPEG",quality=92)
    return (nx,ny,nx+pw,ny+ph)

def crop9(src,box,path):
    img=Image.open(src); cw,ch=W//3,H//3
    b=[2*cw,2*ch,W,H]; ew,eh=int(cw*.25),int(ch*.25)
    b=[max(0,b[0]-ew),max(0,b[1]-eh),min(W,b[2]+ew),min(H,b[3]+eh)]
    c=img.crop(b); c=c.resize((c.width*2,c.height*2),Image.LANCZOS); c.save(path,"JPEG",quality=92)

PROMPT=("逐字符抄录图片中铭牌上可见的字符。看不清的单个字符写 ?。不要补全、不要纠正拼写。"
        "只输出 JSON：{\"nameplate_lines\": [\"...\"]}")
CASES=[("deepseek-flash","https://api.deepseek.com/v1","DEEPSEEK_API_KEY",{"thinking":{"type":"disabled"}}),
       ("qwen3-vl-plus","https://dashscope.aliyuncs.com/compatible-mode/v1","DASHSCOPE_API_KEY",{}),
       ("glm-4.6v","https://open.bigmodel.cn/api/paas/v4","ZHIPU_API_KEY",{"thinking":{"type":"disabled"}})]

def ask(model,base,keyenv,extra,img):
    b64=base64.b64encode(open(img,"rb").read()).decode()
    c=OpenAI(api_key=env[keyenv],base_url=base,timeout=90)
    try:
        r=c.chat.completions.create(model=model,messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
            {"type":"text","text":PROMPT}]}],response_format={"type":"json_object"},
            max_tokens=300,extra_body=extra)
        return r.choices[0].message.content.strip().replace("\n","")[:180]
    except Exception as e: return f"ERROR {str(e)[:120]}"

def score(out):
    hits=sum(1 for g in GOLD if g.replace(" ","") in out.replace(" ",""))
    return f"{hits}/3"

for fs,contrast in [(22,"high"),(14,"high"),(22,"low"),(14,"low")]:
    tag=f"fs{fs}_{contrast}"; p=str(_OUT/f"n_{tag}.jpg"); box=make(fs,contrast,p)
    pc=str(_OUT/f"n_{tag}_crop.jpg"); crop9(p,box,pc)
    print(f"\n===== 字号{fs}px 对比度{contrast}  铭牌占全图 {(box[2]-box[0])*(box[3]-box[1])/(W*H)*100:.2f}% =====")
    for m,b,k,x in CASES:
        of=ask(m,b,k,x,p); oc=ask(m,b,k,x,pc)
        print(f"  {m:16s} 全图 {score(of)}  裁剪放大 {score(oc)}")
        if score(of)!="3/3": print(f"      全图输出: {of[:120]}")
