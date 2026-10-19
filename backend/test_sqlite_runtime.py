import ast
import contextlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock
from sqlite_runtime import commit_with_retry, is_busy_error, short_write


class SQLiteRuntimeTests(unittest.TestCase):
    def test_busy_classification_does_not_hide_disk_errors(self):
        self.assertTrue(is_busy_error(sqlite3.OperationalError('database is locked')))
        self.assertFalse(is_busy_error(sqlite3.OperationalError('database disk image is malformed')))
        self.assertFalse(is_busy_error(RuntimeError('database is locked')))

    def test_commit_retries_same_transaction_with_real_reader_lock(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'test.db'
            writer=sqlite3.connect(path,timeout=.01)
            writer.execute('CREATE TABLE items(value)');writer.commit()
            reader=sqlite3.connect(path);reader.execute('BEGIN');reader.execute('SELECT * FROM items').fetchall()
            writer.execute('INSERT INTO items VALUES(1)')
            waits=[]
            def release(delay): waits.append(delay);reader.rollback()
            commit_with_retry(writer,sleep=release)
            self.assertEqual(len(waits),1);self.assertEqual(writer.execute('SELECT count(*) FROM items').fetchone()[0],1)
            self.assertEqual(writer.execute('PRAGMA busy_timeout').fetchone()[0],10)
            reader.close();writer.close()

    def test_short_write_rolls_back_before_retry(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'test.db';initial=sqlite3.connect(path);initial.execute('CREATE TABLE items(value)');initial.close()
            @contextlib.contextmanager
            def db():
                c=sqlite3.connect(path)
                try:yield c;c.commit()
                except BaseException:c.rollback();raise
                finally:c.close()
            calls=[]
            def write(c):
                calls.append(1);c.execute('INSERT INTO items VALUES(1)')
                if len(calls)==1:raise sqlite3.OperationalError('database is locked')
                return 'ok'
            self.assertEqual(short_write(db,write,sleep=lambda _:None),'ok')
            with db() as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)
            operation=Mock(side_effect=sqlite3.OperationalError('disk I/O error'))
            with self.assertRaises(sqlite3.OperationalError):short_write(db,operation,sleep=lambda _:None)
            self.assertEqual(operation.call_count,1)

    def test_production_context_initializes_wal_once_and_releases_connections(self):
        # Execute the real db() source without starting app workers or touching production.
        source=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        function=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='db')
        with tempfile.TemporaryDirectory() as root:
            ready=threading.Event();schema_calls=[]
            def schema(c):schema_calls.append(1);c.execute('CREATE TABLE items(value)')
            ns={'sqlite3':sqlite3,'contextlib':contextlib,'threading':threading,'DB':str(Path(root)/'test.db'),
                '_schema_ready':ready,'_schema_lock':threading.Lock(),'ensure_schema':schema}
            exec(compile(ast.Module(body=[function],type_ignores=[]),'app.py','exec'),ns)
            errors=[];barrier=threading.Barrier(4)
            def worker():
                try:
                    barrier.wait()
                    with ns['db']() as c:c.execute('INSERT INTO items VALUES(1)')
                except BaseException as exc:errors.append(exc)
            threads=[threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=10)
            self.assertFalse(errors);self.assertEqual(len(schema_calls),1)
            with ns['db']() as c:
                self.assertEqual(c.execute('PRAGMA journal_mode').fetchone()[0],'wal')
                self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],4)
                c.execute('BEGIN');c.execute('SELECT * FROM items').fetchall()
                # WAL permits another writer while this read snapshot is open.
                with ns['db']() as other:other.execute('INSERT INTO items VALUES(2)')
            with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')


if __name__=='__main__':unittest.main()
