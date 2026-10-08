"""Foreground owner: 자식 프로세스·TCP·파일을 반드시 회수한다. (TR-2026-05 사본: 출력 위치 규칙 · --physics · 환경 정리 · GUI 제거)"""
import json, os, selectors, subprocess
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
    # TR-05 사본: 원시 기록이 커서(셀 B 5,000 틱) 사본 밖 폴더도 허용한다. 사본의 고정 입력 폴더 안에는 runs/ 아래만.
    path=Path(path).resolve()
    if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT/'runs'):
        raise ValueError('사본 안의 출력은 runs/ 아래만 허용(고정 입력 폴더 보호)')
    return path
def environment(out):
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GIT_OPTIONAL_LOCKS='0')
    env.pop('VEXPLOR_EXTCTL_PHYSICS',None)  # §6-2: 모드는 CLI 로만
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
    # TR-05 v0.5 구현(리드 결정 2026-10-08): F 의 첫 판-상자 이동 기록(state.fast_first_contact)은 앱 옵트인 --report-first-contact.
    # 실행기는 모든 F 실행에 준다(다른 키는 바이트 같음 — 앱 시험). M 에는 영향 없음. 예전 기록 재생 등은 report_first_contact=False.
    def __init__(self,exe,cell,out,physics,report_first_contact=None):
        flag=(physics=='fast') if report_first_contact is None else report_first_contact
        self.args=[str(exe),'--external-control','--cell',str(cell),'--physics',physics]+(['--report-first-contact'] if flag else [])
        super().__init__(self.args,out,'vision')
