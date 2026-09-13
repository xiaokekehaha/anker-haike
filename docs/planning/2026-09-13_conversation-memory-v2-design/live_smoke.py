import asyncio,json,time
from pathlib import Path
from uuid import uuid4
import httpx
OUT=Path(__file__).with_name('live-smoke.json')
async def main():
 result={'turns':[]}
 async with httpx.AsyncClient(base_url='http://localhost:8000',timeout=120) as c:
  r=await c.post('/sessions');r.raise_for_status(); sid=r.json()['session_id'];result['session_id']=sid
  for index,text in enumerate(['我的耳机没有声音','我机器人，冒烟了','我之前问了什么问题','有什么故障','新问题','我要人工客服','刚说错了','回到耳机没声音的问题','我最开始说了什么，你当时怎么回答？']):
   s=(await c.get('/sessions/'+sid)).json(); started=time.monotonic()
   r=await c.post('/sessions/'+sid+'/messages',data={'input_id':uuid4().hex,'expected_version':s['version'],'text':text});r.raise_for_status()
   events=[json.loads(l[6:]) for l in r.text.splitlines() if l.startswith('data: ')]
   s=(await c.get('/sessions/'+sid)).json()
   turn={'text':text,'seconds':round(time.monotonic()-started,2),'events':events,'snapshot':s}
   result['turns'].append(turn);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2))
   print(index+1,text,'=>',''.join(e.get('delta','') for e in events),'version',s['version'],flush=True)
   assert not any(e['type']=='error' for e in events), events
   assert s['version']==index+1
   assert events[-1]['type']=='done'
 print('session',sid,flush=True)
asyncio.run(main())
