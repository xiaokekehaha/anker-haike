"""One-variable causal probes. All state and model substitutions are process-local."""
import asyncio
import json
from unittest.mock import patch
from repro import ROOT, intake, build_graph, InMemorySaver, InMemorySessionStore, run_message
from app.sessions.graph import route_after_intake

async def main():
    outcomes=[]
    for clear_reason in (False,True):
        graph=build_graph(InMemorySaver()); store=InMemorySessionStore(); sid=(await store.create_session()).session_id
        async def send(text):
            return [e async for e in run_message(store,graph,sid,text)]
        with patch('app.sessions.graph.extract_intake',intake):
            await send('我机器人，冒烟了')
            if clear_reason: await graph.aupdate_state({'configurable':{'thread_id':sid}},{'escalate_reason':None})
            events=await send('新问题')
        outcomes.append({'cleared_only_escalate_reason':clear_reason,'stages':[e['stage'] for e in events if e['type']=='progress'],'reply':''.join(e['delta'] for e in events if e['type']=='message')})
    # Changing historical text alone cannot change this routing interface.
    cases=[]
    for history in ([],[{'role':'user','text':'我想换个新问题，不再继续前一个问题'}]):
        cases.append(route_after_intake({'escalate_reason':'R4','messages':history,'text':'新问题'}))
    assert cases == ['escalate','escalate']
    assert 'escalate' in outcomes[0]['stages'] and 'disambiguate' in outcomes[1]['stages']
    result={'state_probe':outcomes,'history_only_routes':cases,'conclusion':'Clearing old escalation changes routing, but alone does not implement new-topic semantics. More history alone cannot bypass existing routing.'}
    (ROOT/'probe-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
asyncio.run(main())
