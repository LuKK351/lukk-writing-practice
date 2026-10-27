#!/usr/bin/env python3
"""短文练习的机械记录与版本保护。所有操作显式指定 --root；不生成教学判断。"""
import argparse, contextlib, datetime, hashlib, io, json, os, re, sys, zipfile
from pathlib import Path
from urllib.parse import quote

PID=re.compile(r'W\d{3,6}\Z'); VER=re.compile(r'V\d{2,6}\Z')
STAGES={'plan':'约定本次练习','practice':'本人尝试中','compare':'对照检验中','wrap':'整篇待收尾','closed':'本次已结束'}
ALLOWED={'objective','why','method','steps','output','stop','stage','training_complete','selected_version','outcome','remaining','next_action','overview','decisions','assistance','evidence_limit','learner_reflection','base_version','version_notes','process_note','completion_summary','training_map','content_review','teaching'}
OBS={}
SKILL=Path(__file__).resolve().parents[1]
def menu_text(raw):
 # Obsidian may realign table padding; keep words, links, cell order and alignment meaningful.
 lines=[]
 for line in raw.decode('utf-8').replace('\r\n','\n').split('\n'):
  if line.lstrip().startswith('|') and line.rstrip().endswith('|'):
   cells=[c.strip() for c in re.split(r'(?<!\\)\|',line.strip())[1:-1]]
   cells=[re.sub(r'^(:?)-+(:?)$',r'\1---\2',c) for c in cells]
   line='|'+'|'.join(cells)+'|'
  lines.append(line)
 return '\n'.join(lines)

def configure_runtime():
 # Redirected Windows output may otherwise use the system code page.
 for stream in (sys.stdout,sys.stderr):
  if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
 if sys.version_info[:2]<(3,10):fail('需要 Python 3.10 或更高版本；请使用可用的较新解释器')

def digest(b):return hashlib.sha256(b).hexdigest()
def now():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
def fail(s):raise ValueError(s)
def inside(root,p):
 p=Path(p); p=p if p.is_absolute() else root/p
 try:p.resolve().relative_to(root.resolve())
 except ValueError:fail('路径越界：'+str(p))
 cur=p
 while cur!=root and cur!=cur.parent:
  if cur.is_symlink():fail('路径不允许符号链接：'+str(cur))
  cur=cur.parent
 return p

def read(p):
 b=p.read_bytes();OBS[p.resolve()]=digest(b);return b

def text(p):return read(p).decode('utf-8')
def json_read(p):return json.loads(text(p))
def jbytes(d):return (json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
def transaction(root,writes):
 writes={inside(root,p):b for p,b in writes.items()}
 journal=root/'.writing-practice/transaction.json'
 if journal.exists():fail('存在未完成事务，先核对：'+str(journal))
 def validate():
  for p in writes:
   actual=digest(p.read_bytes()) if p.exists() else None
   if p.resolve() not in OBS:
    if p.exists():fail('写前未读取：'+str(p))
    OBS[p.resolve()]=None
   if actual!=OBS[p.resolve()]:fail('文件读取后发生变更，已保留用户内容：'+str(p))
 validate()
 for p in writes:
  p.parent.mkdir(parents=True,exist_ok=True)
  if p.with_name(p.name+'.pending').exists():fail('存在待核文件：'+str(p))
 with journal.open('x',encoding='utf-8') as f:json.dump({str(p.relative_to(root)):digest(b) for p,b in writes.items()},f,ensure_ascii=False)
 for p,b in writes.items():
  with p.with_name(p.name+'.pending').open('xb') as f:f.write(b)
 validate()
 for p,b in writes.items():
  os.replace(p.with_name(p.name+'.pending'),p);OBS[p.resolve()]=digest(b)
 journal.unlink()

@contextlib.contextmanager
def lock(root):
 path=root/'.writing-practice/lock'
 try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 except FileExistsError:fail('已有写入锁，先核对是否仍在使用，不要并发修改')
 try:
  os.write(fd,str(os.getpid()).encode());os.close(fd);yield
 finally:path.unlink(missing_ok=True)

def ident(s):
 if not PID.fullmatch(s):fail('练习ID格式错误')
 return s

def version(s):
 if not VER.fullmatch(s):fail('版本格式错误')
 return s

def version_label(s):
 if not isinstance(s,str):fail('版本说明须为文字')
 s=s.strip()
 if not s or len(s)>48 or any(ord(c)<32 or c in '/\\<>:"|?*' for c in s):fail('版本说明为空、过长或含文件名特殊字符')
 return s

def title_filename(title):
 # Only the folder spelling changes; the article heading and state keep the title.
 name=title.translate(str.maketrans('<>:"|?*','＜＞：＂｜？＊'))
 return name.rstrip('.')+'．'*(len(name)-len(name.rstrip('.')))

def version_name(m,v):
 version(v);label=m.get('version_labels',{}).get(v)
 return v+' '+version_label(label) if label else v

def version_file(m,v):return version_name(m,v)+'.md'

def draft_path(root,folder,m,v):return inside(root,folder/version_file(m,v))

def locate(root,id):
 ident(id);matches=list((root/'00 我的练习').glob(id+' *'))
 if len(matches)!=1:fail('练习目录不唯一或不存在：'+id)
 return inside(root,matches[0])

def state_path(root,id):return inside(root,'.writing-practice/状态/'+ident(id)+'.json')
REFLECTION='## 我的体会\n'
def generated_part(s):return s.split(REFLECTION,1)[0]
def load(root,id,accept_page_change=False):
 folder=locate(root,id);m=json_read(state_path(root,id));page=text(inside(root,folder/'R01 练习记录.md'))
 if m.get('schema')!=2 or m.get('id')!=id:fail('状态格式或身份错误')
 if m.get('page_generated_sha256')!=digest(generated_part(page).encode()) and not accept_page_change:fail('练习页摘要被人工修改，请先理解并合并修改，不覆盖')
 if REFLECTION not in page:fail('练习页缺少体会区，先核对页面')
 return folder,m,page.split(REFLECTION,1)[1]

def method(root,id):
 if not re.fullmatch(r'M0[1-8]',id):fail('方法ID须为M01—M08')
 paths=list((SKILL/'references/方法').glob(id+' *.md'))
 if len(paths)!=1:fail('方法不存在或不唯一：'+id)
 p=inside(SKILL,paths[0]);s=text(p)
 rev=re.search(r'^revision:\s*"?([\d.]+)"?\s*$',s,re.M)
 if not rev:fail('方法缺少版本')
 return {'id':id,'revision':rev[1],'file':str(p.relative_to(SKILL)),'sha256':digest(s.encode()),'source':'skill:lukk-writing-practice'}

def link(label,path):return '['+label+']('+quote(str(path).replace('\\','/'),safe='/')+')'
def retain_outcome(m):
 base=m.get('base_version');target=m['current_version']
 if not base or base==target or not m.get('training_complete') or not any(m.get('outcome',{}).values()):return
 notes=m.setdefault('version_notes',[])
 if any(x['from_version']==base and x['to_version']==target for x in notes):return
 content=['**本轮目标：** '+m.get('objective','')]
 for key,label in [('before','改前'),('after','改后'),('benefit','收益'),('tradeoff','取舍'),('takeaway','可复用的方法')]:
  if m['outcome'].get(key):content.append('**'+label+'：** '+m['outcome'][key])
 for key,label in [('assistance','帮助程度'),('evidence_limit','检验边界')]:
  if m.get(key):content.append('**'+label+'：** '+m[key])
 notes.append({'from_version':base,'to_version':target,'content':'\n\n'.join(content)})

def folded(title,body):
 if not body.strip():return []
 return ['', '> [!note]- '+title]+['> '+line if line else '>' for line in body.strip().splitlines()]

MAP_STATUS={'pending':'待处理','selected':'已选待练','active':'进行中','clarify':'待确认','resolved':'已解决','kept':'保留不改','withdrawn':'已撤回'}
def empty_map():
 return {'purpose':'','strengths':[],'items':[],'proofread':{'status':'pending','note':''},'checked_version':'','checked_sha256':''}

def map_current(m,sha=None):
 mp=m.get('training_map',{});v=m['current_version']
 expected=sha if sha is not None else m.get('submissions',{}).get(v,{}).get('sha256')
 return bool(expected and mp.get('checked_version')==v and mp.get('checked_sha256')==expected)

def read_token(root,folder,m):
 # Reading a token supplies context; it cannot prove that a model understood it.
 return digest(read(state_path(root,m['id']))+b'\0'+read(folder/'R01 练习记录.md')+b'\0'+read(draft_path(root,folder,m,m['current_version'])))

def require_read(root,folder,m,a):
 if ('training_map' in m or a.command=='refresh') and getattr(a,'read_token',None)!=read_token(root,folder,m):
  fail('请先status --read回读最新练习页与全文，再传本轮read-token；内容变化后旧凭据失效')

def validate_map(mp,old=None):
 keys={'purpose','strengths','items','proofread','checked_version','checked_sha256'}
 if not isinstance(mp,dict) or set(mp)!=keys:fail('training_map字段不完整')
 if not all(isinstance(mp[k],str) for k in ['purpose','checked_version','checked_sha256']):fail('地图目的与绑定格式错误')
 if not isinstance(mp['strengths'],list) or any(not isinstance(x,str) for x in mp['strengths']):fail('strengths须为文字数组')
 if not isinstance(mp['items'],list):fail('items须为事项数组')
 ids=set();active=0
 for x in mp['items']:
  if not isinstance(x,dict) or set(x)!={'id','level','kind','status','problem','action','check','basis','result'} or any(not isinstance(v,str) for v in x.values()):fail('地图事项字段不完整')
  if not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,20}',x['id']) or x['id'] in ids:fail('地图事项ID重复或无效')
  ids.add(x['id'])
  if x['level'] not in {'required','optional'} or x['kind'] not in {'content','language'} or x['status'] not in MAP_STATUS:fail('地图等级、类型或状态错误')
  if any(not x[k].strip() for k in ['problem','action','check','basis']):fail('每项须有文字问题、动作、检验标准与依据')
  if x['status'] in {'resolved','kept','withdrawn'} and not x['result'].strip():fail('事项处理后须留下具体原因或证据')
  active+=x['kind']=='content' and x['status']=='active'
 if active>1:fail('同时只推进一个主要内容动作')
 if old and not {x['id'] for x in old['items']}<=ids:fail('不能静默删除地图事项；请说明解决、保留或撤回')
 pr=mp['proofread']
 if not isinstance(pr,dict) or set(pr)!={'status','note'} or pr['status'] not in {'pending','checked'} or not isinstance(pr['note'],str):fail('全文校对状态错误')
 if pr['status']=='checked' and not pr['note'].strip():fail('完成全文校对须说明检查范围和结果')
 return mp

def map_blockers(mp,content_only=False):
 return [x['id'] for x in mp['items'] if (not content_only or x['kind']=='content') and (x['level']=='required' and x['status'] not in {'resolved','withdrawn'} or x['status'] in {'active','selected'})]

CONTENT_DIMENSIONS={'center','materials','paragraphs','order','ending'}
def validate_content_review(r):
 keys={'status','dimensions','priority','pending_choices','checked_version','checked_sha256'}
 if not isinstance(r,dict) or set(r)!=keys:fail('内容审核字段不完整')
 if r['status'] not in {'checked','ready'}:fail('内容审核状态须为checked或ready')
 d=r['dimensions']
 if not isinstance(d,dict) or set(d)!=CONTENT_DIMENSIONS or any(not isinstance(v,str) or not v.strip() for v in d.values()):fail('须逐项说明中心、材料、段落、顺序和结尾的具体审核依据')
 if any(not isinstance(r[k],str) for k in ['priority','checked_version','checked_sha256']) or not r['priority'].strip():fail('须说明内容处理优先级及取舍')
 if not isinstance(r['pending_choices'],list) or any(not isinstance(x,str) or not x.strip() for x in r['pending_choices']):fail('待选择内容事项须为ID数组')
 if r['status']=='ready' and r['pending_choices']:fail('高影响内容建议尚待选择，不能标记可进入词句')
 return r

def content_ready(m,sha):
 r=m.get('content_review',{})
 return bool(sha and r.get('status')=='ready' and not r.get('pending_choices') and r.get('checked_version')==m['current_version'] and r.get('checked_sha256')==sha)

def validate_teaching(t):
 keys={'source','mechanism','example_type','example','comparison','application','check'}
 if not isinstance(t,dict) or set(t)!=keys or any(not isinstance(v,str) or not v.strip() for v in t.values()):fail('带练须有书中方法来源、机制、相关示例、差别与取舍、本文尝试和检验标准')
 if t['example_type'] not in {'book_summary','book_quote','original_comparison'}:fail('示例须区分书例摘要、书中短引或原创对照')
 return t

def sentence(s):
 s=s.strip().rstrip('；;')
 return s if not s or s.endswith(('。','！','？','.','!','?','…','：',':')) else s+'。'

def map_criteria(items):
 # Group only identical bases (apart from trailing separators), never infer equivalence.
 groups={}
 for x in items:groups.setdefault((x['kind'],x['basis'].strip().rstrip('。；;')),[]).append(x)
 lines=[]
 for (_,basis),group in groups.items():
  if len(group)==1:
   x=group[0];lines.append('**'+x['id']+'** '+sentence(basis)+' 检验：'+x['check'])
  else:
   lines.append('**共同依据（'+'、'.join(x['id'] for x in group)+'）** '+sentence(basis))
   lines.extend('**'+x['id']+'** 检验：'+x['check'] for x in group)
 return lines

def map_lines(m):
 mp=m['training_map'];fresh=map_current(m);lines=['## 全文训练地图','', '**本篇目的：** '+(mp['purpose'] or '先完成初稿，再确定全文地图。')]
 if mp['strengths']:lines+=['','**已经成立、应当保留：**','']+['- '+x for x in mp['strengths']]
 if not fresh:lines+=['','**地图待复核：** 以下状态尚未核验为当前稿结果；不能据此宣布完成。']
 lines+=['','| 事项与影响 | 等级 | 处理方向 | 状态／结果 |','|---|---|---|---|']
 for x in mp['items']:
  label=MAP_STATUS[x['status']]
  if x['level']=='optional' and x['status']=='pending':label='未选练' if m['stage']=='closed' else '待选择'
  if not fresh:label+='（待复核）'
  lines+=['| '+cell(x['id']+' '+x['problem'])+' | '+('必须处理' if x['level']=='required' else '可选优化')+' | '+cell(x['action'])+' | '+cell(label+('：'+x['result'] if x['result'] else ''))+' |']
 done=fresh and mp['proofread']['status']=='checked'
 lines+=['| **最后：全文字词句检查** | 固定收尾步骤 | 内容确定后通读全文，一次列齐必改与可选项 | '+('已完整检查；各项处理见上表' if done else '未完成／待最后检查')+' |']
 criteria=map_criteria(mp['items'])
 if mp['proofread']['note']:criteria+=['全文校对说明：'+mp['proofread']['note']]
 lines+=folded('地图的检验依据','\n\n'.join(criteria))
 return lines

def page_text(m,reflection):
 closed=m['stage']=='closed'
 label=('采用稿 ' if closed else '当前工作稿 ')+version_name(m,m['current_version'])
 lines=['# '+m['title'],'','**'+STAGES[m['stage']]+'**','',link(label,version_file(m,m['current_version']))]
 pair=(m['base_version']+' → '+m['current_version']+'｜') if m.get('base_version') else ''
 if closed:
  if m.get('close_with_unfinished'):lines+=['','**带遗留事项结束：** '+m.get('close_reason','')+'；不代表全部问题已解决。']
  lines+=['','## 本篇小结','',m.get('completion_summary') or m.get('next_action') or '本次已结束。']
 else:
  cr=m.get('content_review')
  fresh=map_current(m) and cr and cr.get('checked_version')==m['current_version'] and cr.get('checked_sha256')==m.get('training_map',{}).get('checked_sha256')
  marker=('已完成；可进入词句' if cr['status']=='ready' else '已完成检查；内容仍待处理或选择') if fresh else '未完成或稿件已变化，待复核'
  lines+=['','**内容审核：'+marker+'。**']
  if cr:lines+=['','审核对象：'+cr.get('checked_version','')+'／'+cr.get('checked_sha256','')[:12]+'；正文改变后须重新核验。']
  if cr:
   labels={'center':'中心','materials':'材料','paragraphs':'段落作用','order':'顺序与结构','ending':'结尾'}
   body=[labels[k]+'：'+cr['dimensions'][k] for k in labels]+['优先级与取舍：'+cr['priority']]
   lines+=folded('内容审核依据', '\n\n'.join(body))
  if 'training_map' in m:lines+=['']+map_lines(m)
  lines+=['','## 现在做什么','',m.get('next_action') or '先确定这次想练的一个动作。']
  lines+=['','**'+pair+'本轮目的：** '+(m.get('objective') or '待约定')]
  if m.get('stop'):lines+=['','**做到哪里：** '+m['stop']]
  if m.get('pending_result'):lines+=['','**新稿待复核：** 此前成果已保留，尚未确认适用于这次修改。']
  if m.get('training_complete'):lines+=['','本轮动作已完成；按地图决定下一项或进入最后全文校对。']
  if 'training_map' not in m and m.get('overview'):lines+=['','**全文地图：**']+['- '+x for x in m['overview']]
  if 'training_map' not in m and m.get('remaining'):lines+=['','**剩余事项：**']+['- '+x for x in m['remaining']]
  outcome=m.get('outcome',{})
  if any(outcome.values()):
   lines+=['','## '+pair+'本轮变化','']
   for key,title in [('before','改前'),('after','改后'),('benefit','收益'),('tradeoff','取舍'),('takeaway','可复用的方法')]:
    if outcome.get(key):lines+=['**'+title+'：** '+outcome[key],'']
 if closed and 'training_map' in m:
  lines+=['']+map_lines(m) if m.get('close_with_unfinished') else folded('全文地图与最终处理', '\n'.join(map_lines(m)))
 if m.get('pending_result'):
  prior=m['pending_result'];body=[]
  for key,label in [('before','改前'),('after','改后'),('benefit','收益'),('tradeoff','取舍'),('takeaway','可复用的方法')]:
   if prior.get('outcome',{}).get(key):body+=['**'+label+'：** '+prior['outcome'][key],'']
  for entry in prior.get('version_notes',[]):body+=[entry['from_version']+' → '+entry['to_version'],entry['content'],'']
  lines+=folded('此前成果（对应修改前的稿件，待复核）','\n'.join(body))
 if closed and any(m.get('outcome',{}).values()) and not any(x['from_version']==m.get('base_version') and x['to_version']==m['current_version'] for x in m.get('version_notes',[])):
  gains=[]
  for key,title in [('before','改前'),('after','改后'),('benefit','收益'),('tradeoff','取舍'),('takeaway','可复用的方法')]:
   if m['outcome'].get(key):gains+=['**'+title+'：** '+m['outcome'][key],'']
  lines+=folded(pair+'本轮变化','\n'.join(gains))
 details=[]
 if not closed:
  for key,title in [('why','为什么练'),('output','留下什么')]:
   if m.get(key):details+=['**'+title+'：** '+m[key],'']
  if m.get('steps'):details+=['**怎么练：** '+' → '.join(m['steps']),'']
 if m.get('decisions'):details+=['**已作的选择：**']+['- '+x for x in m['decisions']]+['']
 if not closed and m.get('teaching'):
  t=m['teaching'];labels={'source':'方法来源','mechanism':'如何起作用','example_type':'示例类型','example':'相关示例','comparison':'差别与取舍','application':'本文尝试','check':'怎样检验'}
  details += [labels[k]+'：'+t[k] for k in labels]
 if not closed and m.get('process_note'):details+=[m['process_note']]
 lines+=folded('已确认的选择' if closed else '本轮说明与依据','\n'.join(details))
 if m.get('version_notes'):
  lines+=['','## 版本变化']
  for entry in m['version_notes']:lines+=folded(entry['from_version']+' → '+entry['to_version']+'｜具体变化与取舍',entry['content'])
 help_notes=[]
 for key,title,prior_title in [('assistance','实际帮助','帮助程度'),('evidence_limit','观察边界','检验边界')]:
  repeated=any(('**'+prior_title+'：** '+m.get(key,'')) in entry['content'].split('\n\n') for entry in m.get('version_notes',[]))
  if m.get(key) and not repeated:
   help_notes+=['**'+title+'：** '+m[key],'']
 lines+=folded('帮助与观察边界','\n'.join(help_notes))
 lines+=['','---','',REFLECTION.rstrip(),'']
 return '\n'.join(lines)+reflection

def validate_update(root,m,data):
 if not isinstance(data,dict) or set(data)-ALLOWED:fail('摘要包含不允许的字段：'+str(set(data)-ALLOWED if isinstance(data,dict) else '非对象'))
 lists={'steps','remaining','overview','decisions'}
 for k,v in data.items():
  if k in lists:
   if not isinstance(v,list) or any(not isinstance(x,str) for x in v):fail(k+'须为文本数组')
  elif k=='training_map':validate_map(v,m.get('training_map'))
  elif k=='content_review':validate_content_review(v)
  elif k=='teaching':validate_teaching(v)
  elif k=='version_notes':
   if not isinstance(v,list):fail('version_notes须为版本记录数组')
   seen=set()
   for entry in v:
    if not isinstance(entry,dict) or set(entry)!={'from_version','to_version','content'} or any(not isinstance(x,str) or not x.strip() for x in entry.values()):fail('版本记录须包含from_version、to_version、content')
    pair=(entry['from_version'],entry['to_version'])
    if pair in seen or pair[0]==pair[1]:fail('版本记录重复或前后版本相同')
    seen.add(pair)
    for item in pair:
     version(item)
     if item not in m.get('submissions',{}):fail('版本收益只能记录已提交的稿件')
  elif k=='training_complete':
   if not isinstance(v,bool):fail('training_complete须为布尔值')
  elif k=='outcome':
   if not isinstance(v,dict) or set(v)-{'before','after','benefit','tradeoff','takeaway'} or any(not isinstance(x,str) for x in v.values()):fail('outcome格式错误')
  elif not isinstance(v,str):fail(k+'须为文本')
 if 'stage' in data and data['stage'] not in {'plan','practice','compare','wrap'}:fail('结束必须使用close')
 n={**m,**{k:v for k,v in data.items() if k!='learner_reflection'}}
 if 'training_map' in n and n.get('stage')=='wrap' and map_blockers(n['training_map'],content_only=True):fail('地图仍有必须处理或正在练的内容事项，不能直接进入最后校对')
 if 'content_review' in data:
  ids={x['id'] for x in n.get('training_map',{}).get('items',[]) if x['kind']=='content' and x['status'] not in {'resolved','kept','withdrawn'}}
  if not set(n['content_review']['pending_choices'])<=ids:fail('内容待选择项须指向地图中的未处理内容事项')
 if 'content_review' in data and n['content_review']['status']=='ready' and map_blockers(n.get('training_map',empty_map()),content_only=True):fail('内容仍有必须处理或正在练的事项，不能标记ready')
 if n.get('stage')=='wrap' and ('stage' in data or 'content_review' in data):
  sha=digest(read(draft_path(root,locate(root,n['id']),n,n['current_version'])))
  if not content_ready(n,sha):fail('进入词句前须通过review留下对应当前全文的内容审核完成标记及取舍')
 if n.get('stage')=='practice' and (data.get('stage')=='practice' or any(k in data and data[k]!=m.get(k) for k in ['objective','method','steps','stop'])) and 'teaching' not in data:fail('本轮带练须显式提供方法与示例，不能沿用未复核的旧教学')
 if 'outcome' in data:n['outcome']={**m.get('outcome',{}),**data['outcome']}
 if n.get('base_version'):
  version(n['base_version'])
  if n['base_version'] not in m.get('submissions',{}):fail('对照基准须为已提交稿')
 if n.get('method'):method(root,n['method'])
 if n.get('stage')=='practice' and not all(n.get(k) for k in ['objective','method','steps','stop']):fail('进入练习前须有动作、方法、步骤和停止条件')
 if n.get('selected_version'):
  version(n['selected_version'])
  if not draft_path(root,locate(root,m['id']),n,n['selected_version']).is_file():fail('选用稿不存在')
 return n

def correct_record(root,m,data):
 # Correct explanations without reopening a finished exercise or certifying new work.
 fields={'completion_summary','decisions','process_note','version_notes','assistance','evidence_limit','outcome','training_map'}
 if not isinstance(data,dict) or set(data)-fields:fail('记录整理只接受说明与依据字段，不能改变阶段、版本或完成状态')
 n=validate_update(root,m,data)
 if 'training_map' in data:
  def evidence(mp):
   return (mp['checked_version'],mp['checked_sha256'],mp['proofread']['status'],[(x['id'],x['level'],x['kind'],x['status']) for x in mp['items']])
  if 'training_map' not in m or evidence(n['training_map'])!=evidence(m['training_map']):fail('记录整理不能改变地图事项、分级、结果状态或稿件绑定；须按练习流程复核')
 return n

def page_backup(root,folder,raw):
 p=inside(root,'.writing-practice/记录备份/'+ident(folder.name.split(' ',1)[0])+'.zip');entries={}
 if p.exists():
  with zipfile.ZipFile(io.BytesIO(read(p))) as z:
   if z.testzip():fail('记录备份损坏')
   entries={name:z.read(name) for name in z.namelist()}
 entries['练习页/'+digest(raw)+'.md']=raw
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in entries.items():z.writestr(name,data)
 return p,out.getvalue()

def save(root,folder,m,reflection,note='',extra=None):
 page=page_text(m,reflection);m['page_generated_sha256']=digest(generated_part(page).encode());m['updated_at']=now()
 pp=inside(root,folder/'R01 练习记录.md')
 writes={pp:page.encode(),state_path(root,m['id']):jbytes(m)}
 if pp.exists():
  old=pp.read_bytes()
  if OBS.get(pp.resolve())!=digest(old):fail("练习页读取后发生变更，已保留用户内容；请重新回读")
  if old!=page.encode():
   backup,data=page_backup(root,folder,old);writes[backup]=data
 if extra:writes.update(extra)
 transaction(root,writes)

def archive(root,additions=None):
 p=inside(root,'.writing-practice/稿件恢复.zip');raw=read(p) if p.exists() else None
 entries={}
 if raw:
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():fail('恢复包损坏')
   for name in z.namelist():entries[name]=z.read(name)
 for name,data in (additions or {}).items():
  if name in entries and entries[name]!=data:fail('不能覆盖恢复包中的旧版：'+name)
  entries[name]=data
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in entries.items():z.writestr(name,data)
 return p,out.getvalue(),entries

def submission_snapshot(root,m,v):
 version(v);info=m.get('submissions',{}).get(v)
 if not info:fail('版本尚未提交：'+v)
 key=info.get('archive_key',m['id']+'/'+v+'.md')
 _,_,entries=archive(root);raw=entries.get(key)
 if raw is None or digest(raw)!=info['sha256']:fail('恢复快照缺失或与提交不一致：'+v)
 return key,raw

def verify(root,folder,m,v):
 key,sealed=submission_snapshot(root,m,v)
 b=read(draft_path(root,folder,m,v))
 if b!=sealed:fail('稿件有新修改，请先读取最新全文再submit保存本次快照：'+v)
 return b

def status(root,id,include_read=False):
 folder,m,_=load(root,id,accept_page_change=include_read);changed=[]
 for v in m.get('submissions',{}):
  _,sealed=submission_snapshot(root,m,v)
  if read(draft_path(root,folder,m,v))!=sealed:changed.append(v)
 current=m['current_version']
 result={'id':id,'stage':m['stage'],'current_version':current,'current_draft':str(draft_path(root,folder,m,current)),'changed_versions':changed,'unsubmitted':current not in m.get('submissions',{}),'misplaced_candidates':[v for v in changed if v!=current]}
 if include_read:
  paths=[state_path(root,id),inside(root,folder/'R01 练习记录.md'),draft_path(root,folder,m,current)]
  state_raw,page_raw,raw=[read(p) for p in paths]
  if json.loads(state_raw)!=m or any(p.read_bytes()!=b for p,b in zip(paths,[state_raw,page_raw,raw])):fail('读取期间文件发生变更，请重新status --read')
  result.update(read_token=digest(state_raw+b'\0'+page_raw+b'\0'+raw),draft_text=raw.decode(),practice_page=page_raw.decode(),training_map=m.get('training_map'),map_current=map_current(m,digest(raw)))
  cr=m.get('content_review',{})
  result.update(content_review=cr,content_review_current=bool(cr and cr.get('checked_version')==current and cr.get('checked_sha256')==digest(raw)),content_ready=content_ready(m,digest(raw)))
  if cr and not result['content_review_current']:result['warning']='正文或版本已变化；R01中旧内容审核标记不适用于当前全文。'
 return result

def new_version(folder):
 nums=[int(p.stem.split(' ',1)[0][1:]) for p in folder.glob('V*.md') if VER.fullmatch(p.stem.split(' ',1)[0])]
 return 'V'+str(max(nums,default=0)+1).zfill(2)
def copy_version(raw,old,new):
 s=raw.decode()
 if s.startswith('---\n'):
  parts=s.split('---\n',2)
  if len(parts)==3:
   fm=parts[1]
   fm=re.sub(r'^version:.*$', 'version: '+json.dumps(new),fm,flags=re.M)
   fm=re.sub(r'^parent_version:.*$', 'parent_version: '+json.dumps(old),fm,flags=re.M)
   fm=re.sub(r'^assistance:.*$', 'assistance: "原样复制待本人修改"',fm,flags=re.M)
   return ('---\n'+fm+'---\n'+parts[2]).encode()
 return raw

def cell(s):return s.replace('|','\\|').replace('\n',' ')

def index(root):
 hp=root/'01 开始练习.md';s=text(hp);active=[];closed=[]
 for p in sorted((root/'.writing-practice/状态').glob('W*.json')):
  m=json_read(p);f=locate(root,m['id']);ref=str((f/'R01 练习记录.md').relative_to(root))
  title=cell(m['title']);finished=m['stage']=='closed'
  v=(m.get('accepted_version') or m['current_version']) if finished else m['current_version']
  draft=str(draft_path(root,f,m,v).relative_to(root))
  if finished:
   closed.append('- '+link(title,draft)+' · '+link('练习记录',ref))
  else:
   active.append('### '+title+'\n\n'+link('继续写正文',draft)+' · '+link('查看练习记录',ref))
 # Migrate old generated regions; ordinary Markdown headings/callouts are the anchors.
 for name in ('practice-index','practice-history'):
  begin='<!-- '+name+':start -->';end='<!-- '+name+':end -->'
  if begin not in s and end not in s:continue
  if s.count(begin)!=1 or s.count(end)!=1 or s.index(begin)>s.index(end):
   fail('首页旧索引区域不完整，请先核对入口内容')
  s=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end)+r'\n*','',s)
 anchor=r'(?m)^## 开始新的一篇[ \t]*$'
 if len(re.findall(anchor,s))!=1:fail('首页需要唯一的“开始新的一篇”标题，请先核对入口内容')
 # The active section is tool-maintained; personal prose in other sections is retained.
 active_pat=r'(?m)^## 正在写[ \t]*\n[\s\S]*?(?=^## |\Z)'
 if len(re.findall(active_pat,s))>1:fail('首页“正在写”区域不唯一，请先核对入口内容')
 s=re.sub(active_pat,'',s)
 block='## 正在写\n\n'+'\n\n'.join(active)+'\n\n' if active else ''
 s=re.sub(anchor,lambda m:block+m.group(0),s)
 history_pat=r'(?m)^> \[!note\]- 已结束的练习（\d+）[ \t]*\n(?:>[^\n]*(?:\n|$))*'
 if len(re.findall(history_pat,s))>1:fail('首页已结束练习区域不唯一，请先核对入口内容')
 history='\n'.join(folded('已结束的练习（'+str(len(closed))+'）','\n'.join(closed))).lstrip('\n')+'\n' if closed else ''
 if re.search(history_pat,s):s=re.sub(history_pat,lambda _:history,s)
 elif history:s=s.rstrip()+'\n\n'+history
 transaction(root,{hp:s.encode()})

def with_index(root,result):
 # The practice transaction is already committed; navigation failure must not invite a duplicate operation.
 try:index(root)
 except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:
  result.update(index='pending',warning='练习操作已保存，仅入口刷新失败：'+str(e)+'；核对后只重试index，不重做刚才的操作。')
 return result

def run(root,a):
 if a.command=='index':index(root);return {'index':'updated'}
 if a.command=='new':
  title=a.title.strip()
  if not title or len(title)>100 or any(ord(x)<32 or x in '/\\' for x in title):fail('题目为空、过长或含路径字符')
  nums=[int(p.stem[1:]) for p in (root/'.writing-practice/状态').glob('W*.json') if PID.fullmatch(p.stem)]
  id='W'+str(max(nums,default=0)+1).zfill(3);folder=inside(root,'00 我的练习/'+id+' '+title_filename(title))
  if folder.exists():fail('练习已存在')
  m={'schema':2,'id':id,'title':title,'stage':'plan','current_version':'V01','selected_version':'','accepted_version':'','method':'','objective':'','training_complete':False,'submissions':{},'reviews':[],'created_at':now(),'training_map':empty_map()}
  m['version_labels']={'V01':version_label(a.label or ('从已有记录导入原稿' if a.draft else '从空白开始写初稿'))}
  draft=Path(a.draft).read_bytes() if a.draft else ('# '+title+'\n\n').encode()
  draft.decode('utf-8')
  save(root,folder,m,'\n','创建练习；输入来自本人提供的文字，未作润色。' if a.draft else '创建空白工作稿，等待本人写作。',{draft_path(root,folder,m,'V01'):draft});return with_index(root,{'id':id,'draft':str(draft_path(root,folder,m,'V01'))})
 accept_page=a.command=='record' and a.accept_page_change
 if accept_page and not a.note:fail('接纳人工摘要修改须用--note交代实际修改与合并依据')
 folder,m,reflection=load(root,a.id,accept_page_change=accept_page)
 if a.command in {'record','review','next','close'}:require_read(root,folder,m,a)
 if a.command=='refresh':
  if getattr(a,'input',None):
   require_read(root,folder,m,a)
   verify(root,folder,m,m['current_version'])
   if m.get('training_map') and not map_current(m):fail('地图待复核，请先检阅当前稿；记录整理不代替review')
   m=correct_record(root,m,json.loads(Path(a.input).read_text(encoding='utf-8-sig')))
  save(root,folder,m,reflection)
 elif a.command=='record':
  if m['stage']=='closed':fail('已结束练习；明确继续时先用next准备工作稿')
  d=json.loads(Path(a.input).read_text(encoding='utf-8-sig'))
  if 'training_map' in d or 'content_review' in d:fail('地图及内容审核标记须随review核验当前稿；record不能代替全文复核')
  m=validate_update(root,m,d)
  if 'learner_reflection' in d:reflection='\n'+d['learner_reflection'].strip()+'\n'
  if a.note and 'process_note' not in d:m['process_note']=Path(a.note).read_text(encoding='utf-8-sig').strip()
  save(root,folder,m,reflection)
 elif a.command=='submit':
  if m['stage']=='closed':fail('已结束练习；明确继续时先用next准备工作稿')
  v=m['current_version'];version(v);raw=read(draft_path(root,folder,m,v));sha=digest(raw)
  previous=m['submissions'].get(v)
  if previous:
   _,sealed=submission_snapshot(root,m,v)
   if raw==sealed:
    m['stage']='compare';save(root,folder,m,reflection)
    return with_index(root,{'id':m['id'],'version':v,'sha256':sha,'already_submitted':True})
   m.setdefault('submission_history',[]).append({'version':v,**previous})
  key=m['id']+('/snapshots/'+v+'/'+sha+'.md' if previous else '/'+v+'.md')
  p,b,_=archive(root,{key:raw})
  m['submissions'][v]={'sha256':sha,'submitted_at':now(),'archive_key':key};m['stage']='compare'
  if previous:
   if not m.get('pending_result'):
    m['pending_result']={'version':v,'sha256':previous['sha256'],'outcome':m.get('outcome',{}),'version_notes':[x for x in m.get('version_notes',[]) if x['to_version']==v]}
   m.update(training_complete=False,outcome={},process_note='',completion_summary='',next_action='已保存同版修改，按最新全文对照检验。')
   # Keep prior results explicitly pending, never present them as verified for the new text.
   m['version_notes']=[x for x in m.get('version_notes',[]) if x['to_version']!=v]
  save(root,folder,m,reflection,'保存'+v+'本次精确快照。',{p:b})
 elif a.command=='next':
  if m.get('pending_result'):fail('当前稿已有修改，先复核保留的成果再换动作')
  if not a.reason.strip():fail('须记录建版理由或本人实际选择')
  if m['stage']=='closed' and a.basis!='user':fail('已结束练习仅能按本人明确要求重开')
  if 'training_map' in m and a.basis=='phase' and not map_current(m):fail('阶段建版前先检阅当前完整稿和地图')
  v=m['current_version'];raw=verify(root,folder,m,v);n=new_version(folder)
  m.setdefault('version_labels',{})[n]=version_label(a.label)
  retain_outcome(m)
  m['process_note']=''
  m['last_choice']=a.reason
  m.setdefault('version_decisions',[]).append({'from':v,'to':n,'basis':a.basis,'reason':a.reason,'at':now()})
  m.pop('close_with_unfinished',None);m.pop('close_reason',None)
  m['working_copy_from']=v
  if a.cleanup and not content_ready(m,digest(raw)):fail('仅校对建版前须有当前稿内容审核完成且可进入词句的标记')
  if a.cleanup and 'training_map' in m and map_blockers(m['training_map'],content_only=True):fail('仍有内容事项，不能以收尾建版跳过')
  if a.cleanup:
   m.update(current_version=n,stage='wrap',next_action='仅校对或整理全文；已有训练成果保留，不新增训练。')
  else:
   m.update(base_version=v,current_version=n,stage='practice',training_complete=False,outcome={},evidence_limit='',next_action='按本人选定动作修改当前工作稿，完成后再送评。')
  if 'training_map' in m:
   m.update(base_version=v,training_complete=False,outcome={},completion_summary='')
   m['training_map']['proofread']={'status':'pending','note':''}
   if not a.cleanup:m.update(stage='plan',next_action='已准备本轮工作稿；按地图确定当前动作，同轮小修继续此版。')
  save(root,folder,m,reflection,'从'+v+'准备'+n+('（只作收尾整理）' if a.cleanup else '')+'。本人选择：'+a.reason,{draft_path(root,folder,m,n):copy_version(raw,v,n)})
 elif a.command=='review':
  v=m['current_version'];verify(root,folder,m,v)
  if m['stage'] not in {'compare','wrap'}:fail('当前不是待评价的提交稿')
  if getattr(a,'sha256',None)!=m['submissions'][v]['sha256']:fail('反馈快照不匹配，请核对最新全文和submit返回的sha256')
  feedback=Path(a.input).read_text(encoding='utf-8-sig')
  if not feedback.strip():fail('反馈不能为空')
  d=json.loads(Path(a.summary).read_text(encoding='utf-8-sig'))
  if not isinstance(d,dict) or d.get('stage') not in {'plan','practice','wrap'}:fail('反馈须明确stage为plan、practice或wrap；不自动推断是否继续训练')
  if 'content_review' not in d:fail('全文检阅须提交中心、材料、段落、顺序、结尾的审核记录')
  cr=validate_content_review(d['content_review'])
  cr.update(checked_version=v,checked_sha256=m['submissions'][v]['sha256'])
  pending=m.get('pending_result')
  if pending and ('outcome' not in d or (pending.get('version_notes') and 'version_notes' not in d)):fail('新稿须明确复核outcome及此前版本成果；不适用的项可明确清空')
  if 'training_map' in m or 'training_map' in d:
   if 'training_map' not in d:fail('本轮反馈须逐项回看并提交完整training_map')
   mp=validate_map(d['training_map'],m.get('training_map'))
   if not mp['purpose'].strip():fail('首次全文评价须说明本篇目的')
   if mp['proofread']['status']=='checked' and (d['stage']!='wrap' or map_blockers(mp,content_only=True)):fail('内容事项处理后，才能在最后收尾标记全文校对完成')
   mp.update(checked_version=v,checked_sha256=m['submissions'][v]['sha256'])
  m=validate_update(root,m,d)
  m.pop('pending_result',None)
  if 'learner_reflection' in d:reflection='\n'+d['learner_reflection'].strip()+'\n'
  m['process_note']=d.get('process_note',feedback.strip())
  snapshot_key,_=submission_snapshot(root,m,v)
  review={'version':v,'sha256':m['submissions'][v]['sha256'],'snapshot_key':snapshot_key,'method':method(root,m['method']) if m.get('method') else None,'at':now()}
  payload=jbytes({**review,'feedback':feedback,'summary':d})
  key=m['id']+'/feedback/'+v+'/'+review['sha256']+'/'+digest(payload)+'.json'
  ap,raw,_=archive(root,{key:payload});review['feedback_key']=key;m['reviews'].append(review)
  save(root,folder,m,reflection,extra={ap:raw})
 elif a.command=='close':
  if not a.reason.strip():fail('须有本人明确结束依据')
  verify(root,folder,m,version(a.version))
  if a.version==m['current_version'] and m.get('pending_result'):fail('最新稿的成果仍待复核，不能直接结束')
  if not any(r['version']==a.version and r['sha256']==m['submissions'][a.version]['sha256'] for r in m.get('reviews',[])):fail('采用稿最新快照尚未检阅，请先review再结束')
  if 'training_map' in m:
   if a.version!=m['current_version']:
    matches=[r for r in m['reviews'] if r['version']==a.version and r['sha256']==m['submissions'][a.version]['sha256']]
    _,_,entries=archive(root);payload=json.loads(entries[matches[-1]['feedback_key']])
    mp=payload['summary'].get('training_map')
    if not mp:fail('较早稿没有对应地图，不能套用后续结论；明确继续后先复核该稿')
    m['training_map']=mp
    m['content_review']=payload['summary'].get('content_review',{})
   mp=m['training_map'];validate_map(mp)
   if mp['checked_version']!=a.version or mp['checked_sha256']!=m['submissions'][a.version]['sha256']:fail('地图未核验采用稿，请先review')
   cr=m.get('content_review',{})
   content_done=cr.get('status')=='ready' and not cr.get('pending_choices') and cr.get('checked_version')==a.version and cr.get('checked_sha256')==m['submissions'][a.version]['sha256']
   unfinished=bool(not content_done or map_blockers(mp) or mp['proofread']['status']!='checked')
   if unfinished and not a.allow_unfinished:fail('必要事项或最后全文校对尚未完成；本人明确保留遗留并结束时才可allow-unfinished')
   m['close_with_unfinished']=unfinished
   m['close_reason']=a.reason
   if unfinished:m.update(completion_summary='按本人选择结束，地图中的遗留事项如实保留；未宣称全部完成。',training_complete=False)
  if a.version!=m['current_version']:
   m.pop('pending_result',None)
   m.update(outcome={},training_complete=False,base_version='',process_note='',assistance='',completion_summary='按本人选择采用'+a.version+'结束；较后版本的修改不计作本次采用稿的收益。',evidence_limit='本次选择较早稿件；没有将后续版本的收益套用到采用稿。')
  m.update(stage='closed',accepted_version=a.version,selected_version=a.version,current_version=a.version,steps=[],next_action='本次已结束，采用'+a.version+'。以后可换新题再练。')
  save(root,folder,m,reflection,'本人明确结束并采用'+a.version+'：'+a.reason)
 elif a.command=='recover':
  if not a.reason.strip():fail('须有保留修改并恢复旧版的授权')
  if m['stage']=='closed':fail('已结束练习不能通过恢复自动重开；保留原件，先明确后续安排')
  v=version(a.version);changed=read(draft_path(root,folder,m,v));info=m['submissions'].get(v)
  if not info or digest(changed)==info['sha256']:fail('没有需要恢复的稿件变化')
  _,sealed=submission_snapshot(root,m,v)
  if getattr(a,'into_current',False):
   n=m['current_version']
   if m['stage']=='closed' or n==v or n in m['submissions']:fail('只能归入尚未送评的当前工作稿')
   target=draft_path(root,folder,m,n)
   if read(target)!=copy_version(sealed,v,n):fail('当前工作稿也有修改；保留两边，先核对，不覆盖')
  else:
   current=m['current_version']
   if current!=v:
    if current in m['submissions']:verify(root,folder,m,current)
    else:
     source=m.get('working_copy_from') or m.get('base_version') or v
     _,original=submission_snapshot(root,m,source)
     if read(draft_path(root,folder,m,current))!=copy_version(original,source,current):fail('当前工作稿也有修改；保留两边，先核对，不改变当前入口')
   n=new_version(folder);m.setdefault('version_labels',{})[n]=version_label(a.label)
  m['working_copy_from']=v
  m.update(current_version=n,stage='practice',training_complete=False,outcome={},evidence_limit='',next_action='新文字已保存在'+n+'，旧稿已恢复；核对当前工作稿后继续。')
  save(root,folder,m,reflection,extra={draft_path(root,folder,m,n):copy_version(changed,v,n),draft_path(root,folder,m,v):sealed})
 return with_index(root,{'id':m['id'],'stage':m['stage'],'current_version':m['current_version'],'sha256':m.get('submissions',{}).get(m['current_version'],{}).get('sha256')})

def check(root):
 errors=[];pending=[];states=list((root/'.writing-practice/状态').glob('W*.json'))
 if (root/'.writing-practice/transaction.json').exists():errors.append('未完成事务')
 if list(root.rglob('*.pending')):errors.append('存在pending文件')
 for p in states:
  try:
   f,m,_=load(root,p.stem)
   if m['stage'] not in STAGES:fail('未知阶段')
   for v in m.get('submissions',{}):
    _,sealed=submission_snapshot(root,m,v)
    if read(draft_path(root,f,m,v))!=sealed:
     if m['stage']!='closed' and v==m['current_version']:pending.append(m['id']+'/'+v)
     else:fail('对照稿或已结束稿有变化，请先核对并保留修改：'+v)
   _,_,entries=archive(root)
   for rev in m.get('reviews',[]):
    if rev.get('snapshot_key'):
     if rev['snapshot_key'] not in entries or digest(entries[rev['snapshot_key']])!=rev['sha256']:fail('历史反馈所对应快照缺失或被修改')
     feedback_raw=entries[rev['feedback_key']]
     if digest(feedback_raw)!=Path(rev['feedback_key']).stem:fail('历史反馈内容被修改')
     payload=json.loads(feedback_raw)
     if payload['sha256']!=rev['sha256'] or payload['snapshot_key']!=rev['snapshot_key']:fail('反馈与快照关联不一致')
   if not draft_path(root,f,m,m['current_version']).exists():fail('缺当前稿')
   for k in ['selected_version','accepted_version']:
    if m.get(k) and not draft_path(root,f,m,m[k]).exists():fail('版本指针失效')
   for v,label in m.get('version_labels',{}).items():
    version_label(label)
    if not draft_path(root,f,m,v).is_file():fail('带说明的版本文件缺失：'+v)
   validate_update(root,m,{k:m[k] for k in ['base_version','version_notes'] if k in m})
   if m.get('method'):method(root,m['method'])
   if 'training_map' in m:
    validate_map(m['training_map'])
    if m['stage']=='closed' and not m.get('close_with_unfinished') and (not map_current(m) or map_blockers(m['training_map']) or m['training_map']['proofread']['status']!='checked'):fail('结束状态与地图或全文校对不一致')
   if m['stage']=='closed' and m.get('accepted_version') not in m['submissions']:fail('结束稿未提交')
  except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:errors.append(p.name+': '+str(e))
 for p in (root/'00 我的练习').glob('*/R01 练习记录.md'):
  try:
   if not state_path(root,p.parent.name.split(' ',1)[0]).exists():errors.append('缺集中状态：'+str(p))
  except ValueError:errors.append('练习目录身份错误：'+str(p))
 return {'ok':not errors,'practice_count':len(states),'errors':errors,'pending_drafts':pending}

def main():
 configure_runtime()
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True)
 sub=ap.add_subparsers(dest='command',required=True)
 p=sub.add_parser('new');p.add_argument('--title',required=True);p.add_argument('--draft');p.add_argument('--label',help='V01来源说明；默认区分导入原稿与从空白起稿')
 p=sub.add_parser('record',help='只更新当前摘要；字段：'+', '.join(sorted(ALLOWED)));p.add_argument('id');p.add_argument('--input',required=True);p.add_argument('--note');p.add_argument('--read-token');p.add_argument('--accept-page-change',action='store_true',help='理解人工修改后合并摘要，完整旧页存隐藏后台记录备份，须同时提供note')
 for cmd in ['submit','next','review','close','recover']:
  p=sub.add_parser(cmd);p.add_argument('id')
  if cmd in ['next','close','recover']:p.add_argument('--reason',required=True)
  if cmd in ['close','recover']:p.add_argument('--version',required=True)
  if cmd in ['next','recover']:p.add_argument('--label',required=(cmd=='next'),help='这个版本的主要修改动作，简短具体')
  if cmd in ['next','review','close']:p.add_argument('--read-token')
  if cmd=='close':p.add_argument('--allow-unfinished',action='store_true',help='仅在本人明确保留遗留并结束时使用，不标作全部完成')
  if cmd=='next':p.add_argument('--basis',choices=['phase','user'],default='user');p.add_argument('--cleanup',action='store_true',help='只整理全文，保留已有训练成果')
  if cmd=='review':p.add_argument('--input',required=True);p.add_argument('--summary',required=True);p.add_argument('--sha256',required=True,help='本次实际检阅的submit快照哈希')
  if cmd=='recover':p.add_argument('--into-current',action='store_true',help='归入已有且未改动的当前工作稿，不新增版本')
 for cmd in ['status','refresh']:
  p=sub.add_parser(cmd);p.add_argument('id')
  if cmd=='status':p.add_argument('--read',action='store_true',help='返回最新全文、R01、地图与本轮读取凭据，不写文件')
  else:
   p.add_argument('--input',help='仅整理记录说明与依据，不改变训练状态；须先回读')
   p.add_argument('--read-token')
 sub.add_parser('check');sub.add_parser('index')
 a=ap.parse_args();root=a.root.expanduser().resolve()
 if not (root/'.writing-practice/workspace.json').is_file() or json_read(inside(root,'.writing-practice/workspace.json'))!={'skill':'lukk-writing-practice','layout':4}:fail('请先用本Skill的scripts/init_workspace.py连接练习目录')
 if menu_text(read(inside(root,'03 练习方法.md')))!=menu_text(read(inside(SKILL,'references/方法/方法菜单.md'))):fail('菜单与Skill不一致，请先运行本Skill的init_workspace.py --root <练习目录>同步')
 if a.command=='check':result=check(root)
 elif a.command=='status':result=status(root,a.id,a.read)
 else:
  with lock(root):result=run(root,a)
 print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('ok',True) else 1
if __name__=='__main__':
 try:sys.exit(main())
 except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:print('停止：'+str(e),file=sys.stderr);sys.exit(2)
