"""Run the documented flow with isolated home paths and stubbed privileged calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / 'README.md'
GIT = shutil.which('git')
OFFICIAL = 'https://github.com/wbell09/flightmeshair-feeder.git'

def git(*args, cwd=None):
    env=os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    return subprocess.run([GIT,*args],cwd=cwd,env=env,text=True,capture_output=True,check=True)

def commit(repo, text):
    (repo/'forward_dump1090.py').write_text(text)
    git('add','.',cwd=repo)
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','fixture',cwd=repo)

cases=['missing','bootstrap','original_clean','alternate_clean','alternate_directory','alternate_file',
       'alternate_broken_symlink','tracked_edits','untracked_edits','wrong_origin','missing_origin',
       'nested_in_other_repo','original_file','divergent_history','ahead_only','behind_only',
       'detached_head','no_upstream','wrong_branch','wrong_upstream','git_missing','root_user',
       'fetch_failure','missing_source_script','missing_installed_script','backup_failure',
       'install_failure','restart_failure']
success_cases={'missing','bootstrap','original_clean','alternate_clean','nested_in_other_repo','original_file','behind_only'}
results=[]
with tempfile.TemporaryDirectory(prefix='feeder-review-v2-') as temp:
    root=Path(temp)
    # Isolate only the two home-based source paths; never repurpose the process HOME.
    code=SOURCE.read_text().split('### Updating manually',1)[1].split('```bash\n',1)[1].split('```',1)[0]
    assert code.count('$HOME/flightmeshair-feeder')==2
    script=root/'flow.sh'
    subprocess.run(['/bin/bash','-n'], input=code, text=True, check=True)
    script.write_text(code.replace('$HOME/flightmeshair-feeder','$FIXTURE_HOME/flightmeshair-feeder'))
    bins=root/'bin'; bins.mkdir()
    (bins/'git').write_text('''#!/usr/bin/env python3
import os,sys
a=sys.argv[1:]
if 'fetch' in a and os.environ['FIXTURE_CASE']=='fetch_failure': sys.exit(1)
extra=[]
if any(op in a for op in ('clone','fetch')):
 extra=['-c','protocol.file.allow=always','-c','url.'+os.environ['FIXTURE_REMOTE']+'.insteadOf='+os.environ['FIXTURE_OFFICIAL']]
os.execv(os.environ['FIXTURE_GIT'],[os.environ['FIXTURE_GIT']]+extra+a)
''')
    (bins/'id').write_text('''#!/bin/sh
if [ "$FIXTURE_CASE" = root_user ]; then echo 0; else echo 501; fi
''')
    (bins/'sudo').write_text('''#!/usr/bin/env python3
import os,sys,json
a=sys.argv[1:]; case=os.environ['FIXTURE_CASE']
with open(os.environ['FIXTURE_LOG'],'a') as f: f.write(json.dumps(a)+'\\n')
if a[0]=='test' and case=='missing_installed_script': sys.exit(1)
if a[0]=='cp' and case=='backup_failure': sys.exit(1)
if a[0]=='install' and case=='install_failure': sys.exit(1)
if a[:2]==['systemctl','restart'] and case=='restart_failure': sys.exit(1)
if a[0]=='mktemp': print('/fixture-backup/previous.py')
''')
    for p in bins.iterdir(): p.chmod(0o755)
    nogit=root/'no-git-bin'; nogit.mkdir()
    (nogit/'id').write_text('#!/bin/sh\necho 501\n'); (nogit/'id').chmod(0o755)

    for case in cases:
        case_dir=root/case;case_dir.mkdir()
        remote=case_dir/'remote.git';seed=case_dir/'seed'
        git('init','--bare','--initial-branch=main',str(remote))
        git('clone',str(remote),str(seed))
        commit(seed,'print("published")\n');git('push','origin','main',cwd=seed)
        home=case_dir/'home';home.mkdir()
        original=home/'flightmeshair-feeder';alternate=home/'flightmeshair-feeder-git'
        def checkout(path):
            git('clone',str(remote),str(path))
            git('remote','set-url','origin',OFFICIAL,cwd=path)
        no_original={'missing','bootstrap','alternate_clean','alternate_directory','alternate_file',
                     'alternate_broken_symlink','nested_in_other_repo','original_file','git_missing','root_user'}
        if case not in no_original:checkout(original)
        if case=='bootstrap':
            original.mkdir();(original/'keep.txt').write_text('preserve')
        elif case=='alternate_clean':checkout(alternate)
        elif case=='alternate_directory':
            alternate.mkdir();(alternate/'keep.txt').write_text('preserve')
        elif case=='alternate_file':alternate.write_text('preserve')
        elif case=='alternate_broken_symlink':alternate.symlink_to(home/'absent')
        elif case=='nested_in_other_repo':
            git('init',str(home));original.mkdir()
        elif case=='original_file':original.write_text('preserve')
        elif case=='tracked_edits':(original/'forward_dump1090.py').write_text('local edit')
        elif case=='untracked_edits':(original/'notes.txt').write_text('local edit')
        elif case=='wrong_origin':git('remote','set-url','origin','https://example.invalid/other.git',cwd=original)
        elif case=='missing_origin':git('remote','remove','origin',cwd=original)
        elif case in ('ahead_only','divergent_history'):commit(original,'print("local commit")\n')
        elif case=='detached_head':git('checkout','--detach',cwd=original)
        elif case=='no_upstream':git('branch','--unset-upstream',cwd=original)
        elif case=='wrong_branch':git('checkout','-b','custom','--track','origin/main',cwd=original)
        elif case=='wrong_upstream':
            git('remote','add','other',str(remote),cwd=original);git('fetch','other',cwd=original)
            git('branch','--set-upstream-to=other/main',cwd=original)
        if case in ('behind_only','divergent_history'):
            commit(seed,'print("new published")\n');git('push','origin','main',cwd=seed)
        elif case=='missing_source_script':
            git('rm','forward_dump1090.py',cwd=seed)
            git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Remove script',cwd=seed)
            git('push','origin','main',cwd=seed)
        log=case_dir/'sudo.jsonl'
        env=os.environ.copy()
        env.update(FIXTURE_HOME=str(home),FIXTURE_CASE=case,FIXTURE_REMOTE=str(remote),
                   FIXTURE_GIT=GIT,FIXTURE_OFFICIAL=OFFICIAL,FIXTURE_LOG=str(log),
                   PATH=str(nogit) if case=='git_missing' else str(bins)+os.pathsep+env['PATH'],
                   GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
        run=subprocess.run(['/bin/bash',str(script)],env=env,text=True,capture_output=True)
        calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        assert (run.returncode==0)==(case in success_cases),(case,run.stdout,run.stderr,calls)
        operations=[a[0] if a[0]!='systemctl' else 'systemctl '+a[1] for a in calls]
        if case in success_cases:
            assert operations==['test','mktemp','cp','install','systemctl restart','systemctl status'],(case,calls)
            assert calls[2]==['cp','-p','/opt/flightmesh/forward_dump1090.py','/fixture-backup/previous.py']
            assert calls[3][-1]=='/opt/flightmesh/forward_dump1090.py'
        elif case=='missing_installed_script':assert operations==['test']
        elif case=='backup_failure':assert operations==['test','mktemp','cp']
        elif case=='install_failure':assert operations==['test','mktemp','cp','install']
        elif case=='restart_failure':assert operations==['test','mktemp','cp','install','systemctl restart']
        else:assert calls==[],(case,calls)
        if case=='git_missing':assert 'Git is required' in run.stderr
        if case=='root_user':assert 'normal feeder user' in run.stderr
        if case in ('ahead_only','divergent_history'):assert 'Local commits' in run.stderr
        if case=='behind_only':assert (original/'forward_dump1090.py').read_text()=='print("new published")\n'
        if case in ('bootstrap','alternate_directory'):
            assert ((original if case=='bootstrap' else alternate)/'keep.txt').read_text()=='preserve'
        if case in ('original_file','alternate_file'):
            assert (original if case=='original_file' else alternate).read_text()=='preserve'
        results.append({'case':case,'result':'PASS'})
print(json.dumps({'passed':len(results),'cases':results,'privileged_calls':'stubbed','network':'local fixture remotes only'},indent=2))
