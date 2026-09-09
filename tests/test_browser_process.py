"""Hard-stop lifecycle tests. Only the optional smoke test starts Chromium."""
import os
import time
import pytest
from bantou.fetching.browser_process import ProcessBrowserWorker


def hanging_worker(connection):
    if os.name != 'nt':
        os.setsid()
    connection.send(('ready',None))
    connection.recv()
    while True:
        time.sleep(1)


def echo_worker(connection):
    if os.name != 'nt':
        os.setsid()
    connection.send(('ready',None))
    while True:
        task=connection.recv()
        if task is None:
            break
        connection.send(('ok',('ok',task[0])))
    connection.close()


def test_killable_timeout_and_recovery():
    worker=ProcessBrowserWorker(target=hanging_worker)
    start=time.monotonic()
    with pytest.raises(TimeoutError):
        worker.render('https://example.test/',2,True,True,'load')
    assert time.monotonic()-start < 12
    assert worker._process is None
    worker._target=echo_worker
    assert worker.render('https://example.test/#one',3,True,True,'load')=='ok'
    process=worker._process
    worker.close()
    assert worker._process is None


@pytest.mark.skipif(os.environ.get('RUN_BROWSER_SMOKE')!='1',reason='Chromium smoke explicitly enabled by Windows CI')
def test_real_chromium_local_fragment():
    worker=ProcessBrowserWorker()
    # Inline document only; no remote site or public Internet request.
    url='data:text/html,<html><body><script>document.body.textContent=location.hash</script></body></html>#route-251'
    try:
        content=worker.render(url,20,True,False,'load')
        assert '#route-251' in content
        assert content.final_url.endswith('#route-251')
    finally:
        worker.close()
