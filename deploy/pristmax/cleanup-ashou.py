import pathlib, shutil, subprocess
subprocess.run(['systemctl','disable','--now','ashou.service'],check=True)
for name in ('/opt/ashou','/opt/ashou-new','/opt/ashou-old'):
 p=pathlib.Path(name)
 if p.is_symlink() or str(p.resolve()) != name or p.parent != pathlib.Path('/opt'):
  raise RuntimeError('Unexpected cleanup target: '+name)
 if p.exists(): shutil.rmtree(p)
p=pathlib.Path('/etc/systemd/system/ashou.service')
if p.is_file(): p.unlink()
subprocess.run(['systemctl','daemon-reload'],check=True)
pathlib.Path('/root/pristmax-migration-20260917/ashou-full-backup.tar.gz').unlink()
print('Removed archived Ashou project directories, service, and transferred archive.')
