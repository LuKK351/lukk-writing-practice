import json,subprocess,tempfile,copy
from pathlib import Path
base=Path(__file__).resolve().parents[1]
fixture=tempfile.TemporaryDirectory(prefix='writing-skill-gate-')
root=Path(fixture.name).resolve()/'练习'
(root.parent/'.obsidian').mkdir() # Synthetic test fixture, never registered or bound.
cmd=['python3',str(base/'scripts/practice.py'),'--root',str(root)]
def run(args,ok=True,has=''):
 r=subprocess.run(cmd+args,text=True,capture_output=True)
 assert (r.returncode==0)==ok,(args,r.stdout,r.stderr)
 assert has in r.stdout+r.stderr,(has,r.stdout,r.stderr)
 return json.loads(r.stdout) if ok else None
def status():return run(['status','W001','--read'])
def review(summary,ok=True,has=''):
 run(['submit','W001'])
 st=status();p=root.parent/'summary.json';p.write_text(json.dumps(summary,ensure_ascii=False));f=root.parent/'feedback.md';f.write_text('审核反馈：依据已记录在内容审核和教学字段中。')
 return run(['review','W001','--read-token',st['read_token'],'--sha256',sha,'--input',str(f),'--summary',str(p)],ok,has)
subprocess.run(['python3',str(base/'scripts/init_workspace.py'),'--root',str(root)],check=True,capture_output=True)
r=run(['new','--title','测试短文','--label','初稿']);draft=Path(r['draft']);draft.write_text('# 测试短文\n\n我先写练习结果，然后回头解释如何开始。\n')
sha=run(['submit','W001'])['sha256'];mp=status()['training_map'];mp['purpose']='解释开始练习的经历'
cr={'status':'checked','dimensions':{'center':'本文讲开始练习，但结果先于起因。','materials':'结果和起因均有，不需要补造材料。','paragraphs':'同段混合结果与回溯，可拆开。','order':'先效果后起因可成立，需决定保留倒叙还是重排。','ending':'尚未交代继续练习的意愿，依本篇目的可保留。'},'priority':'先选择顺序，再修句子。','pending_choices':['P1'],'checked_version':'','checked_sha256':''}
mp['items']=[dict(id='P1',level='optional',kind='content',status='pending',problem='结果后回溯起因，转折未标明。',action='选择保留倒叙或调序。',check='读者能辨认起因与结果。',basis='M04：按理解所需安排信息。',result='')]
s={'stage':'plan','training_map':mp,'outcome':{},'content_review':cr}
review({k:v for k,v in s.items() if k!='content_review'},False,'全文检阅')
review(s)
bad=copy.deepcopy(s);bad['stage']='wrap';review(bad,False,'进入词句')
bad=copy.deepcopy(s);bad['content_review']['status']='ready';review(bad,False,'高影响')
bad=copy.deepcopy(s);bad['content_review']['dimensions'].pop('order');review(bad,False,'顺序')
# Explicit current teaching is required, then accepted with book-based original comparison.
practice=copy.deepcopy(s);practice.update(stage='practice',objective='比较两个顺序',method='M04',steps=['比较并选择'],stop='说明选择的作用')
review(practice,False,'方法与示例')
practice['teaching']={'source':'M04，第19、23—24章方法卡摘要，未重读原书。','mechanism':'先获得的信息改变读者对后句的理解。','example_type':'original_comparison','example':'同样是报名和练习：甲先讲练后感受再回忆报名，乙先报名再写练习感受。','comparison':'甲更早出现体验，乙因果顺序更直接；不一概判乙更好。','application':'比较本稿结果和起因的位置，选一种。','check':'能说明选择且没有改造事实。'}
review(practice)
st=status();rp=root.parent/'changed-action.json';rp.write_text(json.dumps({'objective':'换一个新的动作'}))
run(['record','W001','--read-token',st['read_token'],'--input',str(rp)],False,'方法与示例')
bad=copy.deepcopy(s);bad['content_review'].update(status='ready',pending_choices=[]);bad['training_map']['items'][0]['level']='required'
review(bad,False,'不能标记ready')
# Author keeps sequence: allow wrap, display explicit marker.
ready=copy.deepcopy(s);ready['training_map']['items'][0].update(status='kept',result='作者选择保留先效果后起因，并明确回溯。');ready['content_review'].update(status='ready',pending_choices=[],priority='作者保留倒叙，内容可进入词句。');ready['stage']='wrap';ready['training_map']['proofread']={'status':'checked','note':'全文词句已通读，无必要语言项。'}
review(ready)
assert '内容审核：已完成；可进入词句' in status()['practice_page']
original=draft.read_text();draft.write_text(original+'\n新增段落。')
st=status();assert not st['content_review_current'] and not st['content_ready'] and st['warning']
draft.write_text(original)
st=status();run(['next','W001','--read-token',st['read_token'],'--basis','phase','--cleanup','--label','词句修改','--reason','内容审核后原样复制'])
st=status();assert '待复核' in st['practice_page'];assert '主体' not in Path(st['current_draft']).read_text()
# New version/changed text cannot inherit old ready binding through record.
p=root.parent/'record.json';p.write_text(json.dumps({'stage':'wrap'}));run(['record','W001','--read-token',st['read_token'],'--input',str(p)],False,'当前全文')
p.write_text(json.dumps({'content_review':cr}));run(['record','W001','--read-token',st['read_token'],'--input',str(p)],False,'review')
# Legacy states stay readable; check original workspace read-only separately.
run(['check'])
print('PASS: missing coverage, pending choice, absent teaching, valid teaching, ready marker, cleanup copy, stale binding, record bypass, consistency')
fixture.cleanup()
