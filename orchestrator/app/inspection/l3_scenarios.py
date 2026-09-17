"""L3 offline inspection; exercises the production gate/backend/case modules."""
import asyncio
import uuid

from haike_contracts.common import GateResult

from app.actions.executor import ActionExecutor, AuthorizationDenied
from app.evaluation.cli import run
from app.inspection.scenarios import scenario


def valid_gate():
    from app.actions.gate import AuthorizationGate
    from app.policy import PolicyEngine, PolicyInput
    # US：保修期表只对美国有公开来源，非 US 购买地一律 no_policy_matched 转人工，授权门必然不通过。
    policy = PolicyEngine().decide(PolicyInput(sku='EUFY-X10-PRO-OMNI', category='robot_vacuum', region_purchase='US', region_use='US', channel='official_store', purchase_date='2026-02-26', today='2026-09-14', fault_class='quality'))
    return AuthorizationGate().check(decision=policy, option={'remedy':'replace'},receipt={'status':'order_verified'},product_state='confirmed_sku',risk_cases=[],allowed_operations=True,user_confirmed=True,case_status='awaiting_confirmation')


def args():
    return {'idempotency_key': 'inspection:replace','session_id': 'inspection','run_id': 'r','case_id': 'c','gate_result': valid_gate()}


def params(order='DEMO-X10-001'):
    return {'order_no': order,'sku': 'EUFY-X10-PRO-OMNI','reason_code': 'quality','evidence_ids': []}


@scenario('l3_forged_authorization','l3','伪造通过标记不能绕过四项授权检查','L3 03 §3')
async def forged(ctx):
    from app.backends.mock import MemoryBackend
    backend=MemoryBackend()
    try:
        await ActionExecutor(backend).run('replacement.create',params(),**(args()|{'gate_result':GateResult(passed=True,checks=[])}))
    except AuthorizationDenied:
        assert backend.create_calls==0
        return {'unauthorized_writes':0}
    raise AssertionError('forged authorization accepted')


@scenario('l3_idempotent_execution','l3','重复申请只创建一张服务单','L3 03 §4')
async def idempotent(ctx):
    from app.backends.mock import MemoryBackend
    backend=MemoryBackend(); executor=ActionExecutor(backend)
    first=await executor.run('replacement.create',params(),**args())
    repeats=await asyncio.gather(*[executor.run('replacement.create',params(),**args()) for _ in range(5)])
    assert backend.create_calls==1 and all(r.replayed and r.receipt==first.receipt for r in repeats)
    return {'created':backend.create_calls,'replayed':len(repeats)}


@scenario('l3_hitl_reject','l3','拒绝决定持久化且不执行','L3 05 §4')
async def reject(ctx):
    from app.cases.service import CaseService
    service=CaseService(); row=await service.open('s','i',{})
    row=await service.transition(row['case_id'],'awaiting_approval','审核')
    row=await service.decide(row['case_id'],decision_id=str(uuid.uuid4()),decision='reject',actor='agent:inspection',expected_revision=row['revision'],note='不符合政策')
    assert row['status']=='rejected' and len(row['decisions'])==1
    return {'status':row['status']}


@scenario('l3_backend_faults','l3','超时与不可用返回可解释失败回执','L3 03 §5')
async def backend_faults(ctx):
    from app.backends.mock import MemoryBackend
    results=[]
    for i in (1,2):
        executor=ActionExecutor(MemoryBackend())
        result=await executor.run('replacement.create',params(f'DEMO-FAIL-{i:03}'),**args())
        assert result.status=='failed' and result.receipt.next_step
        results.append(result.status)
    return {'statuses':results}


@scenario('l3_complaint_escalation','l3','三轮情绪升高采用对应策略','L3 06 §4')
async def emotion(ctx):
    from app.emotion.policy import evaluate_emotion
    track=[]; results=[]
    for i,text in enumerate(['不满意','生气','我要投诉']):
        value=evaluate_emotion('calm',text,track,str(i))
        track=value['emotion_track']; results.append(value['emotion']['level'])
    assert results==['dissatisfied','angry','complaint_risk']
    assert 'offer_human' in value['emotion_actions']
    return {'levels':results}


@scenario('l3_blurry_image','l3','不可用图片不会提高排障计划先验','L3 06 §1')
async def blurry(ctx):
    from haike_contracts.common import FaultLocalization

    from app.diagnose.localization import normalize, signature_plans
    value=normalize(FaultLocalization(image_quality={'usable':False,'reasons':['blurry']}))
    assert value['image_quality']['guidance'] and signature_plans(value)==[]
    return {'usable':False,'model_accuracy':'not_evaluated'}


@scenario('l3_task_continuation','l3','排障完成后接续物流查询','L3 06 §3')
async def tasks(ctx):
    from app.conversation.tasks import enqueue, next_task
    queue,_=enqueue([],'report_problem',['logistics_query'],'不吸，查物流','i')
    queue,task=next_task(queue,'report_problem')
    assert task['intent']=='logistics_query' and queue[0]['status']=='done'
    assert run('routing')['status']=='passed'
    return {'next':task['intent']}
