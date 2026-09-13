"""对真实 HTTP 服务验收；只创建测试会话，不替换模型或知识适配器。"""
import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
import httpx

OUT = Path(__file__).resolve().parent / 'post-sync'
OUT.mkdir(exist_ok=True)
BASE = 'http://127.0.0.1:8000'

class Session:
    def __init__(self, client, label):
        self.c, self.label = client, label
        self.sid = None
        self.events = []
        self.runs = []
    async def create(self):
        r = await self.c.post('/sessions'); r.raise_for_status()
        self.sid = r.json()['session_id']
        return self
    async def snapshot(self):
        r = await self.c.get(f'/sessions/{self.sid}'); r.raise_for_status()
        return r.json()
    async def stream(self, method, url, **kwargs):
        t0=time.perf_counter(); ev=[]; visible=card=None
        async with self.c.stream(method,url,**kwargs) as r:
            if r.status_code != 200:
                body=(await r.aread()).decode()
                raise AssertionError(f'HTTP {r.status_code}: {body[:300]}')
            async for line in r.aiter_lines():
                if line.startswith('data:'):
                    e=json.loads(line[5:]); ev.append(e)
                    dt=round((time.perf_counter()-t0)*1000)
                    if e['type']=='message' and visible is None: visible=dt
                    if e['type'].endswith('_card') and card is None: card=dt
            headers={k:v for k,v in r.headers.items() if k in ['x-action-replayed','x-run-id']}
        self.events.extend(ev)
        self.runs.append({'types':list(dict.fromkeys(e['type'] for e in ev)), 'first_visible_ms':visible, 'card_ready_ms':card, 'elapsed_ms':round((time.perf_counter()-t0)*1000),'headers':headers})
        errors=[e for e in ev if e['type']=='error']
        assert not errors, f'run errors: {errors}'
        return ev,headers
    async def send(self,text,**kwargs):
        return (await self.stream('POST',f'/sessions/{self.sid}/messages',data={'text':text,**kwargs}))[0]
    async def body(self,kind,payload):
        sn=await self.snapshot(); p=sn.get('pending_input') or {}
        b={'action_id':uuid.uuid4().hex,'kind':kind,'expected_version':sn['version'],'payload':payload}
        if kind not in ['request_human','rediagnose']:
            b.update({k:p[k] for k in ['interrupt_id','card_id']})
        return b
    async def action(self,kind,payload):
        b=await self.body(kind,payload)
        ev,headers=await self.stream('POST',f'/sessions/{self.sid}/actions',json=b)
        return ev,b,headers
    def save(self,extra=None):
        (OUT/f'{self.label}.json').write_text(json.dumps({'session_id':self.sid,'runs':self.runs,'events':self.events,**(extra or {})},ensure_ascii=False,indent=2))


def oftype(ev,typ):
    return [e for e in ev if e['type']==typ]

def require_card(ev):
    cards=oftype(ev,'step_card'); assert cards, f'no step card: {[e["type"] for e in ev]}'
    return cards[-1]

def require_done(ev):
    assert any(e['type']=='progress' and e.get('stage')=='done' for e in ev), 'missing done stage'
    assert ev[-1]['type']=='done' and ev[-1]['reason']=='completed', 'not completed'

async def a1(s):
    ev=await s.send('eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发')
    card=require_card(ev)
    assert card['step']['plan_id']=='rv_suction_hair_wrap', card['step']
    evidence=[i for e in oftype(ev,'evidence') for i in e['items']]
    assert evidence and any(i.get('status') not in ['replay','unavailable'] for i in evidence), 'no live evidence'
    sn=await s.snapshot(); assert sn['pending_input']['card_id']==card['card_id']
    b=await s.body('step_feedback',{'feedback':'solved'})
    ev,h=await s.stream('POST',f'/sessions/{s.sid}/actions',json=b); require_done(ev)
    replay,hr=await s.stream('POST',f'/sessions/{s.sid}/actions',json=b)
    assert hr.get('x-action-replayed')=='true',hr
    assert replay==ev, 'idempotency events changed'
    final=await s.snapshot(); assert final['stage']=='done' and final['pending_input'] is None
    return {'final_stage':final['stage'],'evidence_status':sorted(set(i.get('status','ok') for i in evidence)),'idempotent_replay':True}

async def a2(s):
    ev=await s.send('我的 S1 Pro 不吸了'); assert oftype(ev,'product_card'),'missing product card'
    ev,b,h=await s.action('select_product',{'sku':'EUFY-S1-PRO'}); require_card(ev)
    ev,b,h=await s.action('step_feedback',{'feedback':'solved'}); require_done(ev)
    return {'final_stage':(await s.snapshot())['stage']}

async def a3(s):
    require_card(await s.send('eufy X10 Pro 扫地机不吸了，滚刷缠了很多头发'))
    for _ in range(8):
        sn=await s.snapshot(); p=sn.get('pending_input')
        if p and p['kind']=='upload_receipt': break
        assert p and p['kind']=='step_feedback',f'unexpected pending {p}'
        await s.action('step_feedback',{'feedback':'not_solved'})
    else: raise AssertionError('receipt not requested')
    # 使用既有录制包同款白图，明确只验收低置信/手工确认通路。
    from app.replay.scenarios import demo_receipt_png
    ev,_=await s.stream('POST',f'/sessions/{s.sid}/messages',data={'text':'验收用不可读凭证图','purpose':'receipt'},files=[('images',('blank.png',demo_receipt_png(),'image/png'))])
    cards=oftype(ev,'receipt_card'); assert cards,'missing receipt card'
    fields={'order_no':'20260315-DEMO-9999','channel':'海科演示授权经销商','purchase_date':'2026-03-15','amount':None}
    ev,b,h=await s.action('confirm_receipt',{'fields':fields,'edited':['order_no','channel','purchase_date']})
    summaries=oftype(ev,'escalation_summary'); assert summaries,'missing summary'
    return {'receipt_card':cards[-1], 'summary':summaries[-1]['summary'],'scope':'blank image + manual confirmation, not real screenshot OCR accuracy'}

async def rediagnose(s):
    require_card(await s.send('eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发'))
    await s.action('step_feedback',{'feedback':'not_solved'})
    old=await s.body('step_feedback',{'feedback':'solved'})
    require_card(await s.send('其实还有异响'))
    r=await s.c.post(f'/sessions/{s.sid}/actions',json=old)
    assert r.status_code==409 and r.json()['code']=='stale_version',r.text
    require_card(await s.send('不是吸力小，是有异响'))
    ev=await s.send('说错了，我的是 X10')
    sn=await s.snapshot()
    if sn.get('pending_input') and sn['pending_input']['kind']=='select_product':
        await s.action('select_product',{'sku':'EUFY-X10-PRO-OMNI'})
    ev=await s.send('闻到烧焦味了')
    sums=oftype(ev,'escalation_summary'); assert sums,'no safety summary'
    assert not any(e['type']=='tool_call' and ('search' in e.get('name','') or 'intake'==e.get('name')) for e in ev), 'safety routed through model/retrieval'
    return {'stale_code':r.json()['code'],'safety_summary':sums[-1]['summary']}

async def cancel(s):
    # 获取 run_started 后立即取消，允许服务端在真实模型调用前即中断。
    async with s.c.stream('POST',f'/sessions/{s.sid}/messages',data={'text':'eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发'}) as r:
        assert r.status_code==200
        ev=[]; result=None
        async for line in r.aiter_lines():
            if not line.startswith('data:'):continue
            e=json.loads(line[5:]);ev.append(e)
            if e['type']=='run_started':
                result=await s.c.post(f'/sessions/{s.sid}/cancel',json={'run_id':e['run_id']})
                assert result.status_code==200,result.text
        s.events.extend(ev)
    assert any(e['type']=='done' and e['reason']=='cancelled' for e in ev),'missing cancelled done'
    sn=await s.snapshot(); assert sn['active_run'] is None
    ev,b,h=await s.action('request_human',{}); assert oftype(ev,'escalation_summary')
    return {'cancel':result.json(),'continued_with_human':True}

async def resume(s):
    run_id=None;seq=0
    async with s.c.stream('POST',f'/sessions/{s.sid}/messages',data={'text':'eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发'}) as r:
        assert r.status_code==200
        async for line in r.aiter_lines():
            if line.startswith('data:'):
                e=json.loads(line[5:]);s.events.append(e);seq=e['seq'];run_id=e['run_id'];break
    ev,_=await s.stream('GET',f'/sessions/{s.sid}/runs/{run_id}/events?after_seq={seq}')
    assert all(e['seq']>seq for e in ev) and len({e['seq'] for e in ev})==len(ev)
    require_card(ev)
    sn=await s.snapshot();assert sn['active_run'] is None and sn['pending_input']['kind']=='step_feedback'
    await s.action('step_feedback',{'feedback':'solved'})
    return {'resume_after_seq':seq,'received':len(ev),'final_stage':(await s.snapshot())['stage']}

CASES={'a1':a1,'a2':a2,'a3':a3,'rediagnose':rediagnose,'cancel':cancel,'resume':resume}
async def main(names):
    results=[]
    async with httpx.AsyncClient(base_url=BASE,timeout=90) as c:
        for name in names:
            s=Session(c,name); t0=time.perf_counter()
            try:
                await s.create();detail=await CASES[name](s)
                row={'case':name,'passed':True,'detail':detail}
            except Exception as e:
                row={'case':name,'passed':False,'error':f'{type(e).__name__}: {e}'}
            row.update({'session_id':s.sid,'elapsed_ms':round((time.perf_counter()-t0)*1000)})
            s.save({'result':row});results.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    (OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return 0 if all(r['passed'] for r in results) else 1
if __name__=='__main__':
    import sys
    names=sys.argv[1:] or list(CASES)
    raise SystemExit(asyncio.run(main(names)))
