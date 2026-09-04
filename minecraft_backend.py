import json, os, pathlib, platform, re, shlex, subprocess, tarfile, tempfile, urllib.request, zipfile, xml.etree.ElementTree as ET

MANIFEST="https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
SYSTEM_OS="windows" if os.name=="nt" else "linux"
MACHINE=platform.machine().lower()
SYSTEM_ARCH="x86_64" if MACHINE in ("amd64","x86_64") else ("x86" if MACHINE in ("x86","i386","i686") else MACHINE)

def rules_allowed(rules):
 if not rules:return True
 result=False
 for rule in rules:
  osrule=rule.get('os',{});os_match=osrule.get('name') in (None,SYSTEM_OS)
  if osrule.get('arch') and osrule['arch']!=SYSTEM_ARCH:os_match=False
  features_match=all(not wanted for wanted in rule.get('features',{}).values())
  if os_match and features_match:result=rule.get('action')=='allow'
 return result

class Installer:
 def __init__(self,root,progress=lambda p,t:None,java_override='auto'):self.root=pathlib.Path(root);self.progress=progress;self.java_override=java_override
 def get_json(self,url):
  req=urllib.request.Request(url,headers={"User-Agent":"Zazu-Launcher/0.4.2"});return json.load(urllib.request.urlopen(req,timeout=45))
 def download(self,url,path,label="Downloading",start=0,end=99):
  path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
  if path.is_file() and path.stat().st_size:self.progress(end,label);return
  req=urllib.request.Request(url,headers={"User-Agent":"Zazu-Launcher/0.4.2"})
  with urllib.request.urlopen(req,timeout=60) as src:
   size=int(src.headers.get('Content-Length',0));received=0
   tmp=path.with_suffix(path.suffix+'.part')
   with open(tmp,'wb') as out:
    while True:
     block=src.read(131072)
     if not block:break
     out.write(block);received+=len(block)
     if size:self.progress(min(end,start+int((end-start)*received/size)),label)
   tmp.replace(path)
  self.progress(end,label)
 def install(self,instance,version,loader):
  game=pathlib.Path(instance)/"minecraft";game.mkdir(parents=True,exist_ok=True);shared=self.root/"minecraft-data";versions=shared/"versions";libraries=shared/"libraries";assets=shared/"assets";natives=game/"natives";natives.mkdir(exist_ok=True)
  self.progress(1,"Loading Minecraft catalogue");manifest=self.get_json(MANIFEST);entry=next((v for v in manifest['versions'] if v['id']==version),None)
  if not entry:raise RuntimeError("Minecraft version is not in Mojang's catalogue")
  meta_path=versions/version/(version+'.json');self.download(entry['url'],meta_path,"Version information",1,3);base=json.loads(meta_path.read_text());profile=base;java_major=base.get('javaVersion',{}).get('majorVersion',8);java=self.java(java_major,3,13)
  if loader=="Fabric":self.progress(13,"Loading Fabric profile");profile=self.fabric(version,base,libraries);self.progress(19,"Fabric profile ready")
  elif loader=="Quilt":self.progress(13,"Loading Quilt profile");profile=self.quilt(version,base,libraries);self.progress(19,"Quilt profile ready")
  elif loader=="Forge":profile=self.forge(version,base,shared,java)
  elif loader=="NeoForge":profile=self.neoforge(version,base,shared,java)
  elif loader not in ("Vanilla",):raise RuntimeError("Unsupported loader: "+loader)
  else:self.progress(19,"Vanilla profile ready")
  client=versions/version/(version+'.jar');self.download(base['downloads']['client']['url'],client,"Minecraft client",20,30)
  classpath=[];library_jobs=[]
  for lib in profile.get('libraries',[]):
   if not self.allowed(lib.get('rules')):continue
   downloads=lib.get('downloads',{});artifact=downloads.get('artifact')
   if artifact:
    target=libraries/artifact['path'];library_jobs.append((artifact.get('url') or self.maven_url(lib['name']),target,"Libraries",None));classpath.append(str(target))
   elif lib.get('name'):
    rel=self.maven_path(lib['name']);target=libraries/rel;repository=lib.get('url','https://libraries.minecraft.net/');library_jobs.append((repository.rstrip('/')+'/'+rel,target,"Libraries",None));classpath.append(str(target))
   classifier=self.native_classifier(lib)
   if classifier and classifier in downloads.get('classifiers',{}):
    item=downloads['classifiers'][classifier];target=libraries/item['path'];library_jobs.append((item['url'],target,"Native libraries",lib.get('extract',{}).get('exclude',[])))
  for number,(url,target,label,exclude) in enumerate(library_jobs):
   start=31+int(19*number/max(1,len(library_jobs)));end=31+int(19*(number+1)/max(1,len(library_jobs)));self.download(url,target,label,start,end)
   if exclude is not None:self.extract_natives(target,natives,exclude)
  classpath.append(str(client));index=base['assetIndex'];index_path=assets/"indexes"/(index['id']+'.json');self.download(index['url'],index_path,"Asset index",50,52);objects=json.loads(index_path.read_text()).get('objects',{})
  for i,(name,obj) in enumerate(objects.items()):
   h=obj['hash'];start=52+int(47*i/max(1,len(objects)));end=52+int(47*(i+1)/max(1,len(objects)));self.download("https://resources.download.minecraft.net/"+h[:2]+"/"+h,assets/"objects"/h[:2]/h,"Assets "+str(i+1)+"/"+str(len(objects)),start,end)
  record={"version":version,"loader":loader,"java":str(java),"javaMajor":java_major,"mainClass":profile['mainClass'],"classpath":classpath,"assets":str(assets),"assetIndex":index['id'],"versionType":base.get('type','release'),"arguments":profile.get('arguments',{}),"legacyArguments":profile.get('minecraftArguments',''),"natives":str(natives),"client":str(client)}
  (pathlib.Path(instance)/"instance-launch.json").write_text(json.dumps(record,indent=2));self.progress(100,"Installed successfully");return record
 def fabric(self,version,base,libraries):
  loaders=self.get_json("https://meta.fabricmc.net/v2/versions/loader/"+version)
  if not loaders:raise RuntimeError("Fabric is not available for "+version)
  lv=loaders[0]['loader']['version'];profile=self.get_json(f"https://meta.fabricmc.net/v2/versions/loader/{version}/{lv}/profile/json");return self.merge(base,profile)
 def quilt(self,version,base,libraries):
  loaders=self.get_json("https://meta.quiltmc.org/v3/versions/loader/"+version)
  if not loaders:raise RuntimeError("Quilt is not available for "+version)
  lv=loaders[0]['loader']['version'];profile=self.get_json(f"https://meta.quiltmc.org/v3/versions/loader/{version}/{lv}/profile/json");return self.merge(base,profile)
 def forge(self,version,base,shared,java):
  promos=self.get_json("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json").get('promos',{});build=promos.get(version+'-recommended') or promos.get(version+'-latest')
  if not build:raise RuntimeError("Forge is not available for "+version)
  coordinate=version+'-'+build;url=f"https://maven.minecraftforge.net/net/minecraftforge/forge/{coordinate}/forge-{coordinate}-installer.jar";return self.run_installer(url,base,shared,java,'forge')
 def neoforge(self,version,base,shared,java):
  raw=urllib.request.urlopen("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",timeout=30).read();versions=[v.text for v in ET.fromstring(raw).iter('version')];prefix=version[2:] if version.startswith('1.') else version;matches=[v for v in versions if v.startswith(prefix+'.')]
  if not matches:raise RuntimeError("NeoForge is not available for "+version)
  build=matches[-1];url=f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{build}/neoforge-{build}-installer.jar";return self.run_installer(url,base,shared,java,'neoforge')
 def run_installer(self,url,base,shared,java,kind):
  shared=pathlib.Path(shared);(shared/'launcher_profiles.json').write_text('{"profiles":{},"settings":{}}');before=set((shared/'versions').glob('*/*.json'));installer=shared/'installers'/(kind+'-installer.jar');self.download(url,installer,kind.title()+" installer",13,16);self.progress(17,"Running "+kind.title()+" installer")
  flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if SYSTEM_OS=='windows' else 0;result=subprocess.run([str(java),'-jar',str(installer),'--installClient',str(shared)],capture_output=True,text=True,timeout=300,creationflags=flags)
  if result.returncode:raise RuntimeError(kind.title()+" installer failed: "+(result.stderr or result.stdout)[-800:])
  after=set((shared/'versions').glob('*/*.json'));candidates=list(after-before) or [p for p in after if kind in p.as_posix().lower()]
  if not candidates:raise RuntimeError(kind.title()+" did not create a launch profile")
  profile=json.loads(max(candidates,key=lambda p:p.stat().st_mtime).read_text());self.progress(19,kind.title()+" profile ready");return self.merge(base,profile)
 def merge(self,base,extra):
  out=dict(base);out['mainClass']=extra.get('mainClass',base['mainClass']);out['libraries']=base.get('libraries',[])+extra.get('libraries',[]);a={"game":[],"jvm":[]}
  for k in a:a[k]=base.get('arguments',{}).get(k,[])+extra.get('arguments',{}).get(k,[])
  out['arguments']=a;return out
 def maven_url(self,name):
  group,artifact,version=name.split(':')[:3];return "https://libraries.minecraft.net/"+group.replace('.','/')+f"/{artifact}/{version}/{artifact}-{version}.jar"
 def maven_path(self,name):
  parts=name.split(':');group,artifact,version=parts[:3];classifier=('-'+parts[3]) if len(parts)>3 else '';return group.replace('.','/')+f"/{artifact}/{version}/{artifact}-{version}{classifier}.jar"
 def allowed(self,rules):
  return rules_allowed(rules)
 def native_classifier(self,lib):
  value=lib.get('natives',{}).get(SYSTEM_OS);bits='64' if SYSTEM_ARCH=='x86_64' else '32';return value.replace('${arch}',bits) if value else None
 def extract_natives(self,archive,target,exclude):
  with zipfile.ZipFile(archive) as z:
   for n in z.namelist():
    if n.endswith('/') or n.startswith('META-INF/') or any(n.startswith(x) for x in exclude):continue
    pathlib.Path(target/n).parent.mkdir(parents=True,exist_ok=True)
    with z.open(n) as src,open(target/n,'wb') as dst:dst.write(src.read())
 def java(self,major,start=5,end=15):
  if self.java_override and self.java_override!='auto':
   candidate=pathlib.Path(self.java_override).expanduser()
   if not candidate.is_file():raise RuntimeError("The configured Java executable was not found")
   return candidate
  executable="java.exe" if SYSTEM_OS=="windows" else "java";managed=self.root/"java"/str(major);candidates=list(managed.glob("**/bin"+"/"+executable))
  if candidates:return candidates[0]
  for candidate in (executable,):
   try:
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if SYSTEM_OS=='windows' else 0;out=subprocess.check_output([candidate,'-version'],stderr=subprocess.STDOUT,text=True,creationflags=flags);m=re.search(r'version "(?:1\.)?(\d+)',out)
    if m and int(m.group(1))==major:return pathlib.Path(candidate)
   except Exception:pass
  adoptium_arch="x64" if SYSTEM_ARCH=="x86_64" else ("x86" if SYSTEM_ARCH=="x86" else SYSTEM_ARCH);self.progress(start,f"Downloading Java {major}");assets=self.get_json(f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot?architecture={adoptium_arch}&image_type=jre&os={SYSTEM_OS}&vendor=eclipse")
  if not assets:raise RuntimeError("No Java runtime download was found")
  package=assets[0]['binary']['package'];archive=managed/(package['name']);self.download(package['link'],archive,"Java runtime",start,end);managed.mkdir(parents=True,exist_ok=True)
  if archive.suffix.lower()=='.zip':
   with zipfile.ZipFile(archive) as z:z.extractall(managed)
  else:
   with tarfile.open(archive) as t:t.extractall(managed,filter='data')
  found=list(managed.glob("**/bin"+"/"+executable));
  if not found:raise RuntimeError("Downloaded Java runtime is incomplete")
  found[0].chmod(0o755);return found[0]

def launch(instance,account):
 root=pathlib.Path(instance);r=json.loads((root/"instance-launch.json").read_text());game=root/"minecraft";game.mkdir(exist_ok=True);values={"${auth_player_name}":account['name'],"${version_name}":r['version'],"${game_directory}":str(game),"${assets_root}":r['assets'],"${assets_index_name}":r['assetIndex'],"${auth_uuid}":account['id'].replace('-',''),"${auth_access_token}":account.get('minecraft_token','0'),"${clientid}":"","${auth_xuid}":"","${user_type}":"msa" if account['type']=='Microsoft' else "legacy","${version_type}":r['versionType'],"${natives_directory}":r['natives'],"${launcher_name}":"Zazu Launcher","${launcher_version}":"0.4.2","${classpath}":os.pathsep.join(r['classpath']),"${classpath_separator}":os.pathsep,"${library_directory}":str(pathlib.Path(r['assets']).parent/'libraries')}
 def expand(v):
  for k,x in values.items():v=v.replace(k,x)
  return v
 jvm=[];gameargs=[]
 def append_arg(target,item):
  if isinstance(item,str):target.append(expand(item))
  elif isinstance(item,dict):
   if rules_allowed(item.get('rules',[])):
    value=item.get('value',[]);value=[value] if isinstance(value,str) else value
    target.extend(expand(v) for v in value)
 for item in r.get('arguments',{}).get('jvm',[]):append_arg(jvm,item)
 for item in r.get('arguments',{}).get('game',[]):append_arg(gameargs,item)
 if not gameargs and r.get('legacyArguments'):gameargs=[expand(x) for x in shlex.split(r['legacyArguments'])]
 if not any(x.startswith('-Djava.library.path') for x in jvm):jvm.append('-Djava.library.path='+r['natives'])
 if '-cp' not in jvm and '-classpath' not in jvm:jvm+=['-cp',os.pathsep.join(r['classpath'])]
 memory=int(account.get('memory',4096));cmd=[r['java'],f'-Xmx{memory}M']+jvm+[r['mainClass']]+gameargs
 log=open(root/'latest-launch.log','w');creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if SYSTEM_OS=='windows' else 0;return subprocess.Popen(cmd,cwd=game,stdout=log,stderr=subprocess.STDOUT,creationflags=creationflags)
