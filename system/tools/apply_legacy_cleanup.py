"""Preview/remove only explicitly selected old snapshot files, never active system data."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path,PurePosixPath
SYSTEM=Path(__file__).resolve().parents[1]
GROUPS={'legacy':'legacy','experiment5':'collector/data/experiment5','supervised':'collector/data/supervised','supervised_results':'collector/data/supervised_results','within_family_results':'collector/data/within_family_results'}

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def linked(path):return path.is_symlink() or getattr(path,'is_junction',lambda:False)()
def cleanup(repo,groups,*,apply=False,confirm_inactive=False,inventory=None):
    repo=Path(repo).resolve()
    if not (repo/'system').is_dir():raise ValueError('Use repository root containing system/')
    if not groups or not set(groups)<=set(GROUPS):raise ValueError('Select known cleanup groups')
    groups=list(dict.fromkeys(groups))
    if apply and set(groups)-{'legacy'} and not confirm_inactive:raise ValueError('Historical derived data may still be used by teammates: --confirm-inactive required')
    inv=inventory if inventory is not None else json.loads((SYSTEM/'docs/LEGACY_CLEANUP_INVENTORY.json').read_text())['groups']
    removal=[];summary=[];dirs=[]
    # Preflight all selected groups before deleting anything.
    for group in groups:
        rel=GROUPS[group];folder=repo/rel
        for parent in (folder,*folder.parents):
            if parent==repo:break
            if linked(parent):raise ValueError(f'Symlink/junction refused: {parent}')
        spec=inv[group]
        if spec['directory']!=rel:raise ValueError('Inventory group mismatch')
        expected={}
        for entry in spec['files']:
            name=entry['path']; parts=PurePosixPath(name).parts
            if not name.startswith(rel+'/') or any(x in ('..','.') for x in parts) or '\\' in name or ':' in name or name in expected:raise ValueError('Unsafe inventory path')
            expected[name]=entry
        present=[]
        if folder.exists():
            if not folder.is_dir():raise ValueError(f'Not a directory: {rel}')
            for p in folder.rglob('*'):
                if linked(p):raise ValueError(f'Symlink/junction refused: {p}')
                if p.is_dir():dirs.append(p);continue
                name=p.relative_to(repo).as_posix()
                if not p.is_file() or name not in expected:raise ValueError(f'Unreviewed file; nothing removed: {name}')
                entry=expected[name]
                if p.stat().st_size!=entry['bytes'] or sha(p)!=entry['sha256']:raise ValueError(f'Modified file; nothing removed: {name}')
                present.append((p,entry))
            dirs.append(folder)
        removal.extend(present);summary.append({'group':group,'directory':rel,'matched_files':len(present),'bytes':sum(e['bytes'] for _,e in present),'missing_files':len(expected)-len(present)})
    if apply:
        for path,entry in removal:
            if linked(path) or sha(path)!=entry['sha256']:raise ValueError(f'File changed during cleanup: {path}; inspect working tree')
            path.unlink()
        for path in sorted(set(dirs),key=lambda p:len(p.parts),reverse=True):
            if path.is_dir() and not any(path.iterdir()):path.rmdir()
    return {'applied':apply,'groups':summary,'paths':[p.relative_to(repo).as_posix() for p,_ in removal]}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',type=Path,default=SYSTEM.parent);p.add_argument('--group',choices=list(GROUPS),action='append');p.add_argument('--apply',action='store_true');p.add_argument('--confirm-inactive',action='store_true');a=p.parse_args(argv)
    if a.apply and not a.group:p.error('--apply requires explicit --group selection')
    try:print(json.dumps(cleanup(a.repo_root,a.group or list(GROUPS),apply=a.apply,confirm_inactive=a.confirm_inactive),indent=2));return 0
    except (ValueError,OSError) as exc:print(f'Cleanup refused: {exc}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
