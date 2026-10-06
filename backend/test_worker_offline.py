import ast
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class OfflineSnapshotTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).with_name('worker.py').read_text(encoding='utf-8'))
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='local_aligner_snapshot')
        self.namespace={'Path':Path,'ALIGNER_MODEL':'Qwen/Qwen3-ForcedAligner-0.6B'}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'worker.py','exec'),self.namespace)

    def populate(self,root):
        for name in ('config.json','model.safetensors','preprocessor_config.json','tokenizer_config.json','vocab.json','merges.txt'):
            (root/name).touch()
            (root/name).write_bytes(b'fixture')

    def test_repository_uses_cached_snapshot_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.populate(root)
            download=Mock(return_value=directory)
            with patch.dict(sys.modules,{'huggingface_hub':types.SimpleNamespace(snapshot_download=download)}):
                self.assertEqual(self.namespace['local_aligner_snapshot'](),str(root.resolve()))
            download.assert_called_once_with(repo_id='Qwen/Qwen3-ForcedAligner-0.6B',local_files_only=True)

    def test_missing_weights_fail_before_model_load(self):
        with tempfile.TemporaryDirectory() as directory:
            self.namespace['ALIGNER_MODEL']=directory
            with self.assertRaisesRegex(RuntimeError,'model.safetensors'):
                self.namespace['local_aligner_snapshot']()

    def test_missing_cache_has_actionable_offline_error(self):
        download=Mock(side_effect=OSError('cache unavailable'))
        with patch.dict(sys.modules,{'huggingface_hub':types.SimpleNamespace(snapshot_download=download)}):
            with self.assertRaisesRegex(RuntimeError,'预先安装完整模型缓存'):
                self.namespace['local_aligner_snapshot']()
        download.assert_called_once_with(repo_id='Qwen/Qwen3-ForcedAligner-0.6B',local_files_only=True)

    def test_explicit_local_directory_needs_no_hub(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.populate(root);self.namespace['ALIGNER_MODEL']=directory
            with patch.dict(sys.modules,{'huggingface_hub':None}):
                self.assertEqual(self.namespace['local_aligner_snapshot'](),str(root.resolve()))


if __name__=='__main__':
    unittest.main()
