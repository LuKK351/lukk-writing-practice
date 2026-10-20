#!/usr/bin/env python3
"""连接用户指定的 Obsidian 练习目录；只初始化个人文件，不复制 Skill 规则。"""
import argparse,json,os,shutil,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
from practice import menu_text,configure_runtime

SKILL=Path(__file__).resolve().parents[1]
METADATA={'skill':'lukk-writing-practice','layout':4}
META='.writing-practice/workspace.json'
MENU='03 练习方法.md'
SOURCE_MENU='方法菜单.md'

def default_config():
 return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'lukk-writing-practice/workspace.json'

def no_symlink(p):
 if p.is_symlink():raise ValueError('不覆盖符号链接：'+str(p))

def vault_for(root,explicit=None):
 if explicit:
  vault=explicit.expanduser().resolve()
  try:root.relative_to(vault)
  except ValueError:raise ValueError('练习目录不在所选 Obsidian 库中')
  if not (vault/'.obsidian').is_dir():raise ValueError('所选目录没有 .obsidian 库标记；请先在 Obsidian 中打开或创建库')
  return vault
 for p in [root,*root.parents]:
  if (p/'.obsidian').is_dir():return p
 raise ValueError('未找到上级 Obsidian 库；请指定已有库内的练习目录，或先在 Obsidian 中创建库')

def config_read(path):
 if not path.exists():return None
 value=json.loads(path.read_text(encoding='utf-8'))
 if not isinstance(value,dict) or not isinstance(value.get('root'),str):raise ValueError('本机绑定格式有误，请核对：'+str(path))
 return value

def inspect(config,root=None):
 binding=config_read(config);candidates=set();notes=[]
 if root:
  try:candidates.add(str(vault_for(root.expanduser().resolve())))
  except ValueError as e:notes.append(str(e))
 # Read only Obsidian's known registry locations; never crawl personal documents.
 registries=[Path.home()/'Library/Application Support/obsidian/obsidian.json',Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'obsidian/obsidian.json']
 if os.environ.get('APPDATA'):registries.append(Path(os.environ['APPDATA'])/'obsidian/obsidian.json')
 for p in registries:
  if not p.is_file():continue
  try:
   data=json.loads(p.read_text(encoding='utf-8'))
   for item in data.get('vaults',{}).values():
    location=Path(item['path']).expanduser().resolve()
    if (location/'.obsidian').is_dir():candidates.add(str(location))
  except (ValueError,OSError,KeyError,TypeError,AttributeError):notes.append('无法解析 Obsidian 库登记：'+str(p))
 status='unbound'
 if binding:
  r=Path(binding['root']).expanduser().resolve()
  status='missing'
  if r.is_dir():
   try:
    v=vault_for(r);candidates.add(str(v))
    status='ready' if (r/META).is_file() and json.loads((r/META).read_text(encoding='utf-8'))==METADATA else 'unrecognized'
   except (ValueError,OSError):status='invalid_vault'
 return {'binding':binding,'binding_status':status,'vault_candidates':sorted(candidates),'config':str(config),'notes':notes}

def atomic_write(path,raw):
 no_symlink(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(raw)
  no_symlink(path);os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)

def probe(directory):
 # Actually create/remove only our own temporary file instead of trusting mode bits.
 fd,name=tempfile.mkstemp(prefix='.writing-access-中文 空格-',dir=directory)
 try:
  with os.fdopen(fd,'wb') as f:f.write('写作练习 UTF-8 ✓'.encode('utf-8'))
  if Path(name).read_text(encoding='utf-8')!='写作练习 UTF-8 ✓':raise ValueError('目录读写检验失败')
 finally:Path(name).unlink(missing_ok=True)

def check_environment():
 # Isolated probe: do not create a vault, bind a directory or touch real exercises.
 with tempfile.TemporaryDirectory(prefix='writing-env-') as folder:
  directory=Path(folder)/'中文 路径';directory.mkdir();probe(directory)
 return {'ok':True,'python_version':sys.version.split()[0],
         'python_executable':sys.executable,'temporary_directory':tempfile.gettempdir(),
         'checks':['python>=3.10','utf8_read_write','unicode_and_space_paths']}

def validate_source():
 required=['SKILL.md','references/流程.md','references/工具使用.md','references/方法/'+SOURCE_MENU,'scripts/practice.py','assets/01 开始练习.md','assets/02 选题库.md']
 required+=['references/规则/'+x+'.md' for x in ['开练','诊断','教学','对照','收尾','记录']]
 for i in range(1,9):
  choices=list((SKILL/'references/方法').glob('M%02d *.md'%i))
  if len(choices)!=1:raise ValueError('Skill 方法缺失或不唯一：M%02d'%i)
  required.append(str(choices[0].relative_to(SKILL)))
 for rel in required:
  p=SKILL/rel
  if not p.is_file() or p.is_symlink():raise ValueError('Skill 资源缺失或异常：'+rel)
  p.read_bytes()

def initialize(root,vault):
 validate_source()
 # A dedicated practice subfolder keeps unrelated vault files out of the workspace.
 if root==vault:raise ValueError('请选择 Obsidian 库中的练习子目录，不直接占用整个库')
 ancestor=root
 while ancestor!=vault:
  no_symlink(ancestor);ancestor=ancestor.parent
 no_symlink(root)
 exists=root.exists() and root.is_dir() and any(root.iterdir())
 if root.exists() and not root.is_dir():raise ValueError('目标不是目录')
 if exists:
  for rel in ['.writing-practice',META,MENU,'01 开始练习.md','00 我的练习','.writing-practice/状态']:
   no_symlink(root/rel)
  meta=root/META
  if not meta.is_file() or json.loads(meta.read_text(encoding='utf-8'))!=METADATA:raise ValueError('目标非空且不是已连接的新布局；不覆盖或重置，请先核对迁移')
  if not (root/'01 开始练习.md').is_file():raise ValueError('已有练习缺少练习入口，请先核对恢复；不重置')
  for rel in ['00 我的练习','.writing-practice/状态']:
   if not (root/rel).is_dir():raise ValueError('已有练习缺少核心目录：'+rel+'；请先找回或核对迁移，不创建空目录代替')
  probe(root)
  for rel in ['00 我的练习','.writing-practice/状态']:probe(root/rel)
  menu=root/MENU;raw=(SKILL/'references/方法'/SOURCE_MENU).read_bytes()
  changed=not menu.exists() or menu_text(menu.read_bytes())!=menu_text(raw)
  if changed:atomic_write(menu,raw)
  return 'already_initialized',changed
 root.parent.mkdir(parents=True,exist_ok=True);probe(root.parent)
 stage=Path(tempfile.mkdtemp(prefix='.writing-init-',dir=root.parent))
 try:
  for rel in ['01 开始练习.md','02 选题库.md']:shutil.copy2(SKILL/'assets'/rel,stage/rel)
  shutil.copy2(SKILL/'references/方法'/SOURCE_MENU,stage/MENU)
  for rel in ['00 我的练习','.writing-practice/状态']:(stage/rel).mkdir(parents=True,exist_ok=True)
  (stage/META).write_text(json.dumps(METADATA,ensure_ascii=False)+'\n',encoding='utf-8')
  if root.exists():root.rmdir() # Fails rather than overwriting files added concurrently.
  os.rename(stage,root)
 finally:
  if stage.exists():shutil.rmtree(stage)
 return 'created',True

def main():
 configure_runtime()
 p=argparse.ArgumentParser(description=__doc__)
 mode=p.add_mutually_exclusive_group()
 mode.add_argument('--inspect',action='store_true',help='只读查看绑定与可检测的库')
 mode.add_argument('--check-env',action='store_true',help='在系统临时目录检查运行环境，不建立或绑定练习')
 p.add_argument('--root',type=Path);p.add_argument('--vault',type=Path)
 p.add_argument('--bind',action='store_true',help='将已确认目录保存在本机配置中')
 p.add_argument('--config',type=Path,default=default_config());a=p.parse_args()
 if a.check_env:
  if a.root or a.vault or a.bind:p.error('--check-env 不与练习目录或绑定操作混用')
  print(json.dumps(check_environment(),ensure_ascii=False,indent=2));return
 config=a.config.expanduser().absolute()
 if a.inspect:
  if a.bind:raise ValueError('只读检查不能同时绑定')
  result=inspect(config,a.root)
 else:
  if not a.root:raise ValueError('请提供用户已确认的 --root 目录')
  # Check lexical path first, before resolve would hide a symlinked write target.
  given=a.root.expanduser().absolute()
  for ancestor in [given,*given.parents]:
   if (ancestor/'.obsidian').is_dir():break
   no_symlink(ancestor)
  root=given.resolve();vault=vault_for(root,a.vault)
  result,changed=initialize(root,vault)
  if a.bind:
   binding={'schema':2,'root':str(root),'vault':str(vault)}
   if config_read(config)!=binding:atomic_write(config,(json.dumps(binding,ensure_ascii=False,indent=2)+'\n').encode())
  result={'result':result,'root':str(root),'vault':str(vault),'bound':a.bind,'menu_synced':changed,'config':str(config)}
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
 try:main()
 except (ValueError,OSError,KeyError,TypeError) as e:print('停止：'+str(e),file=sys.stderr);sys.exit(2)
