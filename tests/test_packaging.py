from importlib.metadata import distribution
from pathlib import Path
import os
import subprocess
import sys


def test_installed_metadata() -> None:
    assert sys.version_info[:2] == (3, 14)
    metadata = distribution('m32-fx-reconciler')
    assert metadata.version == '0.1.0'
    assert not metadata.entry_points  # M3 entry points are not implemented.
    assert all('extra ==' in dep for dep in metadata.requires or ())


def test_import_is_inert(tmp_path: Path) -> None:
    code = '''
import sys
sys.dont_write_bytecode = True
import logging
from pathlib import Path
root = Path.cwd()
before = set(root.rglob('*'))
handlers = tuple(logging.root.handlers)
registry = dict(logging.Logger.manager.loggerDict)
def audit(event, args):
    if event == 'open':
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & 3):
            raise AssertionError('write during import')
    if event in ('os.mkdir', 'os.remove', 'os.rename'):
        raise AssertionError('mutation during import')
sys.addaudithook(audit)
import fx_reconciler
import fx_reconciler.models
import fx_reconciler.validation
import fx_reconciler.csv_input
import fx_reconciler.input_validation
import fx_reconciler.diagnostics
assert set(root.rglob('*')) == before
assert tuple(logging.root.handlers) == handlers
assert dict(logging.Logger.manager.loggerDict) == registry
'''
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp_path,
                            env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ''
    assert list(tmp_path.iterdir()) == []


def test_distributions_exclude_operational_artifacts(tmp_path: Path) -> None:
    import shutil
    import tarfile
    import zipfile
    project = Path(__file__).resolve().parents[1]
    root = tmp_path / 'project'
    root.mkdir()
    for name in ('pyproject.toml', 'README.md', 'MANIFEST.in', 'SPEC.md', 'AGENTS.md'):
        shutil.copyfile(project / name, root / name)
    shutil.copytree(project / 'src', root / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
    logs = root / 'src' / 'fx_reconciler' / 'logs'
    logs.mkdir(exist_ok=True)
    (logs / 'synthetic-run.jsonl').write_text('{}\n', encoding='utf-8')
    result = subprocess.run([sys.executable, '-c',
        "import setuptools.build_meta as b; b.build_wheel('dist'); b.build_sdist('dist')"],
        cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    wheel = next((root / 'dist').glob('*.whl'))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert 'fx_reconciler/__init__.py' in names
        assert not any('/logs/' in name or name.endswith('.jsonl') for name in names)
    with tarfile.open(next((root / 'dist').glob('*.tar.gz'))) as archive:
        assert not any('/logs/' in name or name.endswith('.jsonl') for name in archive.getnames())
