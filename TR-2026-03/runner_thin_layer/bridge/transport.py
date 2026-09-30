"""Foreground owner: 자식 프로세스·TCP·파일을 반드시 회수한다."""
import json, os, selectors, socket, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def receive(stream, timeout=30, readiness=None):
    with selectors.DefaultSelector() as sel:
        sel.register(readiness if readiness is not None else stream,selectors.EVENT_READ)
        if not sel.select(timeout):raise TimeoutError('JSONL 응답 시간 초과')
    raw=stream.readline()
    if not raw:raise RuntimeError('응답 전 EOF')
    return json.loads(raw)
def local_path(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT) or path.is_relative_to(ROOT/'vendor') or path.is_relative_to(ROOT/'.git'):
        raise ValueError('출력은 작업 루트 내부(vendor/.git 제외)만 허용')
    return path
def environment(out):
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GIT_OPTIONAL_LOCKS='0')
    for var,sub in [('TMPDIR','tmp'),('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('CLANG_MODULE_CACHE_PATH','clang-cache')]:
        p=out/sub;p.mkdir(parents=True,exist_ok=True);env[var]=str(p)
    return env
class Child:
    def __init__(self,args,out,name):
        self.err=(out/f'{name}-stderr.log').open('wb');self.sock=None;self.stream=None
        try:self.process=subprocess.Popen(args,cwd=ROOT,env=environment(out),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err)
        except BaseException:self.err.close();raise
    def send(self,request):
        writer=self.stream or self.process.stdin;writer.write(canon(request)+b'\n');writer.flush()
        response=receive(self.stream or self.process.stdout,readiness=self.sock)
        if response.get('ok') is not True:raise RuntimeError(response)
        return response
    def close(self,vision=False):
        try:
            if self.process.poll() is None:
                if vision:self.send(dict(cmd='quit'))
                else:self.process.stdin.close()
                rc=self.process.wait(timeout=10)
                if rc!=0:raise RuntimeError(f'자식 종료 코드 {rc}')
            elif self.process.returncode!=0:raise RuntimeError(f'자식 종료 코드 {self.process.returncode}')
        finally:
            if self.process.poll() is None:self.process.kill();self.process.wait(timeout=10)
            if self.stream:self.stream.close()
            if self.sock:self.sock.close()
            for stream in (self.process.stdin,self.process.stdout):
                if stream and not stream.closed:stream.close()
            self.err.close()
class Vision(Child):
    def __init__(self,exe,cell,out,gui=False,hmi=False):
        args=[str(exe),'--external-control-gui' if gui else '--external-control','--cell',str(cell)]
        if hmi:args+=['--hmi-qa','--controller','external']
        if gui:
            screen=json.loads(subprocess.check_output([str(ROOT/'.cache/window-bounds'),'screen'],env=environment(out)))
            width=min(1450,max(1100,screen['width']-1000));height=min(1100,screen['height']-40)

            while True:
                with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
                if not 8790<=port<=8799:break
            args+=['--tcp-port',str(port)]
        super().__init__(args,out,'vision')
        if gui:
            try:
                end=time.monotonic()+30
                while True:
                    try:self.sock=socket.create_connection(('127.0.0.1',port),timeout=1);break
                    except OSError:
                        if self.process.poll() is not None or time.monotonic()>end:raise
                        time.sleep(.02)
                self.sock.settimeout(30);self.stream=self.sock.makefile('rwb')
            except BaseException:
                self.process.kill();self.process.wait();self.err.close();raise
