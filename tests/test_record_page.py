"""Reading order and information preservation for the learner-facing record."""
import copy
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('practice',Path(__file__).resolve().parents[1]/'scripts/practice.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def issue(id,kind):
 return dict(id=id,kind=kind,level='optional',status='pending',problem=id+'问题原文',action=id+'处理方向',check=id+'检验标准',basis=id+'方法依据',result='')
sha='a'*64
m=dict(id='W001',title='测试短文',stage='plan',current_version='V01',version_labels={'V01':'初稿'},submissions={'V01':{'sha256':sha}},objective='比较两个叙述顺序',next_action='先找出写结果的两段。',why='结果重复交代，读者需要重新连接起因。',steps=['这是不应重复显示的后台步骤'],stop='这是不应重复显示的后台停止条件',process_note='这是保留的历史说明',decisions=['作者希望保留口语'],assistance='AI指出结构问题',evidence_limit='未核对外部材料',training_map={'purpose':'说明一次尝试','strengths':['动作细节有效'],'items':[issue('L1','language'),issue('P1','content'),issue('L2','language'),issue('P2','content')],'proofread':{'status':'pending','note':'内容确定后再检查'},'checked_version':'V01','checked_sha256':sha},content_review={'status':'checked','dimensions':{k:k+'具体审核结论' for k in p.CONTENT_DIMENSIONS},'priority':'先考虑顺序','pending_choices':['P1'],'checked_version':'V01','checked_sha256':sha},teaching={'source':'方法卡所引第19章','mechanism':'先获得的信息影响后句理解。','example_type':'original_comparison','example':'相同材料的两种次序。','comparison':'一种先给意外，一种先给背景。','application':'比较后选择符合原意的安排。','check':'能说明选择的作用。'})
reflection='\n这段心得由我自己写。\n'
page=p.page_text(m,reflection)
visible='\n'.join(x for x in page.splitlines() if not x.startswith('>'))
assert page.index(m['next_action']) < page.index(m['teaching']['example']) < page.index('## 全篇检查')
assert page.index('P1问题原文')<page.index('P2问题原文')<page.index('L1问题原文')<page.index('L2问题原文')
for item in m['training_map']['items']:
 for field in ['problem','action','check','basis']:assert item[field] in page
for key in ['example','comparison','application','check']:assert page.count(m['teaching'][key])==1
assert 'original_comparison' not in page and sha[:12] not in visible
assert '后台步骤' not in page and '后台停止条件' not in page
assert m['process_note'] in page and m['process_note'] not in visible
assert page.endswith(reflection)
# Initial drafting must not fabricate a lesson or a completed review.
blank=copy.deepcopy(m);blank.pop('teaching');blank.pop('content_review');blank['training_map']=p.empty_map()
text=p.page_text(blank,reflection)
assert '## 方法和例子' not in text and '待复核' in text and '后台步骤' in text
# Proofreading changes the checklist label, not the underlying issue records.
wrap=copy.deepcopy(m);wrap['stage']='wrap';wrap['content_review']['status']='ready';wrap['content_review']['pending_choices']=[]
text=p.page_text(wrap,reflection);assert '词句修改清单' in text and '可进入词句' in text
assert '## 方法和例子' not in text # Prior content lesson must not reappear as proofreading guidance.
wrap['teaching_stage']='wrap';assert '## 方法和例子' in p.page_text(wrap,reflection)
# Closed exercises lead with actual outcomes; no stale current lesson.
closed=copy.deepcopy(m);closed.update(stage='closed',completion_summary='本次学会解释一次调序的理由。',close_with_unfinished=True,close_reason='作者选择结束')
text=p.page_text(closed,reflection)
assert '带遗留事项结束' in text and text.index(closed['completion_summary'])<text.index('全篇检查')
assert '## 这轮先做什么' not in text and '## 方法和例子' not in text and text.endswith(reflection)
closed.update(base_version='V00',outcome={'benefit':'同一收益'},version_notes=[{'from_version':'V00','to_version':'V01','content':'同一收益'}])
assert p.page_text(closed,reflection).count('同一收益')==1
print('PASS: actionable reading order, grouped complete findings, visible lesson, no duplicate task, hidden metadata, reflection preservation, blank/wrap/closed states')
